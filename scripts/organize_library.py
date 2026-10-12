"""Build the local document library from source archives and existing files.

Original archives and extraction caches are left untouched. Re-running this script is safe:
identical bytes are stored once, and the public catalog never includes slides or lessons.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'knowledge' / 'library'
ARCHIVES = ROOT / 'new_things'
DATA = ROOT / 'knowledge' / 'data'
CATEGORIES = {'documents', 'papers', 'literature', 'courses', 'pdf', 'presentations', 'media'}
ALLOWED = {'documents', 'papers', 'literature', 'pdf', 'media'}


def category(name: str) -> str:
    name = Path(name).name
    suffix = Path(name).suffix.lower()
    if suffix in {'.ppt', '.pptx'}:
        return 'presentations'
    if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov'}:
        return 'media'
    if suffix == '.pdf':
        return 'pdf'
    if ('教学' in name or '教案' in name or '课件' in name or '课程' in name
            or '研修' in name or '第四讲' in name):
        return 'courses'
    if '论文' in name:
        return 'papers'
    if name.startswith(('3820_习近平', '3820_网文', '3820_资料_')):
        return 'literature'
    return 'documents'


def clean_name(name: str) -> str:
    name = Path(name).name.replace('/', '_').replace('\\', '_')
    name = re.sub(r'\s+', ' ', name).strip()
    # The two old Word files and the course slides are OOXML despite their suffixes.
    if name.lower().endswith('.doc'):
        name += 'x'
    if name.lower().endswith('.ppt'):
        name += 'x'
    return name


def markdown_to_docx(source: Path, destination: Path) -> None:
    """Create a readable Word download while preserving the Markdown source for preview."""
    doc = Document()
    in_code = False
    for line in source.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            in_code = not in_code
            continue
        if not line.strip():
            continue
        if in_code:
            doc.add_paragraph(line, style='No Spacing')
        elif line.startswith('#') and re.match(r'^#{1,6}\s', line):
            level = min(len(line) - len(line.lstrip('#')), 4)
            doc.add_heading(line[level:].strip(), level=level)
        elif re.match(r'^\s*[-*+]\s+', line):
            doc.add_paragraph(re.sub(r'^\s*[-*+]\s+', '', line), style='List Bullet')
        elif re.match(r'^\s*\d+[.)]\s+', line):
            doc.add_paragraph(re.sub(r'^\s*\d+[.)]\s+', '', line), style='List Number')
        else:
            doc.add_paragraph(re.sub(r'\*\*|__|`', '', line))
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)


def build() -> dict:
    LIBRARY.mkdir(parents=True, exist_ok=True)
    for group in CATEGORIES:
        (LIBRARY / group).mkdir(exist_ok=True)
    entries: list[dict] = []
    by_digest: dict[str, dict] = {}
    duplicate_sources: list[dict] = []

    def add(name: str, payload: bytes, source: str, display_title: str | None = None) -> None:
        if name.startswith('._') or Path(name).name.startswith('~$'):
            return
        digest = hashlib.sha256(payload).hexdigest()
        if digest in by_digest:
            duplicate_sources.append({'source': source, 'same_as': by_digest[digest]['path']})
            return
        group = category(name)
        filename = clean_name(name)
        target = LIBRARY / group / filename
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target = target.with_name(f'{target.stem}-{digest[:8]}{target.suffix}')
        if not target.exists():
            target.write_bytes(payload)
        rel = target.relative_to(ROOT).as_posix()
        title = display_title or target.stem
        if filename.startswith('原件扫描_page_'):
            title = f'福州市20年经济社会发展战略设想 · 原件扫描第{int(source.rsplit("_", 1)[-1].removesuffix(".png"))}页'
        item = {'id': digest[:20], 'title': title, 'path': rel,
                'category': group, 'sha256': digest, 'bytes': len(payload),
                'source': source, 'searchable': group in ALLOWED}
        entries.append(item)
        by_digest[digest] = item
        if target.suffix.lower() == '.md':
            word = target.with_suffix('.docx')
            if not word.exists() or word.stat().st_mtime_ns < target.stat().st_mtime_ns:
                markdown_to_docx(target, word)
            item['download_path'] = word.relative_to(ROOT).as_posix()

    # Source ZIP 1 contains the text corpus, an inner PDF archive and duplicate lessons.
    for archive in sorted(ARCHIVES.glob('*.zip')):
        with ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name.startswith('03_代码/'):
                    continue
                if name.endswith('3820视频.pptx-含4段内嵌视频与图片'):
                    add('3820视频.pptx', z.read(info), f'{archive.name}/{name}')
                    continue
                payload = z.read(info)
                if '若干资料.zip' in name:
                    with ZipFile(io.BytesIO(payload)) as inner:
                        for inner_info in inner.infolist():
                            if inner_info.is_dir() or inner_info.filename.lower().endswith('.epub'):
                                continue  # A Markdown transcription of the EPUB is in the text corpus.
                            add(inner_info.filename, inner.read(inner_info), f'{archive.name}/{name}/{inner_info.filename}')
                elif Path(name).suffix.lower() in {'.md', '.doc', '.docx', '.pdf', '.ppt', '.pptx', '.mp4', '.png', '.jpg'}:
                    add(name, payload, f'{archive.name}/{name}')

    for source in sorted(DATA.iterdir()):
        if source.is_file() and source.suffix.lower() in {'.doc', '.docx', '.ppt', '.pptx', '.mp4'}:
            if source.name == '3820PPT+视频.ppt':
                duplicate_sources.append({'source': source.relative_to(ROOT).as_posix(),
                                          'same_as': 'knowledge/library/presentations/3820视频.pptx',
                                          'reason': 'same 29-slide text, earlier deck version'})
                continue
            add(source.name, source.read_bytes(), source.relative_to(ROOT).as_posix())
    public_dir = DATA / 'public_sources'
    public_manifest = public_dir / 'manifest.json'
    if public_manifest.is_file():
        for record in json.loads(public_manifest.read_text(encoding='utf-8')):
            source = public_dir / f'{record["id"]}.txt'
            if not source.is_file():
                continue
            body = source.read_text(encoding='utf-8', errors='replace').strip()
            document = f'# {record["title"]}\n\n来源：{record["url"]}\n\n{body}\n'
            add(f'3820_资料_公开网页_{record["id"]}.md', document.encode('utf-8'),
                source.relative_to(ROOT).as_posix(), record['title'])
    # Original scan page images and images attached to project documents are retained as media.
    for source in sorted((DATA / 'original_3820' / 'pages').glob('*.png')):
        add(f'原件扫描_{source.name}', source.read_bytes(), source.relative_to(ROOT).as_posix())
    for source in sorted((ROOT / 'docs' / 'media').glob('*')):
        if source.is_file():
            add(source.name, source.read_bytes(), source.relative_to(ROOT).as_posix())

    # The guide remains in docs/, its authoritative location. It is exposed through the catalog.
    for source in sorted((ROOT / 'docs').glob('基于3820战略工程内容的多智能体系统搭建指南.md')):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        entries.append({'id': digest[:20], 'title': source.stem, 'path': source.relative_to(ROOT).as_posix(),
                        'category': 'documents', 'sha256': digest, 'bytes': source.stat().st_size,
                        'source': 'project guide', 'searchable': True,
                        'download_path': (source.with_suffix('.docx')).relative_to(ROOT).as_posix()})

    entries.sort(key=lambda item: (item['category'], item['title'], item['path']))
    catalog = {'version': 1, 'entries': entries, 'duplicates': duplicate_sources,
               'counts': dict(Counter(item['category'] for item in entries))}
    (LIBRARY / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    return catalog


if __name__ == '__main__':
    result = build()
    print(json.dumps({'counts': result['counts'], 'duplicates': len(result['duplicates'])}, ensure_ascii=False))

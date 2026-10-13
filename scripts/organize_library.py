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
import unicodedata
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
PAGE_MARKER = re.compile(r'^【第(\d+)页(?:·([^】]+))?】\s*(.*)$')
SOURCE_META = re.compile(r'^(?:来源链接|抓取时间|提取方式)\s*[:：]|^来源\s*[:：]\s*(?:微信|https?://)')
IMPORT_NOTE = re.compile(r'^（.*(?:自动提取|未经人工校对).*[）)]$')
SITE_BANNER = ('学习贯彻习近平新时代中国特色社会主义思想', '学习贯彻党的二十届四中全会精神',
               '学习贯彻全国组织工作会议精神')
WEB_FOOTER = re.compile(r'^(?:发布时间：.*?编辑：.*|(?:京|闽)ICP备\d+号(?:-\d+)?|责任编辑：.*)$')
MIRROR_SUFFIX = re.compile(r'\s*[（(](?:z-library|1lib|z-lib)[^）)]*[）)]', re.I)
WEB_ARTICLE_BOUNDARIES = {
    '福州市政府-3820战略工程解读': ('“3820”战略工程解读', '市自然资源和规划局'),
    '福州市发改委-有福之州大步迈向现代化国际城市':
        ('有福之州大步迈向现代化国际城市——“3820”战略工程引领福州高质量发展',
         '扫一扫在手机上查看当前页面'),
    '福建省民政厅-把宏伟蓝图变成美好现实':
        ('牢记嘱托 感恩奋进', '扫一扫在手机上查看当前页面'),
}


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
    if name.lower().endswith('.pdf'):
        stem = MIRROR_SUFFIX.sub('', Path(name).stem)
        stem = re.sub(r'[（(]已做\s*OCR[）)]|3820已做\s*OCR', '', stem, flags=re.I)
        name = stem.strip() + '.pdf'
    return name


def clean_title(value: str) -> str:
    value = MIRROR_SUFFIX.sub('', value).strip()
    value = re.sub(r'[（(]已做\s*OCR[）)]|3820已做\s*OCR', '', value, flags=re.I)
    value = re.sub(r'^论文[:：]\s*', '', value)
    value = re.sub(r'\s*[_]\s*(?=[^_]{1,18}$)', ' · ', value)
    return value.strip(' _-')


def _normal_line(line: str) -> str:
    full = '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
    ascii_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    line = line.translate(str.maketrans(full, ascii_chars)).replace('\ufeff', '')
    line = ''.join(char for char in line if unicodedata.category(char) not in {'Co', 'Cs', 'Cf'})
    return line.strip()


def _join_wrapped(lines: list[str]) -> str:
    result = ''
    for line in lines:
        if result and re.search(r'[A-Za-z0-9]$', result) and re.match(r'^[A-Za-z0-9]', line):
            result += ' '
        result += line
    return result


def sanitize_markdown(raw: str) -> tuple[str, str, str | None, list[int]]:
    """Remove importer notes; turn real PDF page boundaries into readable sections."""
    lines = raw.replace('\r\n', '\n').splitlines()
    heading = clean_title(_normal_line(lines[0]).lstrip('# ').strip()) if lines else '未命名文献'
    source_url = None
    body = []
    for line in lines[1:]:
        line = _normal_line(line)
        if line.startswith('来源链接：') or line.startswith('来源链接:'):
            source_url = re.sub(r'^来源链接\s*[:：]\s*', '', line)
        elif re.match(r'^来源\s*[:：]\s*https?://', line):
            source_url = re.sub(r'^来源\s*[:：]\s*', '', line)
        if SOURCE_META.match(line) or IMPORT_NOTE.match(line) or line in SITE_BANNER or WEB_FOOTER.match(line):
            continue
        body.append(line)
    while body and not body[0]:
        body.pop(0)

    # Three source-site exports contain navigation and footer text around the
    # article. Keep the article title/date/body while dropping only those page
    # wrappers; the download Word is generated from this same clean text.
    if heading in WEB_ARTICLE_BOUNDARIES:
        first, last = WEB_ARTICLE_BOUNDARIES[heading]
        start = next((i for i, line in enumerate(body) if line == first), None)
        end = next((i for i, line in enumerate(body) if line == last), None)
        if start is not None and end is not None and start < end:
            body = [line for line in body[start:end]
                    if not line.startswith('0" style="display: none')]

    has_pages = any(PAGE_MARKER.match(line) for line in body)
    if not has_pages:
        clean = []
        last_blank = False
        for line in body:
            if line in {'封面', '书名页'}:
                continue
            if not line:
                if not last_blank:
                    clean.append('')
                last_blank = True
            else:
                clean.append(line)
                last_blank = False
        return f'# {heading}\n\n' + '\n'.join(clean).strip() + '\n', heading, source_url, []

    output = [f'# {heading}', '']
    paragraph: list[str] = []
    pages = []

    def flush():
        if paragraph:
            output.extend([_join_wrapped(paragraph), ''])
            paragraph.clear()

    for line in body:
        marker = PAGE_MARKER.match(line)
        if marker:
            flush()
            page = int(marker.group(1))
            pages.append(page)
            label = f'## 第 {page} 页'
            if marker.group(2):
                label += f' · {marker.group(2)}'
            output.extend(['---', '', label, ''])
            line = marker.group(3).strip()
        if not line:
            flush()
            continue
        if line in {'目 录', '目录'} or re.match(r'^第[一二三四五六七八九十0-9]+[章节]\s', line):
            flush()
            output.extend([f'### {line}', ''])
            continue
        if re.search(r'\.{4,}\s*\d+\s*$', line):
            flush()
            output.extend([line, ''])
            continue
        paragraph.append(line)
        if re.search(r'[。！？!?]$|\]$', line):
            flush()
    flush()
    return '\n'.join(output).rstrip() + '\n', heading, source_url, pages


def markdown_to_docx(source: Path, destination: Path) -> None:
    """Create a readable Word download while preserving the Markdown source for preview."""
    doc = Document()
    in_code = False
    for line in source.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            in_code = not in_code
            continue
        if not line.strip() or line.strip() == '---':
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
    archives = sorted(ARCHIVES.glob('*.zip'))
    if len(archives) < 3 or not (DATA / 'public_sources' / 'manifest.json').is_file() \
            or not any((DATA / 'original_3820' / 'pages').glob('*.png')):
        raise RuntimeError('原始压缩包和扫描/网页缓存不完整，停止重建，保留现有资料目录')
    if LIBRARY.is_dir():
        shutil.rmtree(LIBRARY)
    LIBRARY.mkdir(parents=True, exist_ok=True)
    for group in CATEGORIES:
        (LIBRARY / group).mkdir(exist_ok=True)
    entries: list[dict] = []
    by_digest: dict[str, dict] = {}
    duplicate_sources: list[dict] = []

    def add(name: str, payload: bytes, source: str, display_title: str | None = None) -> None:
        if name.startswith('._') or Path(name).name.startswith('~$'):
            return
        group = category(name)
        source_url = None
        pages = []
        if Path(name).suffix.lower() == '.md':
            clean, document_title, source_url, pages = sanitize_markdown(payload.decode('utf-8-sig', errors='replace'))
            payload = clean.encode('utf-8')
        else:
            document_title = clean_title(display_title or Path(name).stem)
        digest = hashlib.sha256(payload).hexdigest()
        if digest in by_digest:
            duplicate_sources.append({'source': source, 'same_as': by_digest[digest]['path']})
            return
        filename = clean_name(name)
        target = LIBRARY / group / filename
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target = target.with_name(f'{target.stem}-{digest[:8]}{target.suffix}')
        if not target.exists():
            target.write_bytes(payload)
        rel = target.relative_to(ROOT).as_posix()
        title = clean_title(display_title or document_title)
        if filename.startswith('原件扫描_page_'):
            title = f'福州市20年经济社会发展战略设想 · 原件扫描第{int(source.rsplit("_", 1)[-1].removesuffix(".png"))}页'
        searchable = group in ALLOWED and not filename.startswith('原件扫描_page_')
        if name == '0cdf9890d95614347108c00094f33b1d.mp4':
            searchable = False  # The inspected footage is a training site visit.
        item = {'id': digest[:20], 'title': title, 'path': rel,
                'category': group, 'sha256': digest, 'bytes': len(payload),
                'source': source, 'searchable': searchable}
        if source_url:
            item['source_url'] = source_url
        if pages:
            item['pages'] = pages
        if name.startswith('3820_习近平在福州_'):
            item['collection'] = '《习近平在福州》采访实录'
        elif name.startswith('3820_习近平在福建_'):
            item['collection'] = '《习近平在福建》采访实录'
        entries.append(item)
        by_digest[digest] = item
        if target.suffix.lower() == '.md':
            word = target.with_suffix('.docx')
            if not word.exists() or word.stat().st_mtime_ns < target.stat().st_mtime_ns:
                markdown_to_docx(target, word)
            item['download_path'] = word.relative_to(ROOT).as_posix()

    # Source ZIP 1 contains the text corpus, an inner PDF archive and duplicate lessons.
    for archive in archives:
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
                    if Path(name).name == '3820_knowledge.md':
                        continue  # An importer seed note, not an independent source.
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
            if record['id'] in {'3820_fuzhou_explainer', 'fuzhou_interview_18',
                                'fuzhou_interview_14', 'fujian_interview_28'}:
                continue  # The same article is present in the supplied article corpus.
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
            continue  # Project guide images are not independent literature.

    pdf_text_pairs = {
        '习近平党建思想的时代特质': '习近平党建思想的时代特质',
        '习近平关于基层治理论述摘编': '习近平关于基层治理论述摘编',
        '习近平总书记关于党的建设的重要思想概论': '习近平总书记关于党的建设的重要思想概论',
        '福州市20年经济社会发展战略设想': '福州市20年经济社会发展战略设想',
    }
    texts = [item for item in entries if item['path'].endswith('.md')]
    for item in entries:
        if item['category'] != 'pdf':
            continue
        for pdf_prefix, text_prefix in pdf_text_pairs.items():
            if item['title'].startswith(pdf_prefix):
                pair = next((text for text in texts if text['title'].startswith(text_prefix)
                             and text.get('pages')), None)
                if pair:
                    item['text_path'] = pair['path']
                    item['pages'] = pair['pages']
                    pair['pdf_id'] = item['id']
                break

    entries.sort(key=lambda item: (item['category'], item['title'], item['path']))
    catalog = {'version': 1, 'entries': entries, 'duplicates': duplicate_sources,
               'counts': dict(Counter(item['category'] for item in entries))}
    (LIBRARY / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    return catalog


if __name__ == '__main__':
    result = build()
    print(json.dumps({'counts': result['counts'], 'duplicates': len(result['duplicates'])}, ensure_ascii=False))

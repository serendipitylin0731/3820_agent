"""Incrementally import the newly supplied electronic books without rebuilding the library.

The source archive remains in new_things/.  OCR transcriptions are cached outside
knowledge/library/ so a later full library rebuild can be followed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from zipfile import ZipFile

from scripts.organize_library import markdown_to_docx

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'new_things' / '相关电子版资料.rar'
LIBRARY = ROOT / 'knowledge' / 'library'
CACHE = ROOT / 'knowledge' / 'data' / 'supplemental_text'
CATALOG = LIBRARY / 'catalog.json'
_OCR_READER = None

BOOKS = {
    '《习近平谈治国理政》第一卷': '习近平谈治国理政·第一卷',
    '《习近平谈治国理政》第二卷': '习近平谈治国理政·第二卷',
    '《习近平谈治国理政》第三卷': '习近平谈治国理政·第三卷',
    '《习近平谈治国理政》第四卷': '习近平谈治国理政·第四卷',
    '《习近平谈治国理政》第五卷': '习近平谈治国理政·第五卷',
    '中国共产党第十九届中央委员会第六次全体会议公报': '中国共产党第十九届中央委员会第六次全体会议公报',
    '习近平生态文明思想概论': '习近平生态文明思想概论',
    '十九大报告': '中国共产党第十九次全国代表大会报告',
    '闽山闽水物华新  习近平福建足迹(上)': '闽山闽水物华新·习近平福建足迹（上）',
    '闽山闽水物华新——习近平福建足迹(下)': '闽山闽水物华新·习近平福建足迹（下）',
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _normal_text(value: str) -> str:
    value = value.replace('\x00', '').replace('\u200b', '').replace('\ufeff', '')
    value = value.replace('仅限于教学及科研使用', '')
    value = re.sub(r'\r\n?', '\n', value)
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()


def _ocr_page(page, reader) -> str:
    import fitz
    import numpy as np

    pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
    channels = pix.n
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, channels)
    result, _ = reader(pixels)
    if not result:
        return ''
    return _normal_text('\n'.join(row[1] for row in result if len(row) > 1 and row[1]))


def _prefer_ocr(body: str, recognized: str) -> bool:
    """Reject a long but mostly garbled PDF text layer in favor of legible OCR."""
    body_hanzi = len(re.findall(r'[\u4e00-\u9fff]', body))
    ocr_hanzi = len(re.findall(r'[\u4e00-\u9fff]', recognized))
    body_ratio = body_hanzi / max(len(body), 1)
    ocr_ratio = ocr_hanzi / max(len(recognized), 1)
    if (re.match(r'[\u4e00-\u9fff]\d{3}\s*年', body) and
            re.match(r'(?:19|20)\d{2}年', recognized) and
            ocr_hanzi >= body_hanzi * 0.8):
        return True
    return ocr_hanzi >= 5 and (ocr_hanzi > body_hanzi or
                                ocr_hanzi >= body_hanzi * 0.4 and
                                ocr_ratio > body_ratio * 2)


def transcribe_span(source: str, title: str, start: int, stop: int) -> tuple[str, int, list[int], int, str]:
    """Extract a bounded PDF page range so scanned books can use several workers."""
    import fitz

    global _OCR_READER
    reader = _OCR_READER
    ocr_pages = 0
    numbered = []
    parts = []
    with fitz.open(source) as document:
        for number in range(start, stop):
            page = document[number - 1]
            body = _normal_text(page.get_text(sort=True))
            # Some editions contain image-only front matter and image-only body pages.
            # Preserve their actual PDF page positions in the transcript.
            if len(re.findall(r'[\u4e00-\u9fff]', body)) < 50:
                if reader is None:
                    import cv2
                    from rapidocr_onnxruntime import RapidOCR
                    cv2.setNumThreads(1)
                    gpu = os.environ.get('AGENT3820_OCR_GPU') == '1'
                    reader = RapidOCR(det_use_cuda=gpu, cls_use_cuda=gpu, rec_use_cuda=gpu,
                                      intra_op_num_threads=1, inter_op_num_threads=1)
                    if gpu and 'CUDAExecutionProvider' not in reader.text_det.infer.session.get_providers():
                        raise RuntimeError('CUDA OCR requested but CUDAExecutionProvider is unavailable')
                    _OCR_READER = reader
                recognized = _ocr_page(page, reader)
                if _prefer_ocr(body, recognized):
                    body = recognized
                ocr_pages += 1
            if len(re.findall(r'[\u4e00-\u9fff]', body)) < 3:
                continue
            numbered.append(number)
            parts.extend(['---', '', f'## 第 {number} 页', '', body, ''])
    print(f'{title}: processed pages {start}-{stop - 1}', flush=True)
    return title, start, numbered, ocr_pages, '\n'.join(parts).rstrip() + '\n'


def _extract(archive: Path, destination: Path) -> Path:
    if not archive.is_file():
        raise FileNotFoundError(archive)
    subprocess.run(['bsdtar', '-xf', str(archive), '-C', str(destination)], check=True)
    files = list(destination.rglob('*.pdf'))
    if len(files) < len(BOOKS):
        raise RuntimeError(f'RAR extraction incomplete: found {len(files)} PDFs')
    return files[0].parent


def _select(folder: Path) -> dict[str, Path]:
    result = {}
    for prefix, title in BOOKS.items():
        matches = [path for path in folder.glob('*.pdf') if path.name.startswith(prefix)]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one PDF for {title}, found {len(matches)}')
        result[title] = matches[0]
    return result


def _archive_duplicates(folder: Path, entries: list[dict], existing: list[dict]) -> list[dict]:
    """Account for the other two new uploads and repeated titles in the RAR."""
    by_hash = {item['sha256']: item for item in entries}
    seen = {item['source'] for item in existing}
    found = []

    def add(source: str, same_as: str, reason: str) -> None:
        if source not in seen:
            found.append({'source': source, 'same_as': same_as, 'reason': reason})
            seen.add(source)

    for path in folder.iterdir():
        if path.suffix.lower() == '.pdf' and not any(path.name.startswith(prefix) for prefix in BOOKS):
            title = next((title for title in (
                '习近平关于基层治理论述摘编',
                '习近平总书记关于党的建设的重要思想概论') if path.name.startswith(title)), None)
            match = next((item for item in entries if item['category'] == 'pdf'
                          and item['title'].startswith(title)), None) if title else None
            if match:
                add(f'{ARCHIVE.relative_to(ROOT).as_posix()}/{path.name}', match['path'],
                    'same-title alternative edition; existing complete OCR reading copy retained')
        elif path.suffix.lower() == '.md':
            match = next((item for item in entries if item['category'] == 'literature'
                          and '第二十次全国代表大会' in item['title'] and '报告' in item['title']), None)
            if match:
                add(f'{ARCHIVE.relative_to(ROOT).as_posix()}/{path.name}', match['path'],
                    'shorter text of a report already held in full')

    slide = next((item for item in (ROOT / 'new_things').glob('*.pptx')
                  if '张玲2024' in item.name), None)
    if slide:
        target = by_hash.get(_sha(slide))
        if target:
            add(slide.relative_to(ROOT).as_posix(), target['path'], 'identical SHA-256')

    zip_path = ROOT / 'new_things' / '3820若干资料.zip'
    if zip_path.is_file():
        with ZipFile(zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                source = f'{zip_path.relative_to(ROOT).as_posix()}/{member.filename}'
                if member.filename.lower().endswith('.epub'):
                    target = next((item for item in entries if item['category'] == 'literature'
                                   and item['title'].startswith('江山就是人民 人民就是江山')), None)
                    if target:
                        add(source, target['path'], 'existing Markdown transcription of this EPUB')
                else:
                    digest = hashlib.sha256(archive.read(member)).hexdigest()
                    target = by_hash.get(digest)
                    if target:
                        add(source, target['path'], 'identical SHA-256')
    return found


def import_books(folder: Path, workers: int = 8, refresh_titles: set[str] | None = None) -> dict:
    selected = _select(folder)
    refresh_titles = refresh_titles or set()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    entries = catalog['entries']
    by_sha = {record['sha256'] for record in entries}
    pending = {}
    for title, source in selected.items():
        digest = _sha(source)
        if digest not in by_sha or title in refresh_titles:
            pending[title] = (source, digest)
    if pending:
        import fitz
        CACHE.mkdir(parents=True, exist_ok=True)
        work = {}
        results = {}
        with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
            for title, (source, digest) in pending.items():
                target = CACHE / f'{digest}.md'
                if target.exists() and title not in refresh_titles:
                    continue
                with fitz.open(source) as document:
                    total = len(document)
                results[title] = {'total': total, 'spans': [], 'ocr_pages': 0}
                # Image-only books benefit from per-page parallelism; text PDFs
                # are fast enough to process in one task.
                batch = 25 if title.startswith(('闽山闽水物华新', '习近平生态文明思想概论',
                                                '习近平谈治国理政·第一卷')) else total
                for start in range(1, total + 1, batch):
                    stop = min(total + 1, start + batch)
                    work[pool.submit(transcribe_span, str(source), title, start, stop)] = title
            for job in as_completed(work):
                title, start, pages, ocr_pages, body = job.result()
                results[title]['spans'].append((start, pages, body))
                results[title]['ocr_pages'] += ocr_pages
        for title, result in results.items():
            digest = pending[title][1]
            target = CACHE / f'{digest}.md'
            spans = sorted(result['spans'])
            body = f'# {title}\n\n' + '\n'.join(section for _, _, section in spans)
            body = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', body)
            temporary = target.with_suffix('.tmp')
            temporary.write_text(body, encoding='utf-8')
            temporary.replace(target)
            page_count = sum(len(pages) for _, pages, _ in spans)
            print(f'{title}: {page_count}/{result["total"]} searchable pages, '
                  f'{result["ocr_pages"]} OCR pages', flush=True)

    additions = []
    for title, (source, digest) in pending.items():
        text_source = CACHE / f'{digest}.md'
        if not text_source.is_file():
            raise FileNotFoundError(text_source)
        pdf = LIBRARY / 'pdf' / f'{title}.pdf'
        md = LIBRARY / 'literature' / f'{title}.md'
        word = md.with_suffix('.docx')
        pdf.parent.mkdir(parents=True, exist_ok=True)
        md.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, pdf)
        shutil.copy2(text_source, md)
        markdown_to_docx(md, word)
        page_numbers = [int(n) for n in re.findall(r'(?m)^## 第 (\d+) 页$', md.read_text(encoding='utf-8'))]
        source_name = f'{ARCHIVE.relative_to(ROOT).as_posix()}/{source.name}'
        pdf_record = {'id': digest[:20], 'title': title,
                      'path': pdf.relative_to(ROOT).as_posix(), 'category': 'pdf',
                      'sha256': digest, 'bytes': pdf.stat().st_size, 'source': source_name,
                      'searchable': True, 'text_path': md.relative_to(ROOT).as_posix(),
                      'pages': page_numbers}
        md_digest = _sha(md)
        text_record = {'id': md_digest[:20], 'title': title,
                       'path': md.relative_to(ROOT).as_posix(), 'category': 'literature',
                       'sha256': md_digest, 'bytes': md.stat().st_size, 'source': source_name,
                       'searchable': True, 'pages': page_numbers,
                       'download_path': word.relative_to(ROOT).as_posix(),
                       'pdf_id': pdf_record['id']}
        additions.extend((pdf_record, text_record))
    if refresh_titles:
        entries[:] = [item for item in entries if item['title'] not in refresh_titles]
    entries.extend(additions)
    duplicates = _archive_duplicates(folder, entries, catalog.get('duplicates', []))
    catalog.setdefault('duplicates', []).extend(duplicates)
    counts = {}
    for record in entries:
        counts[record['category']] = counts.get(record['category'], 0) + 1
    catalog['counts'] = counts
    catalog['version'] = catalog.get('version', 1) + 1
    if additions or duplicates:
        temporary = CATALOG.with_suffix('.tmp')
        temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(CATALOG)
    return {'new_books': len(additions) // 2 - len(refresh_titles & set(pending)),
            'refreshed_books': len(refresh_titles & set(pending)),
            'recorded_duplicates': len(duplicates), 'counts': counts,
            'skipped_existing': len(BOOKS) - len(additions) // 2}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extracted-root', type=Path, help='Folder already containing the RAR PDFs')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--refresh-title', action='append', choices=sorted(BOOKS.values()),
                        help='Recreate the reading copy for an already imported title')
    args = parser.parse_args()
    if args.extracted_root:
        result = import_books(args.extracted_root, args.workers, set(args.refresh_title or []))
    else:
        with tempfile.TemporaryDirectory(prefix='3820_supplemental_') as tmp:
            folder = _extract(ARCHIVE, Path(tmp))
            result = import_books(folder, args.workers, set(args.refresh_title or []))
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

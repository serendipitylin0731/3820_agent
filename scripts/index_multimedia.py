"""Extract searchable text from archived images, videos and presentations.

Run after organize_library.py. Generated text and embedded videos stay in
knowledge/library/, so a deployed server only needs the finished library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'knowledge' / 'library'
CATALOG = LIBRARY / 'catalog.json'
DERIVED = LIBRARY / 'derived'
PPT_OCR = ROOT / 'knowledge' / 'data' / 'ppt_ocr'
VIDEO_SUFFIXES = {'.mp4', '.mov', '.m4v'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}
DRAWING_NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
SLIDE_NAME = re.compile(r'^ppt/slides/slide(\d+)\.xml$')


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _write_text(item: dict, text: str) -> None:
    target = DERIVED / f"{item['id']}.txt"
    target.write_text(text.strip() + '\n', encoding='utf-8')
    item['text_path'] = _relative(target)


def _ppt_ocr() -> dict[str, dict[int, str]]:
    manifest = PPT_OCR / 'manifest.json'
    if not manifest.is_file():
        return {}
    indexed = {}
    for deck in json.loads(manifest.read_text(encoding='utf-8')).get('decks', []):
        slides = {}
        for slide in deck.get('slides', []):
            path = PPT_OCR / slide['text_file']
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == slide['text_sha256']:
                slides[slide['page']] = path.read_text(encoding='utf-8').strip()
        indexed[deck['source_sha256']] = slides
    return indexed


def _ppt_text(path: Path, title: str, image_text: dict[int, str]) -> str:
    blocks = [f'# {title}']
    with ZipFile(path) as archive:
        slides = sorted(((int(match.group(1)), name) for name in archive.namelist()
                         if (match := SLIDE_NAME.match(name))), key=lambda pair: pair[0])
        for page, name in slides:
            root = ElementTree.fromstring(archive.read(name))
            lines = []
            for paragraph in root.iter(f'{DRAWING_NS}p'):
                line = ''.join(node.text or '' for node in paragraph.iter(f'{DRAWING_NS}t')).strip()
                if line:
                    lines.append(line)
            ocr = image_text.get(page, '')
            if ocr:
                lines.extend(line for line in ocr.splitlines() if line.strip() and
                             line.replace(' ', '') not in ''.join(lines).replace(' ', ''))
            if lines:
                blocks.extend((f'## 第 {page} 页', '\n'.join(lines)))
    return '\n\n'.join(blocks)


def _image_text(item: dict, path: Path, engine=None) -> str:
    source = ROOT / item['source']
    cached = source.with_suffix('.txt') if source.suffix.lower() in IMAGE_SUFFIXES else None
    if cached and cached.is_file():
        body = cached.read_text(encoding='utf-8', errors='replace').strip()
    else:
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR()
        lines, _ = engine(str(path))
        body = '\n'.join(row[1] for row in lines or [] if len(row) > 1 and row[1].strip())
    return f"# {item['title']}\n\n{body}" if body else f"# {item['title']}"


def _embedded_videos(entries: list[dict]) -> list[dict]:
    existing = {item['sha256'] for item in entries}
    videos = []
    for deck in (item for item in entries if item['category'] == 'presentations'):
        with ZipFile(ROOT / deck['path']) as archive:
            media = sorted((info for info in archive.infolist()
                            if info.filename.startswith('ppt/media/') and
                            Path(info.filename).suffix.lower() in VIDEO_SUFFIXES),
                           key=lambda info: info.filename)
            for number, info in enumerate(media, 1):
                payload = archive.read(info)
                digest = hashlib.sha256(payload).hexdigest()
                if digest in existing:
                    continue
                existing.add(digest)
                target = LIBRARY / 'media' / f'embedded_{digest[:20]}{Path(info.filename).suffix.lower()}'
                if not target.is_file():
                    target.write_bytes(payload)
                videos.append({'id': digest[:20], 'title': f"《{deck['title']}》内嵌视频 {number}",
                               'path': _relative(target), 'category': 'media', 'sha256': digest,
                               'bytes': len(payload), 'source': deck['path'],
                               'source_kind': 'embedded_video', 'searchable': True})
    return videos


def _duration(path: Path) -> float:
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'default=nokey=1:noprint_wrappers=1', str(path)],
                            check=True, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def _time(seconds: float) -> str:
    total = int(seconds)
    return f'{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}'


def _video_text(item: dict, path: Path, asr, ocr, frame_interval: int) -> str:
    segments, _ = asr.transcribe(str(path), language='zh', beam_size=2, vad_filter=True,
                                 condition_on_previous_text=False)
    events = []
    previous = ''
    for segment in segments:
        text = segment.text.strip(' ，。,.')
        if len(text) < 3 or text == previous or segment.no_speech_prob > 0.8:
            continue
        events.append((segment.start, f'[音频 {_time(segment.start)}] {text}'))
        previous = text

    import cv2
    capture = cv2.VideoCapture(str(path))
    try:
        last_text = ''
        for second in range(0, int(_duration(path)) + 1, frame_interval):
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            success, frame = capture.read()
            if not success:
                continue
            if frame.shape[1] > 1600:
                frame = cv2.resize(frame, (1600, round(frame.shape[0] * 1600 / frame.shape[1])))
            lines, _ = ocr(frame)
            text = ' '.join(row[1].strip() for row in lines or [] if len(row) > 1 and
                            len(row[1].strip()) >= 2)
            if len(text) >= 6 and text != last_text:
                events.append((second, f'[画面 {_time(second)}] {text}'))
                last_text = text
    finally:
        capture.release()
    events.sort(key=lambda pair: pair[0])
    return f"# {item['title']}\n\n" + '\n'.join(line for _, line in events)


def build(*, model: str = 'base', frame_interval: int = 30) -> dict:
    if not CATALOG.is_file():
        raise FileNotFoundError('请先运行 scripts/organize_library.py')
    DERIVED.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    entries = [item for item in catalog['entries'] if item.get('source_kind') != 'embedded_video']
    entries.extend(_embedded_videos(entries))
    ppt_ocr = _ppt_ocr()
    images = [item for item in entries if item['category'] == 'media' and
              Path(item['path']).suffix.lower() in IMAGE_SUFFIXES]
    presentations = [item for item in entries if item['category'] == 'presentations']
    videos = [item for item in entries if item['category'] == 'media' and
              Path(item['path']).suffix.lower() in VIDEO_SUFFIXES]
    for item in images:
        _write_text(item, _image_text(item, ROOT / item['path']))
        item['searchable'] = True
    for item in presentations:
        _write_text(item, _ppt_text(ROOT / item['path'], item['title'],
                                    ppt_ocr.get(item['sha256'], {})))
        item['searchable'] = False
    if videos:
        from faster_whisper import WhisperModel
        from rapidocr_onnxruntime import RapidOCR
        asr = WhisperModel(model, device='cpu', compute_type='int8', local_files_only=True)
        ocr = RapidOCR()
        for number, item in enumerate(videos, 1):
            print(f"[{number}/{len(videos)}] 视频转写 {item['title']}", flush=True)
            _write_text(item, _video_text(item, ROOT / item['path'], asr, ocr, frame_interval))
            item['searchable'] = True
    entries.sort(key=lambda item: (item['category'], item['title'], item['path']))
    catalog['entries'] = entries
    catalog['counts'] = dict(Counter(item['category'] for item in entries))
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'images': len(images), 'videos': len(videos), 'presentations': len(presentations)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='base', help='本机已缓存的 faster-whisper 模型名称')
    parser.add_argument('--frame-interval', type=int, default=30, help='视频画面 OCR 间隔（秒）')
    options = parser.parse_args()
    print(json.dumps(build(model=options.model, frame_interval=options.frame_interval),
                     ensure_ascii=False), flush=True)

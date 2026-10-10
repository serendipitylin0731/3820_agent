"""保存学习强国原始扫描预览的逐页图像、OCR 文本和来源清单。"""

import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ARTICLE_URL = 'https://article.xuexi.cn/articles/pdf/index.html?art_id=1854475750850039511'
ARTICLE_ID = '1854475750850039511'
OUTPUT = Path(__file__).resolve().parent / 'data' / 'original_3820'
IMAGE_REF = re.compile(rb'I\x00/\x00(?:[0-9]\x00)+')
_OCR = None


def _download(url):
    for attempt in range(4):
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': ARTICLE_URL})
            with urlopen(request, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def _article_info():
    raw = _download(f'https://boot-source.xuexi.cn/data/app/{ARTICLE_ID}.js')
    if not raw.startswith(b'callback(') or not raw.rstrip().endswith(b')'):
        raise ValueError('学习强国文章元数据格式变化')
    data = json.loads(raw[len(b'callback('):].rstrip()[:-1])
    if data.get('title') != '福州市20年经济社会发展战略设想' or not data.get('files'):
        raise ValueError('原始扫描件标题或文件列表不匹配')
    file = data['files'][0]
    return file['url'].removesuffix('/doc/meta.json').removesuffix('/meta.json'), file


def _page_image_url(base, page):
    binary = _download(f'{base}/doc/fp{page}.bin')
    refs = [match.group().decode('utf-16le') for match in IMAGE_REF.finditer(binary)]
    if not refs:
        raise ValueError(f'预览第 {page} 页没有图像引用')
    # 双图层扫描页的第一层是黑色遮罩，末层是包含文字的页面图像。
    return f'{base}/doc/{refs[-1]}'


def _ocr_text(image_path):
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    lines, _ = _OCR(str(image_path))
    if not lines:
        return ''
    from PIL import Image
    with Image.open(image_path) as image:
        width, height = image.size
    # 扫描正文多为双栏。页眉和跨栏标题优先，其后按左栏、右栏读取。
    header, left, right = [], [], []
    for box, content, _confidence in lines:
        xmin = min(point[0] for point in box)
        xmax = max(point[0] for point in box)
        ymin = min(point[1] for point in box)
        record = (ymin, content.strip())
        if ymin < 0.13 * height or xmax - xmin > 0.55 * width:
            header.append(record)
        elif (xmin + xmax) / 2 < width / 2:
            left.append(record)
        else:
            right.append(record)
    groups = [sorted(group) for group in (header, left, right)]
    return '\n'.join(text for group in groups for _, text in group if text).strip()


def _process_page(base, page, output):
    pages = Path(output) / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    image_path = pages / f'page_{page:04d}.png'
    text_path = pages / f'page_{page:04d}.txt'
    if not image_path.is_file():
        image = _download(_page_image_url(base, page))
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(f'预览第 {page} 页不是 PNG 图像')
        image_path.write_bytes(image)
    if not text_path.is_file():
        content = _ocr_text(image_path)
        text_path.write_text(content + '\n' if content else '', encoding='utf-8')
    return {'page': page, 'image_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
            'text_sha256': hashlib.sha256(text_path.read_bytes()).hexdigest(),
            'characters': len(text_path.read_text(encoding='utf-8').strip())}


def fetch_scan(output=OUTPUT, pages=None, workers=2):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base, source_file = _article_info()
    meta = json.loads(_download(f'{base}/doc/meta.json'))
    catalog = json.loads(_download(f'{base}/doc/catalog.json'))
    if meta.get('pc') != 276:
        raise ValueError('原始扫描件页数变化，请人工核对')
    (output / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    page_numbers = list(range(1, 277)) if pages is None else sorted(set(pages))
    if any(page < 1 or page > 276 for page in page_numbers):
        raise ValueError('预览页码必须在 1–276 之间')
    records = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(_process_page, base, page, output): page for page in page_numbers}
        for future in as_completed(pending):
            record = future.result()
            records.append(record)
            print(f"预览第 {record['page']} 页：{record['characters']} 字", flush=True)
    manifest_path = output / 'manifest.json'
    prior = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    by_page = {record['page']: record for record in prior.get('pages', [])}
    by_page.update({record['page']: record for record in records})
    manifest = {'article_url': ARTICLE_URL, 'article_id': ARTICLE_ID,
                'title': '福州市20年经济社会发展战略设想',
                'preview_base_url': base, 'source_filename': source_file['name'],
                'source_size_bytes': source_file['size'], 'preview_pages': meta['pc'],
                'retrieved': date.today().isoformat(), 'ocr_engine': 'rapidocr-onnxruntime 1.4.4',
                'pages': [by_page[page] for page in sorted(by_page)]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, nargs='*', help='只处理指定的预览页码；省略时处理全部 276 页')
    parser.add_argument('--workers', type=int, default=2, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    result = fetch_scan(pages=args.pages, workers=args.workers)
    print(f"已保存 {len(result['pages'])}/{result['preview_pages']} 页")

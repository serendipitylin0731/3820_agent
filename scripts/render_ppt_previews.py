"""Render archived presentations to single-slide WebP previews.

Requires LibreOffice Impress on the build machine and PyMuPDF in the Python
environment.  The web server only needs the generated slide_previews folder.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'knowledge' / 'library' / 'catalog.json'
OUTPUT = ROOT / 'knowledge' / 'library' / 'slide_previews'


def render(*, libreoffice: str = 'libreoffice', width: int = 1440) -> dict[str, int]:
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    rendered = {}
    with tempfile.TemporaryDirectory(prefix='3820-slides-') as temporary:
        temp = Path(temporary)
        for item in catalog['entries']:
            if item['category'] != 'presentations':
                continue
            source = ROOT / item['path']
            # A dedicated profile avoids collisions with an open LibreOffice session.
            profile = (temp / f"profile-{item['id']}").as_uri()
            result = subprocess.run(
                [libreoffice, f'-env:UserInstallation={profile}', '--headless',
                 '--convert-to', 'pdf:impress_pdf_Export', '--outdir', str(temp), str(source)],
                capture_output=True, text=True, timeout=300, check=False,
            )
            pdf = temp / f'{source.stem}.pdf'
            if result.returncode != 0 or not pdf.is_file():
                raise RuntimeError(f'PPT 转换失败：{source.name}: {result.stderr or result.stdout}')
            destination = OUTPUT / item['id']
            destination.mkdir(parents=True, exist_ok=True)
            document = pymupdf.open(pdf)
            try:
                for number, page in enumerate(document, 1):
                    scale = width / page.rect.width
                    pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    image = Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples)
                    image.save(destination / f'slide_{number:04d}.webp', 'WEBP', quality=85, method=4)
                count = len(document)
            finally:
                document.close()
                pdf.unlink()
            item['preview_dir'] = destination.relative_to(ROOT).as_posix()
            item['preview_page_count'] = count
            rendered[item['title']] = count
            print(f'{item["title"]}: {count} 页', flush=True)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return rendered


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--libreoffice', default='libreoffice')
    parser.add_argument('--width', type=int, default=1440)
    options = parser.parse_args()
    if options.width < 640 or options.width > 2560:
        parser.error('width must be between 640 and 2560')
    print(json.dumps(render(libreoffice=options.libreoffice, width=options.width), ensure_ascii=False))

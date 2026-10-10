"""下载获准公开访问的网页资料，保留原文、提取文本和来源元数据。"""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html

OUTPUT = Path(__file__).resolve().parent / 'data' / 'public_sources'

# 1992 年《福州市20年经济社会发展战略设想》全文未找到公开可信版本。
# 这里的解读、采访和节选不能标作该原件。
SOURCES = (
    ('3820_fuzhou_explainer', 'official_interpretation',
     'https://www.fuzhou.gov.cn/gzdt/rcyw/202205/t20220519_4364544.htm', '//*[@id="detailCont"]'),
    ('fuzhou_interview_14', 'book_serialized_interview',
     'https://www.fuzhou.gov.cn/zfxxgkzl/sjcj/zz/xjpzfz/xjpzfzcfsl/202012/t20201203_3698098.htm',
     '//*[contains(@class,"TRS_Editor")]'),
    ('fuzhou_interview_18', 'book_serialized_interview',
     'https://jcj.fuzhou.gov.cn/zz/xjpzfz/zxbd_49574/202001/t20200120_3185437.htm',
     '//*[contains(@class,"TRS_Editor")]'),
    ('fujian_interview_28', 'book_serialized_interview',
     'https://jcj.fuzhou.gov.cn/zz/xjpzfz/xjpzfjcfsl/202012/t20201221_3881801.htm',
     '//*[contains(@class,"TRS_Editor")]'),
    ('fujian_footprints_excerpt', 'book_excerpt',
     'https://mksxy.fzgsxy.com/index.php?a=show&c=index&catid=513&id=111&m=content',
     '//*[contains(@class,"v_news_content")]'),
    ('twentieth_congress_report', 'authorized_full_report',
     'https://www.news.cn/politics/leaders/2022-10/25/c_1129079429.htm', '//*[@id="detail"]'),
)


def fetch_all(directory=OUTPUT, *, refresh=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name, kind, url, xpath in SOURCES:
        html_path = directory / f'{name}.html'
        if refresh or not html_path.is_file():
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(request, timeout=30) as response:
                payload = response.read()
            html_path.write_bytes(payload)
        else:
            payload = html_path.read_bytes()
        page = html.fromstring(payload.decode('utf-8', errors='replace'))
        candidates = page.xpath(xpath)
        if not candidates:
            raise ValueError(f'{name}：网页结构变化，找不到正文')
        article = max(candidates, key=lambda node: len(''.join(node.itertext())))
        for node in article.xpath('.//script|.//style|.//nav'):
            node.getparent().remove(node)
        paragraphs = []
        for node in article.xpath('.//p|.//h1|.//h2|.//h3'):
            line = ' '.join(''.join(node.itertext()).split())
            if line and (not paragraphs or line != paragraphs[-1]):
                paragraphs.append(line)
        content = '\n\n'.join(paragraphs) if paragraphs else ' '.join(''.join(article.itertext()).split())
        if len(content) < 600:
            raise ValueError(f'{name}：提取文本过短，请检查网页')
        text_payload = (content + '\n').encode('utf-8')
        (directory / f'{name}.txt').write_bytes(text_payload)
        records.append({
            'id': name, 'url': url, 'kind': kind, 'retrieved': date.today().isoformat(),
            'title': ' '.join(page.xpath('string(//title)').split()),
            'html_sha256': hashlib.sha256(payload).hexdigest(),
            'text_sha256': hashlib.sha256(text_payload).hexdigest(),
            'characters': len(content),
            'note': '非1992年《战略设想》原件' if name == '3820_fuzhou_explainer' else '',
        })
    (directory / 'manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n',
                                             encoding='utf-8')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='重新下载网页，而非复用本地原文')
    args = parser.parse_args()
    for record in fetch_all(refresh=args.refresh):
        print(record['id'], record['characters'])

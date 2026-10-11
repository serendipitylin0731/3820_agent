"""Direct, cited passages for recurring questions the semantic search may miss."""

import hashlib
import re
from pathlib import Path

from contracts import KnowledgeHit, SourceRef


BACKGROUND = Path(__file__).resolve().parents[1] / 'docs' / '3820背景.md'
SECTIONS = {
    '03 三步目标': (
        'https://www.fuzhou.gov.cn/gzdt/rcyw/202205/t20220519_4364544.htm',
        '3820 战略工程三阶段目标',
    ),
    '04 江海布局': (
        'https://article.xuexi.cn/articles/pdf/index.html?art_id=1854475750850039511',
        '预览第40页：战略布局',
    ),
}


def _section(title: str) -> str:
    document = BACKGROUND.read_text(encoding='utf-8')
    match = re.search(rf'(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)', document)
    if not match:
        raise ValueError(f'背景文档缺少 {title}')
    return match.group(1).split('\n来源：', 1)[0].strip()


def direct_hits(question: str) -> list[KnowledgeHit]:
    sections = []
    if any(term in question for term in ('三个阶段', '三阶段', '各阶段', '三步目标',
                                        '第一阶段', '第二阶段', '第三阶段')):
        sections.append('03 三步目标')
    if ('福州经济技术开发区' in question and '老市区' in question) or (
            '战略布局' in question and any(term in question for term in ('闽江口', '开发区'))):
        sections.append('04 江海布局')
    version = hashlib.sha256(BACKGROUND.read_bytes()).hexdigest()[:16]
    return [KnowledgeHit(
        chunk_id=f'background:{title}', content=_section(title),
        source=SourceRef(source_file=SECTIONS[title][0], section=SECTIONS[title][1],
                         page_or_slide=None, data_version=version, verified=True),
        score=1.0, score_kind='similarity',
    ) for title in sections]

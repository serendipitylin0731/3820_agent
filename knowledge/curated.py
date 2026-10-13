"""The reviewed background guide is the first retrieval tier for broad 3820 questions.

Original OCR and interviews remain searchable, but their noisy snippets must not crowd
out a concise section that already answers the question with explicit provenance.
"""

import hashlib
import json
import re
from pathlib import Path

from contracts import KnowledgeHit, SourceRef


BACKGROUND = Path(__file__).resolve().parents[1] / 'docs' / '3820背景.md'
JIANG_HAI_TERMS = ('沿江向海', '东进南下')
OVERVIEW_CUES = ('具体内容', '主要内容', '核心内容', '总体内容', '整体内容',
                 '有什么内容', '哪些内容', '包含什么', '包含哪些',
                 '包括什么', '包括哪些', '有哪些方面', '讲了什么',
                 '讲的是什么', '讲了哪些', '核心安排', '主要安排',
                 '主要做什么', '是做什么的', '概述', '概况', '简介',
                 '介绍一下')
OVERVIEW_SECTIONS = ('02 规划如何形成', '03 三步目标', '04 江海布局',
                     '05 重点工程', '06 城市与生活')
SECTIONS = {
    '01 起点与问题': ('https://slj.fuzhou.gov.cn/zwgk/ztxx/djgz/3820zlgcsxjs/202402/t20240219_4778720.htm', '背景导读·01 起点与问题'),
    '02 规划如何形成': ('https://zygh.fuzhou.gov.cn/zwgk/ztzl/xjpxsdzgtsshzysxxxzt/202105/t20210511_4096820.htm', '背景导读·02 规划如何形成'),
    '03 三步目标': ('https://www.fuzhou.gov.cn/gzdt/rcyw/202205/t20220519_4364544.htm', '3820 战略工程三阶段目标'),
    '04 江海布局': ('knowledge/library/media/原件扫描_page_0040.png', '预览第40页：战略布局'),
    '05 重点工程': ('docs/3820背景.md', '背景导读·05 重点工程'),
    '06 城市与生活': ('https://slj.fuzhou.gov.cn/zwgk/ztxx/djgz/3820zlgcsxjs/202402/t20240219_4778720.htm', '背景导读·06 城市与生活'),
    '07 阶段回看': ('https://slj.fuzhou.gov.cn/zwgk/ztxx/djgz/3820zlgcsxjs/202402/t20240219_4778720.htm', '背景导读·07 阶段回看'),
    '08 原始规划与后来的理论视角': ('docs/3820背景.md', '背景导读·08 史料与理论视角'),
    '09 指标名称与统计口径': ('https://www.stats.gov.cn/zs/tjws/tjzb/202301/t20230101_1903832.html', '背景导读·09 指标与口径'),
}

# Topic cues identify the evidence needed, rather than individual expected questions.
TOPIC_CUES = (
    ('09 指标名称与统计口径', ('GDP和GNP', 'GDP与GNP', 'GDP、GNP', '指标口径', '目标值与完成值', '目标与完成值')),
    ('08 原始规划与后来的理论视角', ('理论', '思想', '马克思', '新时代', '新发展理念', '人民至上', '视角', '原始依据', '原文', '史料', '后来', '后续表述', '启示')),
    ('07 阶段回看', ('成效', '达成', '完成情况', '实现了吗', '回顾', '第一阶段实现', '发展成果')),
    ('01 起点与问题', ('为什么制定', '为何制定', '为什么需要', '为何需要', '为什么要搞', '为何要搞', '长期规划', '背景', '起点', '发展问题', '南方谈话', '发展条件')),
    ('02 规划如何形成', ('调查', '调研', '问卷', '论证', '形成', '编制', '制定', '历时', '审议通过', '三个数字', '数字', '跨度', '3、8、20', '3/8/20', '分别代表', '提出的过程', '算起', '起算')),
    ('03 三步目标', ('阶段', '目标', '三个时期', '三年', '八年', '二十年', '3年', '8年', '20年', '三步', '分几步', '1995', '2000', '2010', '翻一番', '小康', '完成值')),
    ('04 江海布局', ('布局', '空间', '闽江口', '金三角', '沿江', '向海', '东进', '南下', '开发区', '老市区', '老城区', '南北两翼', '沿海县', '山区县', '后卫', '腹地', '福马线', '福厦线', '闽江流域', '港口')),
    ('05 重点工程', ('机场', '通航', '海上福州', '招商', '侨资', '侨商', '以侨引侨', '园区为基', '海洋经济', '重点工程', '重点项目', '具体项目', '核心举措', '主要举措', '实施措施', '实现路径', '产业项目', '防洪')),
    ('06 城市与生活', ('民生', '百姓', '人民生活', '菜篮子', '苍霞', '生态', '环保', '环境', '内河', '文化保护', '生活环境')),
)


def _section(title: str) -> str:
    document = BACKGROUND.read_text(encoding='utf-8')
    match = re.search(rf'(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)', document)
    if not match:
        raise ValueError(f'背景文档缺少 {title}')
    return match.group(1).split('\n来源：', 1)[0].strip()


def section_titles(question: str) -> list[str]:
    """Select reviewed source sections for the topic, with no fuzzy OCR match."""
    query = question.strip()
    if (any(cue in query for cue in OVERVIEW_CUES) and
            any(cue in query for cue in ('3820', '战略工程', '二十年发展战略')) and
            not re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)', query)):
        return list(OVERVIEW_SECTIONS)
    titles = [title for title, cues in TOPIC_CUES if any(cue in query for cue in cues)]
    if (any(term in query for term in ('为什么', '为何')) and
            any(term in query for term in ('制定', '提出', '形成')) and
            '01 起点与问题' not in titles):
        titles.insert(0, '01 起点与问题')
    if '01 起点与问题' in titles and '02 规划如何形成' in titles and '目标' not in query:
        titles = [title for title in titles if title != '03 三步目标']
    if '09 指标名称与统计口径' in titles and not re.search(r'(?:19|20)\d{2}', query):
        titles = [title for title in titles if title != '03 三步目标']
    if any(term in query for term in ('3820', '20年经济社会发展战略', '二十年发展战略')):
        if not titles and any(term in query for term in ('是什么', '什么是', '含义', '概况', '简介', '介绍')):
            titles = ['02 规划如何形成', '03 三步目标']
        elif any(term in query for term in ('是什么', '什么是', '三个数字', '3、8、20', '3/8/20', '分别代表')):
            for title in ('02 规划如何形成', '03 三步目标'):
                if title not in titles:
                    titles.append(title)
    if '海上福州' in query and '04 江海布局' not in titles:
        titles.append('04 江海布局')
    if any(term in query for term in ('福州经济技术开发区', '老市区', '老城区')) and '04 江海布局' not in titles:
        titles.append('04 江海布局')
    # Dates and project phases outside the selected source must be answered as
    # unsupported, instead of being inferred from a nearby planning passage.
    combined = '\n'.join(_section(title) for title in titles)
    years = re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', query)
    if any(year not in combined for year in years):
        return []
    if '二期' in query and '二期' not in combined:
        return []
    return titles[:3]


def direct_hits(question: str) -> list[KnowledgeHit]:
    if '示意图' in question and any(term in question for term in ('闽江口', '金三角', '投资')):
        map_data = json.loads((BACKGROUND.parents[1] / 'knowledge' / 'map_labels.json').read_text(encoding='utf-8'))
        return [KnowledgeHit(
            chunk_id='reviewed:investment_map',
            content=f"{map_data['title']}：" + '、'.join(map_data['labels']) + '。',
            source=SourceRef.model_validate(map_data['source_ref']),
            score=1.0, score_kind='similarity',
        )]
    version = hashlib.sha256(BACKGROUND.read_bytes()).hexdigest()[:16]
    hits = [KnowledgeHit(
        chunk_id=f'background:{title}', content=_section(title),
        source=SourceRef(source_file=SECTIONS[title][0], section=SECTIONS[title][1],
                         page_or_slide=None, data_version=version, verified=True),
        score=1.0, score_kind='similarity',
    ) for title in section_titles(question)]
    if ('闽江口金三角' in question and
            any(term in question for term in ('涉及', '哪些区域', '范围', '分布', '包括'))):
        map_data = json.loads((BACKGROUND.parents[1] / 'knowledge' / 'map_labels.json').read_text(encoding='utf-8'))
        hits.append(KnowledgeHit(
            chunk_id='reviewed:investment_map',
            content=f"{map_data['title']}：" + '、'.join(map_data['labels']) + '。',
            source=SourceRef.model_validate(map_data['source_ref']),
            score=1.0, score_kind='similarity',
        ))
    return hits


def source_sections(question: str) -> list[str]:
    sections = [SECTIONS[title][1] for title in section_titles(question)]
    if ('闽江口金三角' in question and
            any(term in question for term in ('涉及', '哪些区域', '范围', '分布', '包括'))):
        sections.append('福州市闽江口金三角经济圈投资示意图')
    return sections


def answer_passage(question: str) -> str | None:
    """Use the reviewed prose as an offline, source-backed answer outline."""
    titles = section_titles(question)
    if not titles:
        return None
    if titles == list(OVERVIEW_SECTIONS):
        formation = _section('02 规划如何形成').split('\n\n')
        stages = _section('03 三步目标').split('\n\n')
        layout = _section('04 江海布局').split('\n\n')
        projects = _section('05 重点工程').split('\n\n')
        livelihood = _section('06 城市与生活').split('\n\n')
        selected = [
            '“3820”战略工程以三年、八年、二十年为规划跨度，把阶段目标、江海布局、重点工程和民生安排纳入福州长期发展蓝图。',
            '规划形成：' + formation[0],
            '阶段目标：' + ' '.join(item.replace('**', '') for item in stages[:3]),
            '空间布局：' + layout[0],
            '重点工程：' + projects[0],
            '民生与城市生活：' + livelihood[0],
        ]
        return '\n\n'.join(selected)[:2600]
    passages = []
    for title in titles:
        paragraphs = [paragraph.strip() for paragraph in _section(title).split('\n\n') if paragraph.strip()]
        if not paragraphs:
            continue
        if title.startswith('05'):
            if any(term in question for term in ('核心举措', '主要举措', '实施措施', '实现路径')):
                passage = '\n\n'.join((paragraphs[0], paragraphs[-1]))
                passages.append(re.sub(r'\*\*(.*?)\*\*', r'\1', passage))
                continue
            subjects = [term for term in ('机场', '海上福州', '招商', '侨资', '侨商', '港口', '产业')
                        if term in question]
            selected = [paragraph for paragraph in paragraphs if paragraph.startswith('**')
                        and any(subject in paragraph for subject in subjects)]
            if not selected:
                selected = [paragraph for paragraph in paragraphs if any(subject in paragraph for subject in subjects)]
            if any(term in question for term in ('侨资', '侨商', '以侨引侨')):
                selected.extend(paragraph for paragraph in paragraphs if '项目指南依据收录材料' in paragraph)
            passage = '\n\n'.join(dict.fromkeys(selected[:3] or paragraphs[:2]))
        elif title.startswith('03'):
            years = [year for year in ('1995', '2000', '2010') if year in question]
            selected = [paragraph for paragraph in paragraphs if any(year in paragraph for year in years)]
            passage = '\n\n'.join(selected[:2] if years and selected else paragraphs[:3])
        elif title.startswith('07') and any(term in question for term in ('达成', '评估', '完成')):
            passage = paragraphs[-1]
        elif title.startswith('02') and any(term in question for term in ('数字', '跨度', '算起', '起算', '3、8、20', '3/8/20', '分别代表', '是什么', '什么是')):
            passage = paragraphs[-1] if any(term in question for term in ('数字', '跨度', '算起', '起算', '3、8、20', '3/8/20', '分别代表')) else '\n\n'.join((paragraphs[1], paragraphs[-1]))
        elif title.startswith('02') and any(term in question for term in ('调查', '调研', '问卷', '论证')):
            passage = paragraphs[0]
        elif title.startswith('08') and any(term in question for term in ('马克思', '新时代', '新发展理念', '人民至上')) and not any(
                term in question for term in ('区分', '原文', '原始')):
            passage = paragraphs[1]
            if '马克思' in question and not any(term in question for term in ('新时代', '新发展理念')):
                passage = passage.split('。', 1)[0] + '。'
        else:
            passage = '\n\n'.join(paragraphs[:2])
        passages.append(re.sub(r'\*\*(.*?)\*\*', r'\1', passage))
    if ('闽江口金三角' in question and
            any(term in question for term in ('涉及', '哪些区域', '范围', '分布', '包括'))):
        map_data = json.loads((BACKGROUND.parents[1] / 'knowledge' / 'map_labels.json').read_text(encoding='utf-8'))
        passages.append('原件投资示意图标注的区域和投资区包括：' + '、'.join(map_data['labels']) + '。')
    if any(term in question for term in ('什么是3820', '3820工程是什么', '3820战略工程是什么')):
        introduction = BACKGROUND.read_text(encoding='utf-8').split('## 01', 1)[0].split('\n\n', 1)[-1].strip()
        passages.insert(0, introduction)
    return '\n\n'.join(passages)[:2200] or None

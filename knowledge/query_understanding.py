"""Turn short, colloquial and follow-up questions into standalone search questions.

The returned text is an internal query. It never becomes evidence: facts still have to
come from the document and indicator paths later in the graph.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata

from config import get_settings
from llm_client import chat

logger = logging.getLogger('3820_agent')

PROJECT = '3820战略工程'
TOPIC_QUESTIONS = {
    'overview': f'{PROJECT}的主要内容是什么？',
    'stages': f'{PROJECT}的三个阶段目标是什么？',
    'formation': f'{PROJECT}是怎样通过调查研究形成的？',
    'layout': f'{PROJECT}的战略布局是什么？',
    'projects': f'{PROJECT}有哪些重点工程和实施措施？',
    'livelihood': f'{PROJECT}在民生和城市生活方面有哪些安排？',
    'outcomes': f'{PROJECT}的实施成效如何？',
    'theory': f'{PROJECT}与后来的理论视角有什么关系？',
}
STAGE_CUE = re.compile(r'三(?:个|大)?阶段|三步(?:走|目标)?|三个时期|阶段划分|第[一二三123]阶段|分几步|(?<!\d)3[、,/· ]+8[、,/· ]+20(?!\d)')
OVERVIEW_CUE = re.compile(r'具体内容|主要内容|核心内容|总体内容|整体内容|有什么内容|哪些内容|包含什么|包含哪些|包括什么|包括哪些|有哪些方面|讲了什么|讲的是什么|讲了哪些|核心安排|主要安排|主要做什么|是做什么的|概述|概况|简介|介绍一下')
FOLLOWUP_CUE = re.compile(r'^(?:那|那么|然后|还有|接着|继续|这个|该|它|其|前者|后者|相比|和第|与第|至于|关于)')
YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')
ENTITY_TERMS = ('长乐国际机场', '福州经济技术开发区', '闽江口金三角经济圈', '海上福州',
                '老市区', '苍霞', '马尾', PROJECT, '福州')
PROJECT_CUES = ('3820', '福州', '闽江口', '长乐', '马尾', '苍霞', '海上福州', '金三角经济圈')


def _clean(question: str) -> str:
    text = unicodedata.normalize('NFKC', question).strip()
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('三八二零', '3820').replace('三八二〇', '3820')
    # A frequent input-method/voice typo seen in phase questions.
    text = text.replace('三个结算', '三个阶段').replace('三大结算', '三个阶段')
    text = text.replace('三步结算', '三个阶段')
    return text


def _is_elliptical(question: str) -> bool:
    return bool(FOLLOWUP_CUE.search(question) or
                len(question) <= 18 and question.rstrip('？?。').endswith('呢'))


def _subject_from_previous(previous: str) -> str:
    return next((term for term in ENTITY_TERMS if term in previous), PROJECT)


def _followup(question: str, previous: str) -> str | None:
    if not previous or not _is_elliptical(question):
        return None
    # A new explicit subject takes priority over conversation memory.
    if any(term in question for term in PROJECT_CUES) and not re.search(r'^(?:那|那么)?(?:它|这个|该)', question):
        return None
    core = re.sub(r'^(?:那|那么|然后|接着|至于|关于)\s*', '', question).strip()
    core = re.sub(r'[呢？?。]+$', '', core).strip()
    if not core:
        return None
    comparison = re.search(r'和第[一二三123]阶段相比', core)
    earlier = re.search(r'第[一二三123]阶段', previous)
    if comparison and earlier:
        return f'{PROJECT}的{earlier.group()}{core}？'
    duration = next(((name, ordinal) for name, ordinal in
                     (('二十年', '第三'), ('八年', '第二'), ('三年', '第一'))
                     if name in core and '阶段' in core), None)
    if duration:
        return f'{PROJECT}的{duration[1]}阶段目标是什么？'
    if STAGE_CUE.search(core):
        ordinal = re.search(r'第[一二三123]阶段', core)
        if ordinal:
            if '上一阶段' in core:
                return f'{PROJECT}的{ordinal.group()}与上一阶段有什么区别？'
            return f'{PROJECT}的{ordinal.group()}目标是什么？' if core == ordinal.group() else f'{PROJECT}的{core}？'
        return f'{PROJECT}的{core}是什么？'
    if '上一阶段' in core:
        earlier = re.search(r'第[一二三123]阶段', previous)
        if earlier:
            return f'{PROJECT}的{earlier.group()}与上一阶段有什么区别？'
    previous_years = YEAR.findall(previous)
    current_years = YEAR.findall(core)
    if len(current_years) == 1 and len(previous_years) == 1 and len(core) <= 12:
        return YEAR.sub(current_years[0], previous, count=1)
    if (not current_years and len(previous_years) == 1 and
            re.search(r'GDP|GNP|地区生产总值|国民生产总值|人均收入|工业总产值', core, re.I) and
            len(core) <= 18):
        qualifier = '目标' if '目标' in previous and '目标' not in core else ''
        return f'{previous_years[0]}年{core}{qualifier}？'
    if len(previous_years) == 1 and any(term in core for term in ('这个目标', '该目标', '目标实现', '目标达成')):
        core = core.replace('这个目标', f'{previous_years[0]}年目标').replace('该目标', f'{previous_years[0]}年目标')
    subject = _subject_from_previous(previous)
    core = re.sub(r'^(?:这个|该|它|其)(?:工程|规划|战略)?', '', core).strip()
    if not core:
        return None
    if subject == PROJECT:
        connector = '' if core.startswith(('是', '有', '和', '为什么', '怎么', '如何')) else '的'
        return f'{PROJECT}{connector}{core}？'
    if core.startswith(('和3820', '与3820')):
        return f'{subject}{core}？'
    return f'{subject}在{PROJECT}中{core}？'


def _model_topic(question: str, previous: str, settings) -> str | None:
    if not (settings.ark_api_key and settings.llm_model and len(question) <= 80):
        return None
    try:
        response = chat([
            {'role': 'system', 'content': (
                '只识别提问意图，不回答问题。当前应用主题是福州3820战略工程。'
                '输出严格JSON对象，唯一字段topic，值只能是overview、stages、formation、layout、'
                'projects、livelihood、outcomes、theory、other之一。'
                '若问题与该工程无关，选other；不要根据上一问覆盖新问题的明确主题。')},
            {'role': 'user', 'content': json.dumps({'previous_question': previous[:180],
                                                   'question': question}, ensure_ascii=False)},
        ], temperature=0, settings=settings).strip()
        if response.startswith('```'):
            response = re.sub(r'^```(?:json)?\s*|\s*```$', '', response, flags=re.I)
        topic = json.loads(response).get('topic')
        return topic if topic in TOPIC_QUESTIONS else None
    except Exception as exc:
        logger.info('问题意图分类回退到本地规则 error_type=%s', type(exc).__name__)
        return None


def resolve_question(question: str, previous_question: str = '', *, settings=None) -> str:
    """Resolve a question using only the same thread's preceding question."""
    current = _clean(question)
    previous = _clean(previous_question)
    if not current:
        return current
    resolved = _followup(current, previous)
    if resolved:
        return resolved
    if not any(cue in current for cue in PROJECT_CUES) and (
            STAGE_CUE.search(current) or OVERVIEW_CUE.search(current) or
            any(term in current for term in ('这项工程', '这个工程', '这个规划', '这份规划',
                                             '这个战略', '该战略', '这项战略', '这套计划',
                                             '这个策略', '主要目标', '核心举措', '重点项目',
                                             '长期规划')) or
            re.search(r'(?:1995|2000|2010)年目标', current)):
        bare = re.sub(r'^(?:这项工程|这个工程|这个规划|这份规划|这个战略工程|这个战略|该战略|这项战略|这套计划|这个策略)', '', current).strip()
        connector = '' if bare.startswith(('是', '有', '包括', '包含', '怎么', '为什么', '为何')) else '的'
        current = f'{PROJECT}{connector}{bare}'
    # The reviewed material has an explicit chapter for these common questions.
    from knowledge.curated import section_titles
    if section_titles(current) or any(term in current.upper() for term in ('GDP', 'GNP')):
        return current
    # A topic label is deliberately broad; keep explicit dates, metrics and named
    # places intact so classification cannot turn a specific question into a
    # generic one with apparently matching sources.
    if (YEAR.search(current) or re.search(r'\d+|GDP|GNP|多少|哪一年|哪年|何时',
                                         current.replace('3820', ''), re.I)
            or any(term in current for term in ENTITY_TERMS[:-2])):
        return current
    topic = _model_topic(current, previous, settings or get_settings())
    if topic:
        return TOPIC_QUESTIONS[topic]
    return current

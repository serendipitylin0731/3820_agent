"""问题拆分与可追溯汇总。"""
import json
import logging
import re

from pydantic import ValidationError
from config import ConfigurationError, get_settings
from contracts import SubTask
from knowledge.curated import JIANG_HAI_TERMS, OVERVIEW_CUES, cangxia_case
from llm_client import chat

SPLIT_SYSTEM = '''将问题拆成 JSON 数组。每个对象必须包含 type 和 question，question 是对应子问题；禁止使用 content 字段。type 仅为 planning、indicator、spatial、evaluation。
indicator 必须有 key，可用 gdp、gdp_per_capita、gnp、gnp_per_capita、industry_primary、industry_secondary、industry_tertiary、gross_ia、agriculture_output、industry_output、export_total、urban_income、rural_income；spatial 必须有 keyword，仅用于查询具体空间要素。询问战略空间布局、规划或作用等概括性问题时使用 planning。只输出 JSON，不要 Markdown 围栏。'''
logger = logging.getLogger('3820_agent')
KEYWORDS = [('gdp_per_capita','人均地区生产总值'),('gdp_per_capita','人均GDP'),
            ('gnp_per_capita','人均收入总值'),('gnp_per_capita','人均国民生产总值'),('gnp_per_capita','人均GNP'),
            ('urban_income','城镇居民人均可支配收入'),('rural_income','农村居民人均纯收入'),
            ('gross_ia','工农业总产值'),('industry_output','工业总产值'),
            ('agriculture_output','农业总产值'),('urban_income','城镇收入'),
            ('rural_income','农村收入'),('gdp','地区生产总值'),('gnp','地区收入总值'),('gnp','国民生产总值'),
            ('gdp','GDP'),('gnp','GNP'),('export_total','出口'),
            ('industry_primary','第一产业'),('industry_secondary','第二产业'),
            ('industry_tertiary','第三产业')]


def _local_split(question):
    tasks = []
    years = sorted({int(y) for y in re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', question)})
    growth = (any(term in question for term in ('增长率', '增幅', '涨幅', '增长了多少', '增长多少'))
              or '增长' in question and any(term in question for term in ('百分之几', '百分比')))
    if any(term in question for term in ('三次产业结构', '三大产业结构', '三次产业构成')):
        tasks.extend({'type': 'indicator', 'question': question, 'key': key, 'years': years or None}
                     for key in ('industry_primary', 'industry_secondary', 'industry_tertiary'))
    if (any(term in question for term in ('评估', '达成率', '翻一番', '完成率',
                                         '实现了吗', '实现没有', '完成了吗', '兑现了吗'))):
        tasks.append({'type':'evaluation','question':question})
    remaining = question
    found = set()
    for key, label in KEYWORDS:
        if label.lower() in remaining.lower() and key not in found:
            tasks.append({'type':'indicator','question':question,'key':key,'years':years or None,
                          'growth':growth})
            found.add(key)
            remaining = re.sub(re.escape(label), '', remaining, count=1, flags=re.IGNORECASE)
    if any(word in question for word in ('空间','港口','机场','园区','元洪','苍霞','侨商','博览会')) and not ('布局' in question and '战略' in question):
        match = next((w for w in ('元洪','苍霞','港口','机场','园区','侨商','博览会') if w in question), '空间')
        tasks.append({'type':'spatial','question':question,'keyword':match})
    if not tasks or any(w in question for w in ('规划','路径','背景','战略')):
        tasks.append({'type':'planning','question':question})
    return tasks


def _normalize_tasks(tasks, question):
    """对模型拆分做领域校验，防止无关问题被误映射为某项指标。"""
    if cangxia_case(question):
        return [{'type': 'planning', 'question': question}]
    # The economic circle is a strategic layout, not a single spatial feature.
    # Model-generated spatial lookups for broad area questions otherwise fail and
    # turn an otherwise complete answer into a misleading partial response.
    if ('闽江口金三角' in question and
            any(term in question for term in ('为什么', '为何', '涉及', '哪些区域', '范围', '布局', '建设')) and
            not any(label.lower() in question.lower() for _, label in KEYWORDS)):
        return [{'type': 'planning', 'question': question}]
    if (any(task['type'] == 'spatial' for task in tasks) and not any(
            term in question for term in ('3820', '福州', '闽江', '机场', '港口',
                                         '园区', '马尾', '苍霞', '元洪', '福清',
                                         '罗源', '平潭', '空间', '布局', '地图'))):
        tasks = [task for task in tasks if task['type'] != 'spatial']
        tasks.append({'type': 'planning', 'question': question})
    if ('3820' in question and any(cue in question for cue in OVERVIEW_CUES) and
            not re.search(r'(?:19|20)\d{2}|GDP|GNP|多少', question, re.I)):
        return [{'type': 'planning', 'question': question}]
    if ('3820' in question and
            re.search(r'三个阶段|三个时期|三阶段|三步目标|第[一二三123]阶段|分几步', question) and
            not any(label.lower() in question.lower() for _, label in KEYWORDS)):
        return [{'type': 'planning', 'question': question}]
    if ('GDP' in question.upper() and 'GNP' in question.upper() and
            not re.search(r'(?:19|20)\d{2}', question) and '目标' not in question and
            any(term in question for term in ('区别', '差别', '概念', '定义'))):
        return [{'type': 'planning', 'question': question}]
    local_indicators = [task for task in _local_split(question) if task['type'] == 'indicator']
    tasks = [task for task in tasks if task['type'] != 'indicator']
    conceptual = any(cue in question for cue in ('为什么要区分', '如何区分', '怎样区分'))
    evaluating = not conceptual and (any(cue in question for cue in
                                         ('评估', '达成率', '完成率', '翻一番', '判定',
                                          '实现了吗', '实现没有', '完成了吗', '兑现了吗'))
                                     or bool(re.search(r'(?:是否|能否|有没有)[^？?。]*达成|目标[^？?。]*达成',
                                                       question)))
    if not evaluating:
        tasks = [task for task in tasks if task['type'] != 'evaluation']
    target_only = '目标' in question and not evaluating and '实际' not in question
    if target_only:
        if local_indicators:
            tasks = [{**task, 'target': True, 'growth': False} for task in local_indicators]
        elif not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    else:
        tasks.extend(local_indicators)
    if evaluating:
        if not any(task['type'] == 'evaluation' for task in tasks):
            tasks.insert(0, {'type': 'evaluation', 'question': question})
        if '目标' in question and not local_indicators and not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if '布局' in question and '战略' in question:
        from knowledge.domain import spatial_features
        if not any(item['name'] in question for item in spatial_features()):
            tasks = [{**task, 'type': 'planning', 'keyword': None, 'stype': None}
                     if task['type'] == 'spatial' else task for task in tasks]
    if any(term in question for term in ('示意图', '地图', '幻灯片', 'PPT', '图片')):
        tasks = [{**task, 'type': 'planning', 'keyword': None, 'stype': None}
                 if task['type'] == 'spatial' else task for task in tasks]
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if '机场' in question and not any(term in question for term in ('在哪里', '位置', '位于', '空间')):
        tasks = [task for task in tasks if task['type'] != 'spatial']
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if any(term in question for term in ('何时', '什么时候', '哪一年', '哪年', '开工', '建成', '完工', '通航')):
        if any(task['type'] == 'spatial' for task in tasks):
            tasks = [task for task in tasks if task['type'] != 'spatial']
            if not any(task['type'] == 'planning' for task in tasks):
                tasks.append({'type': 'planning', 'question': question})
    from knowledge.domain import spatial_features
    named = [item['name'] for item in spatial_features()
             if item['name'] in question and item['name'] not in {'港口与对外通道', '开发区与园区'}]
    if named and not any(term in question for term in ('何时', '什么时候', '哪年', '开工', '建成', '完工', '通航',
                                                        '规划', '战略布局', '地图', '示意图')):
        tasks = [task for task in tasks if task['type'] not in {'planning', 'spatial'}]
        tasks.append({'type': 'spatial', 'question': question, 'keyword': named[0]})
    if '福州经济技术开发区' in question and '老市区' in question:
        tasks = [task for task in tasks if task['type'] != 'spatial']
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if (any(term in question for term in ('老市区', '老城区')) and
            any(term in question for term in ('布局', '作用', '位置', '定位', '依托'))):
        tasks = [task for task in tasks if task['type'] != 'spatial']
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if any(term in question for term in JIANG_HAI_TERMS):
        tasks = [task for task in tasks if task['type'] != 'spatial']
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if any(term in question for term in ('图片', '图像', '照片', '扫描件', '视频', '录像', '画面', '幻灯片', 'PPT')):
        if not any(task['type'] == 'planning' for task in tasks):
            tasks.append({'type': 'planning', 'question': question})
    if any(task['type'] == 'planning' for task in tasks):
        tasks = [task for task in tasks if task['type'] != 'planning'] + [
            {'type': 'planning', 'question': question}]
    return tasks or [{'type': 'planning', 'question': question}]


def split_task(question):
    settings = get_settings()
    if settings.ark_api_key and settings.llm_model:
        try:
            response = chat([{'role':'system','content':SPLIT_SYSTEM},
                             {'role':'user','content':question}], temperature=0).strip()
            if response.startswith('```'):
                response = re.sub(r'^```(?:json)?\s*|\s*```$', '', response, flags=re.IGNORECASE)
            raw = json.loads(response)
            if not isinstance(raw, list) or not raw:
                raise ValueError('模型未返回任务数组')
            raw = [{**item, 'question': item.get('question', item.get('content'))} if
                   isinstance(item, dict) and 'question' not in item and 'content' in item else item
                   for item in raw]
            raw = [{key: value for key, value in item.items() if key != 'content'} if
                   isinstance(item, dict) else item for item in raw]
            tasks = [SubTask.model_validate(item).model_dump(exclude_none=True) for item in raw]
            return [SubTask.model_validate(item).model_dump(exclude_none=True)
                    for item in _normalize_tasks(tasks, question)]
        except (ValueError, TypeError, ValidationError, ConfigurationError):
            logger.warning('模型拆分格式无效，改用本地规则')
    return [SubTask.model_validate(item).model_dump(exclude_none=True)
            for item in _normalize_tasks(_local_split(question), question)]


def summarize(question, results):
    parts = [f'问题：{question}']
    for role, result in results.items():
        status = result.get('status', 'ok')
        data = result.get('data')
        sources = result.get('sources', [])
        if status == 'error':
            content = result.get('error', {}).get('message', '子任务失败')
        elif role.startswith('indicator') and isinstance(data, dict):
            if 'target_value' in data:
                content = (f'{data["name"]}：{data["year"]} 年目标 {data["target_value"]} '
                           f'{data["unit"]}（{data["target_kind"]}）；{data["note"]}')
            else:
                values = '、'.join(f'{year} 年 {value} {data["unit"]}' for year, value in data['values'].items())
                content = f'{data["name"]}：{values}'
                if 'growth_percent' in data:
                    content += f'；增长率 {data["growth_percent"]}%（{data["formula"]}）'
                if data.get('conflicts') or data.get('incomparable'):
                    alternatives = [item['other'] for item in data.get('conflicts', [])]
                    alternatives.extend(data.get('incomparable', []))
                    content += '；另一统计版本记录：' + '、'.join(
                        f'{item["year"]} 年 {item["value"]} {item["unit"]}（{item["source_ref"]["source_file"]}）'
                        for item in alternatives)
        elif role.startswith('spatial') and isinstance(data, list):
            content = '；'.join(f'{item["name"]}：{item["note"]}' for item in data)
        elif role.startswith('evaluation') and isinstance(data, list):
            content = '；'.join(f'{row["指标"]}达成率 {row["达成率"]}%' for row in data)
        elif role.startswith('planning') and isinstance(data, dict):
            names = [('background', '背景'), ('stage_goals', '阶段目标'),
                     ('implementation_paths', '路径举措'), ('evidence', '依据'),
                     ('risks', '风险'), ('suggestions', '建议')]
            content = '\n'.join(f'{title}：{data.get(key, "资料未提及")}' for key, title in names)
        else:
            content = str(data or '依据不足')
        if sources:
            content += '（来源：' + '、'.join(dict.fromkeys(
                f'{src["source_file"]} ' + ' '.join(str(part) for part in
                    (src.get('section'), src.get('page_or_slide')) if part is not None)
                for src in sources)) + '）'
        parts.append(f'[{role} / {status}] {content}')
    return '\n'.join(parts)

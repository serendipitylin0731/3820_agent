"""问题拆分与可追溯汇总。"""
import json
import re

from config import ConfigurationError, get_settings
from contracts import SubTask
from llm_client import chat

SPLIT_SYSTEM = '''将问题拆成 JSON 数组。type 仅为 planning、indicator、spatial、evaluation。
indicator 必须有 key，可用 gdp、gdp_per_capita、gnp、gnp_per_capita、industry_primary、industry_secondary、industry_tertiary、gross_ia、agriculture_output、industry_output、export_total、urban_income、rural_income；spatial 必须有 keyword。只输出 JSON。'''
KEYWORDS = [('gdp_per_capita','人均GDP'),('gnp_per_capita','人均GNP'),('urban_income','城镇收入'),('rural_income','农村收入'),('industry_output','工业总产值'),('gdp','GDP'),('gnp','GNP'),('export_total','出口'),('industry_primary','第一产业'),('industry_secondary','第二产业'),('industry_tertiary','第三产业')]


def _local_split(question):
    tasks = []
    years = [int(y) for y in re.findall(r'(?:1990|1995|2000|2010)', question)]
    if '评估' in question or '达成率' in question or '翻一番' in question or '完成率' in question:
        tasks.append({'type':'evaluation','question':question})
    for key, label in KEYWORDS:
        if label.lower() in question.lower():
            tasks.append({'type':'indicator','question':question,'key':key,'years':years or None})
            break
    if any(word in question for word in ('空间','港口','机场','园区','元洪','苍霞','侨商','博览会')):
        match = next((w for w in ('元洪','苍霞','港口','机场','园区','侨商','博览会') if w in question), '空间')
        tasks.append({'type':'spatial','question':question,'keyword':match})
    if not tasks or any(w in question for w in ('规划','路径','背景','目标','战略')):
        tasks.append({'type':'planning','question':question})
    return tasks


def split_task(question):
    settings = get_settings()
    if settings.ark_api_key and settings.llm_model:
        try:
            raw = json.loads(chat([{'role':'system','content':SPLIT_SYSTEM},
                                   {'role':'user','content':question}], temperature=0))
            if not isinstance(raw, list) or not raw:
                raise ValueError('模型未返回任务数组')
            return [SubTask.model_validate(item).model_dump(exclude_none=True) for item in raw]
        except (ValueError, ConfigurationError):
            pass
    return [SubTask.model_validate(item).model_dump(exclude_none=True) for item in _local_split(question)]


def summarize(question, results):
    parts = [f'问题：{question}']
    for role, result in results.items():
        status = result.get('status', 'ok') if isinstance(result, dict) else 'ok'
        data = result.get('data') if isinstance(result, dict) and 'data' in result else result
        parts.append(f'[{role} / {status}] {data}')
    return '\n'.join(parts)

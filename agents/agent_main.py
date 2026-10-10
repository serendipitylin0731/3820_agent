"""问题拆分与可追溯汇总。"""
import json
import re

from config import ConfigurationError, get_settings
from contracts import SubTask
from llm_client import chat

SPLIT_SYSTEM = '''将问题拆成 JSON 数组。type 仅为 planning、indicator、spatial、evaluation。
indicator 必须有 key，可用 gdp、gdp_per_capita、gnp、gnp_per_capita、industry_primary、industry_secondary、industry_tertiary、gross_ia、agriculture_output、industry_output、export_total、urban_income、rural_income；spatial 必须有 keyword。只输出 JSON。'''
KEYWORDS = [('gdp_per_capita','人均地区生产总值'),('gdp_per_capita','人均GDP'),
            ('gnp_per_capita','人均收入总值'),('gnp_per_capita','人均GNP'),
            ('urban_income','城镇居民人均可支配收入'),('rural_income','农村居民人均纯收入'),
            ('gross_ia','工农业总产值'),('industry_output','工业总产值'),
            ('agriculture_output','农业总产值'),('urban_income','城镇收入'),
            ('rural_income','农村收入'),('gdp','地区生产总值'),('gnp','地区收入总值'),
            ('gdp','GDP'),('gnp','GNP'),('export_total','出口'),
            ('industry_primary','第一产业'),('industry_secondary','第二产业'),
            ('industry_tertiary','第三产业')]


def _local_split(question):
    tasks = []
    years = [int(y) for y in re.findall(r'(?:1990|1995|2000|2010)', question)]
    if '评估' in question or '达成率' in question or '翻一番' in question or '完成率' in question:
        tasks.append({'type':'evaluation','question':question})
    remaining = question
    found = set()
    for key, label in KEYWORDS:
        if label.lower() in remaining.lower() and key not in found:
            tasks.append({'type':'indicator','question':question,'key':key,'years':years or None})
            found.add(key)
            remaining = re.sub(re.escape(label), '', remaining, count=1, flags=re.IGNORECASE)
    if any(word in question for word in ('空间','港口','机场','园区','元洪','苍霞','侨商','博览会')):
        match = next((w for w in ('元洪','苍霞','港口','机场','园区','侨商','博览会') if w in question), '空间')
        tasks.append({'type':'spatial','question':question,'keyword':match})
    if not tasks or any(w in question for w in ('规划','路径','背景','战略')):
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
        except (ValueError, ConfigurationError) as exc:
            raise ValueError('模型输出的子任务格式无效') from exc
    return [SubTask.model_validate(item).model_dump(exclude_none=True) for item in _local_split(question)]


def summarize(question, results):
    parts = [f'问题：{question}']
    for role, result in results.items():
        status = result.get('status', 'ok')
        data = result.get('data')
        sources = result.get('sources', [])
        if status == 'error':
            content = result.get('error', {}).get('message', '子任务失败')
        elif role.startswith('indicator') and isinstance(data, dict):
            values = '、'.join(f'{year} 年 {value} {data["unit"]}' for year, value in data['values'].items())
            content = f'{data["name"]}：{values}'
        elif role.startswith('spatial') and isinstance(data, list):
            content = '；'.join(f'{item["name"]}：{item["note"]}' for item in data)
        elif role.startswith('evaluation') and isinstance(data, list):
            content = '；'.join(f'{row["指标"]}达成率 {row["达成率"]}%' for row in data)
        else:
            content = str(data or '依据不足')
        if sources:
            content += '（来源：' + '、'.join(dict.fromkeys(
                f'{src["source_file"]} {src.get("section") or src.get("page_or_slide") or ""}' for src in sources)) + '；' + ('已核验' if all(src['verified'] for src in sources) else '未独立核验') + '）'
        parts.append(f'[{role} / {status}] {content}')
    return '\n'.join(parts)

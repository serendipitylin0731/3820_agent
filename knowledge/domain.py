"""指南样例数据的唯一读取入口；来源未独立核验时始终保留 verified=false。"""
import json
import math
from functools import lru_cache
from pathlib import Path

from contracts import SourceRef

ROOT = Path(__file__).parent
YEARS = (1990, 1995, 2000, 2010)
GUIDE = 'docs/基于3820战略工程内容的多智能体系统搭建指南.md'


@lru_cache(maxsize=1)
def indicators():
    raw = json.loads((ROOT / 'indicators.json').read_text(encoding='utf-8'))
    if len(raw) != 13:
        raise ValueError('指标必须恰有 13 项')
    result = {}
    for key, item in raw.items():
        values = {int(year): value for year, value in item['values'].items()}
        if tuple(sorted(values)) != YEARS or not item.get('name') or not item.get('unit'):
            raise ValueError(f'指标结构无效：{key}')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values.values()):
            raise ValueError(f'指标数值无效：{key}')
        source = SourceRef.model_validate(item['source_ref'])
        result[key] = {**item, 'values': values, 'source_ref': source.model_dump()}
    if result['gdp']['values'][2010] != 3123.41:
        raise ValueError('2010 年 GDP 基线不匹配')
    return result


@lru_cache(maxsize=1)
def spatial_features():
    raw = json.loads((ROOT / 'spatial.json').read_text(encoding='utf-8'))
    if len(raw) != 7:
        raise ValueError('空间要素必须恰有 7 项')
    for item in raw:
        if not item.get('name') or not item.get('type'):
            raise ValueError('空间要素名称或类型为空')
        SourceRef.model_validate(item['source_ref'])
    return raw


def record_conflicts(records):
    """同键、同年、同口径但异值时保留全部记录，提示人工核验。"""
    groups = {}
    for record in records:
        identity = (record['key'], record['year'], record['basis'])
        groups.setdefault(identity, []).append(record)
    return [group for group in groups.values() if len({r['value'] for r in group}) > 1]

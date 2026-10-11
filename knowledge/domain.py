"""指南指标数据的唯一读取入口，保留不同资料的版本与来源。"""
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
        if not item.get('name') or not item.get('type') or not item.get('period') or not isinstance(item.get('related_paths'), list):
            raise ValueError('空间要素名称或类型为空')
        SourceRef.model_validate(item['source_ref'])
    return raw


@lru_cache(maxsize=1)
def knowledge_model():
    model = json.loads((ROOT / 'entities.json').read_text(encoding='utf-8'))
    expected = {'阶段目标', '指标体系', '空间要素', '实施路径', '效果评估'}
    if set(model['entity_types']) != expected or any(
        relation['from'] not in expected or relation['to'] not in expected
        for relation in model['relations']
    ):
        raise ValueError('知识实体或关系结构无效')
    return model


def record_conflicts(records):
    """同键、同年、同口径但异值时保留全部记录，提示人工核验。"""
    groups = {}
    for record in records:
        identity = (record['key'], record['year'], record['basis'])
        groups.setdefault(identity, []).append(record)
    return [group for group in groups.values() if len({r['value'] for r in group}) > 1]


def extra_observations():
    """另一个来源的值单独保存；不得覆盖指南基线。"""
    from pydantic import BaseModel, ConfigDict, ValidationError

    class Observation(BaseModel):
        model_config = ConfigDict(extra='forbid')
        key: str
        year: int
        value: float
        unit: str
        basis: str
        source_ref: SourceRef

    path = ROOT / 'observations.json'
    records = json.loads(path.read_text(encoding='utf-8'))['records']
    return [Observation.model_validate(item).model_dump() for item in records]


def compare_sources(key, years, baseline, observations=None):
    """按键/年保留异值来源；不同统计口径直接标记不可比。"""
    observations = extra_observations() if observations is None else observations
    relevant = [item for item in observations if item['key'] == key and item['year'] in years]
    conflicts, incomparable = [], []
    for item in relevant:
        base_value = baseline['values'][item['year']]
        if item['unit'] != baseline['unit'] or item['basis'] != baseline['basis']:
            incomparable.append(item)
        elif item['value'] != base_value:
            conflicts.append({'year':item['year'], 'baseline_value':base_value,
                              'baseline_source':baseline['source_ref'], 'other':item})
    return {'conflicts':conflicts, 'incomparable':incomparable}

"""确定性指标查询与计算。"""
import json
from pathlib import Path
from knowledge.domain import YEARS, indicators, compare_sources

# 兼容现有评估调用；数据只从 JSON 加载。
INDICATOR_DATA = indicators()
ALIASES = {'GDP': 'gdp', '地区生产总值': 'gdp', '人均GDP': 'gdp_per_capita',
           'GNP': 'gnp', '城镇收入': 'urban_income', '农村收入': 'rural_income'}


def query_target(key, years):
    """区分指南表 4 的阶段目标与原始扫描表中的目标列值。"""
    targets = json.loads((Path(__file__).parents[1] / 'knowledge' / 'original_targets.json').read_text(encoding='utf-8'))
    info = indicators().get(key)
    if info is None or not years or len(years) != 1:
        return {'insufficient_evidence': '请指定一项已收录指标及单一年份。', 'sources': []}
    year = years[0]
    source = targets['source_ref']
    if key == 'gnp' and str(year) in targets['gnp']:
        value = targets['gnp'][str(year)]
        return {'name': info['name'], 'year': year, 'target_value': value, 'unit': '亿元',
                'target_kind': '原始扫描目标表列值',
                'note': '这是规划目标；指南表1记录的是后来完成值，两者不能当作同一数据。',
                'sources': [source]}
    if key == 'gdp' and year == 1995:
        value = round(info['values'][1990] * 2, 2)
        return {'name': info['name'], 'year': year, 'target_value': value, 'unit': info['unit'],
                'target_kind': '指南表4列示的GDP阶段目标（1990年数值翻番）',
                'note': '原始扫描目标表未单列GDP；其中1995年GNP目标为221亿元，与GDP目标不是同一指标。',
                'sources': [info['source_ref'], source]}
    return {'insufficient_evidence': f'原始扫描目标表未列出 {year} 年{info["name"]}目标，无法给出数值。',
            'sources': [source]}


def query_indicator(key, years=None, *, growth=False):
    key = ALIASES.get(key, key)
    info = indicators().get(key)
    if info is None:
        return {'error': f'未找到指标 {key}，可查：{list(indicators())}'}
    years = list(YEARS) if years is None else years
    if not years:
        return {'insufficient_evidence': f'请指定{info["name"]}的查询年份；可查年份：{list(YEARS)}。'}
    if any(y not in YEARS for y in years):
        missing = [year for year in years if year not in YEARS]
        return {'insufficient_evidence':
                f'已收录指标表未包含{",".join(map(str, missing))}年的{info["name"]}数据。'
                f'可查年份：{list(YEARS)}。'}
    comparison = compare_sources(key, years, info)
    values = {year: info['values'][year] for year in years}
    result = {'key': key, 'name': info['name'], 'unit': info['unit'], 'values': values,
              'basis': info['basis'], 'source': info['source_ref'], 'verified': info['source_ref']['verified'],
              'conflicts': comparison['conflicts'], 'incomparable': comparison['incomparable']}
    if growth:
        if comparison['conflicts'] or comparison['incomparable']:
            return {'error': '存在不同统计版本，请指定同一版本和统计口径后计算增长率',
                    'key': key, 'name': info['name'], 'unit': info['unit'],
                    'values': values, **comparison}
        if len(years) != 2 or years[0] >= years[1]:
            return {'error': '增长率须提供按升序排列的两个年份'}
        base, final = (values[year] for year in years)
        if base == 0:
            return {'error': '基期为零，无法计算增长率'}
        result['growth_percent'] = round((final / base - 1) * 100, 1)
        result['formula'] = '(末期值/基期值-1)×100%'
    return result


def industry_structure(year):
    if year not in YEARS:
        return {'error': f'未收录年份，可查年份：{list(YEARS)}'}
    keys = ('industry_primary', 'industry_secondary', 'industry_tertiary')
    return {'year': year, 'shares': {key: indicators()[key]['values'][year] for key in keys},
            'unit': '%', 'sources': [indicators()[key]['source_ref'] for key in keys]}

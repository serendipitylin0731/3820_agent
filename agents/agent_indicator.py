"""确定性指标查询与计算。"""
from knowledge.domain import YEARS, indicators, compare_sources

# 兼容现有评估调用；数据只从 JSON 加载。
INDICATOR_DATA = indicators()
ALIASES = {'GDP': 'gdp', '地区生产总值': 'gdp', '人均GDP': 'gdp_per_capita',
           'GNP': 'gnp', '城镇收入': 'urban_income', '农村收入': 'rural_income'}


def query_indicator(key, years=None, *, growth=False):
    key = ALIASES.get(key, key)
    info = indicators().get(key)
    if info is None:
        return {'error': f'未找到指标 {key}，可查：{list(indicators())}'}
    years = list(YEARS) if years is None else years
    if not years or any(y not in YEARS for y in years):
        return {'error': f'未收录年份，可查年份：{list(YEARS)}'}
    comparison = compare_sources(key, years, info)
    values = {year: info['values'][year] for year in years}
    result = {'key': key, 'name': info['name'], 'unit': info['unit'], 'values': values,
              'basis': info['basis'], 'source': info['source_ref'], 'verified': info['source_ref']['verified'],
              'conflicts': comparison['conflicts'], 'incomparable': comparison['incomparable']}
    if growth:
        if comparison['conflicts'] or comparison['incomparable']:
            return {'error': '存在异值来源或不可比口径，须先核验后计算增长率', **comparison}
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

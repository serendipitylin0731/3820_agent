# agents/agent_indicator.py
INDICATOR_DATA = {
    'gdp': {'name': '地区生产总值（GDP）', 'unit': '亿元', 'values': {1990: 102.40, 1995: 464.14, 2000: 876.39, 2010: 3123.41}},
    'gdp_per_capita': {'name': '人均地区生产总值', 'unit': '元', 'values': {1990: 1936, 1995: 8219, 2000: 14841, 2010: 44000}},
    'gnp': {'name': '地区收入总值（GNP）', 'unit': '亿元', 'values': {1990: 110.91, 1995: 495.55, 2000: 925.35, 2010: 3165.05}},
    'gnp_per_capita': {'name': '人均收入总值（人均GNP）', 'unit': '元', 'values': {1990: 2097, 1995: 8776, 2000: 15670, 2010: 45262}},
    'industry_primary': {'name': '第一产业占比', 'unit': '%', 'values': {1990: 28.72, 1995: 21.23, 2000: 15.42, 2010: 9.05}},
    'industry_secondary': {'name': '第二产业占比', 'unit': '%', 'values': {1990: 40.25, 1995: 36.02, 2000: 43.23, 2010: 44.88}},
    'industry_tertiary': {'name': '第三产业占比', 'unit': '%', 'values': {1990: 31.03, 1995: 42.75, 2000: 41.34, 2010: 46.06}},
    'gross_ia': {'name': '工农业总产值', 'unit': '亿元', 'values': {1990: 179.76, 1995: 666.28, 2000: 1341.27, 2010: 5349.07}},
    'agriculture_output': {'name': '农业总产值', 'unit': '亿元', 'values': {1990: 42.48, 1995: 159.46, 2000: 217.42, 2010: 480.01}},
    'industry_output': {'name': '工业总产值', 'unit': '亿元', 'values': {1990: 137.28, 1995: 506.82, 2000: 1123.85, 2010: 4869.05}},
    'export_total': {'name': '出口总值', 'unit': '亿美元', 'values': {1990: 2.34, 1995: 15.67, 2000: 27.29, 2010: 163.14}},
    'urban_income': {'name': '城镇居民人均可支配收入', 'unit': '元', 'values': {1990: 1537, 1995: 4896, 2000: 7944, 2010: 22723}},
    'rural_income': {'name': '农村居民人均纯收入', 'unit': '元', 'values': {1990: 864, 1995: 2303, 2000: 3860, 2010: 8543}},
}
def query_indicator(key, years=None):
    # 按指标键与年份查询；未收录的指标返回错误信息
    info = INDICATOR_DATA.get(key)
    if info is None:
        return {'error': f'未找到指标 {key}，可查：{list(INDICATOR_DATA)}'}
    years = sorted(info['values']) if years is None else years
    missing_years = [year for year in years if year not in info['values']]
    if missing_years:
        return {'error': '未收录年份{}，可查年份：{}'.format(missing_years, sorted(info['values']))}
    return {
        'name': info['name'],
        'unit': info['unit'],
        'values': {y: info['values'][y] for y in years if y in info['values']},
        'source': '附件资料《主要指标完成情况》表',
    }

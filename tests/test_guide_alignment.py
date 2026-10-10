"""指南是需求与样例数据的基准，防止 README 或 JSON 自行漂移。"""
from decimal import Decimal
from pathlib import Path

from knowledge.domain import GUIDE, indicators, knowledge_model, spatial_features


def test_indicator_json_matches_guide_table():
    guide = Path(GUIDE).read_text(encoding='utf-8')
    table = guide.split('**表1 “3820”战略工程主要指标完成情况（来自附件资料）**', 1)[1]
    table = table.split('指标智能体应同时记录', 1)[0]
    rows = [line for line in table.splitlines() if line.startswith('|') and '---' not in line]
    keys = ('gnp','gnp_per_capita','gdp','industry_primary','industry_secondary',
            'industry_tertiary','gdp_per_capita','gross_ia','agriculture_output',
            'industry_output','export_total','urban_income','rural_income')
    assert len(rows) == 14
    for key, line in zip(keys, rows[1:]):
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        assert cells[1] == indicators()[key]['unit']
        expected = [Decimal(value) for value in cells[2:6]]
        actual = [Decimal(str(indicators()[key]['values'][year])) for year in (1990,1995,2000,2010)]
        assert actual == expected, key


def test_five_entities_and_spatial_paths():
    assert len(knowledge_model()['entity_types']) == 5
    assert len(spatial_features()) == 7
    assert next(x for x in spatial_features() if x['name'] == '苍霞片区')['related_paths'] == ['拓新改旧']

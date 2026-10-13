from agents.agent_evaluation import eval_1995_phase
from agents.agent_indicator import INDICATOR_DATA, industry_structure, query_indicator, query_target
from agents.agent_spatial import query_spatial
from knowledge.domain import indicators, record_conflicts, spatial_features


def test_guide_baseline_and_provenance():
    assert len(indicators()) == 13
    assert all(len(x['values']) == 4 and x['source_ref']['verified'] for x in indicators().values())
    assert indicators()['gdp']['values'][2010] == 3123.41
    assert len(spatial_features()) == 7


def test_queries_and_growth():
    assert query_indicator('GDP', [1990, 1995], growth=True)['growth_percent'] == 353.3
    assert 'error' in query_indicator('unknown')
    assert '未包含2020年' in query_indicator('gdp', [2020])['insufficient_evidence']
    assert industry_structure(1995)['shares']['industry_primary'] == 21.23
    assert query_spatial('元洪')[0]['source_ref']['verified'] is True
    assert 'error' in query_spatial('不存在')


def test_evaluation_and_conflict():
    rows = eval_1995_phase(INDICATOR_DATA)
    assert [row['达成率'] for row in rows] == [224.2, 226.6, 212.3, 159.3, 133.3, 184.6]
    assert rows[0]['目标'] == 221
    assert rows[0]['目标来源']['source_file'].startswith('https://article.xuexi.cn/')
    records = [{'key':'gdp','year':1995,'basis':'a','value':1},
               {'key':'gdp','year':1995,'basis':'a','value':2}]
    assert record_conflicts(records) == [records]


def test_original_gnp_targets_are_not_mislabelled_as_gdp():
    gnp = query_target('gnp', [2000])
    assert gnp['target_value'] == 482
    assert gnp['sources'][0]['page_or_slide'] == '预览第45页'
    assert 'insufficient_evidence' in query_target('gdp', [2010])

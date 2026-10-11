from agents import agent_indicator
from knowledge.domain import compare_sources, indicators


def test_conflicting_value_keeps_both_sources(monkeypatch):
    baseline = indicators()['gdp']
    other = {'key':'gdp','year':2010,'value':999,'unit':baseline['unit'],
             'basis':baseline['basis'],'source_ref':{'source_file':'attachment.pdf',
             'data_version':'v2','verified':False}}
    monkeypatch.setattr('knowledge.domain.extra_observations', lambda: [other])
    result = agent_indicator.query_indicator('gdp', [1990, 2010])
    assert result['values'][2010] == 3123.41
    assert result['conflicts'][0]['other']['value'] == 999
    assert result['conflicts'][0]['baseline_source']['verified'] is True
    assert 'error' in agent_indicator.query_indicator('gdp', [1990, 2010], growth=True)


def test_incomparable_basis_is_separate():
    baseline = indicators()['gdp']
    other = {'key':'gdp','year':2010,'value':3123.41,'unit':'元',
             'basis':'不同口径','source_ref':{'source_file':'attachment.pdf',
             'data_version':'v2','verified':False}}
    result = compare_sources('gdp', [2010], baseline, [other])
    assert result['incomparable'] == [other]
    assert result['conflicts'] == []


def test_official_yearbook_alternative_is_preserved_in_answer():
    from agents.agent_main import summarize
    result = agent_indicator.query_indicator('gdp', [2010])
    assert result['values'][2010] == 3123.41
    assert any(item['value'] == 3242.65 for item in result['incomparable'])
    answer = summarize('2010年GDP是多少？', {'indicator': {
        'status': 'ok', 'data': result, 'sources': [result['source']]}})
    assert '3123.41' in answer and '3242.65' in answer
    assert '另一统计版本' in answer

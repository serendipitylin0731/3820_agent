from config import Settings


def test_offline_mixed_partial_and_checkpoint(monkeypatch, tmp_path):
    import graph
    settings = Settings(checkpoint_path=tmp_path / 'state.sqlite3')
    graph.get_graph.cache_clear()
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(graph, 'split_task', lambda q: [
        {'type':'indicator','question':q,'key':'gdp','years':[2010]},
        {'type':'spatial','question':q,'keyword':'不存在'}])
    result = graph.ask('混合问题', 'session-a')
    assert result['results']['indicator_1']['data']['values'][2010] == 3123.41
    assert result['results']['spatial_2']['status'] == 'error'
    snapshot = graph.get_graph().get_state({'configurable':{'thread_id':'session-a'}})
    assert snapshot.values['answer'] == result['answer']
    assert graph.get_graph().get_state({'configurable':{'thread_id':'session-b'}}).values == {}
    graph.get_graph.cache_clear()
    assert graph.get_graph().get_state({'configurable':{'thread_id':'session-a'}}).values['answer'] == result['answer']
    graph.get_graph.cache_clear()


def test_offline_default_split_without_key(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings', lambda: Settings())
    tasks = agent_main.split_task('2010年 GDP 是多少？')
    assert tasks[0]['key'] == 'gdp'

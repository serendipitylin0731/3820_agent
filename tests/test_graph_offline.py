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


def test_online_split_accepts_content_alias_and_falls_back_on_invalid(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='test-only-key', llm_model='fake-model'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"planning","content":"三阶段目标"}]')
    assert agent_main.split_task('三阶段目标')[0]['question'] == '三阶段目标'
    monkeypatch.setattr(agent_main, 'chat', lambda *_args, **_kwargs: '无效响应')
    assert agent_main.split_task('2010年GDP是多少？')[0]['key'] == 'gdp'


def test_mixed_metrics_and_qualitative_goal(monkeypatch):
    from agents import agent_main
    import graph
    settings = Settings()
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    tasks = agent_main.split_task('1995年GDP和GNP翻一番目标完成情况')
    assert {'evaluation', 'indicator'} == {item['type'] for item in tasks}
    assert {item['key'] for item in tasks if item['type'] == 'indicator'} == {'gdp', 'gnp'}
    value = graph.execute_node({'sub_tasks':[{'type':'evaluation','question':'2000年目标评估'}]})
    assert value['results']['evaluation']['status'] == 'insufficient_evidence'

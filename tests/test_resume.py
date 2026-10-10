from config import Settings


def test_resume_interrupted_graph_after_restart(monkeypatch, tmp_path):
    import graph
    from agents import agent_main
    settings = Settings(checkpoint_path=tmp_path / 'checkpoints.sqlite3')
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    app = graph.get_graph()
    config = {'configurable':{'thread_id':'resume-test'}}
    initial = {'question':'2010年GDP是多少？','thread_id':'resume-test','request_id':'r1',
               'sub_tasks':[],'kb_context':'','kb_sources':[],'kb_error':None,
               'results':{},'errors':[],'answer':''}
    app.invoke(initial, config, interrupt_after=['parse_node'])
    assert app.get_state(config).next
    graph.get_graph.cache_clear()
    completed = graph.resume('resume-test')
    assert completed['results']['indicator']['data']['values'][2010] == 3123.41
    assert graph.get_graph().get_state(config).next == ()
    graph.get_graph.cache_clear()


def test_resume_missing_session(monkeypatch, tmp_path):
    import pytest
    import graph
    monkeypatch.setattr(graph, 'get_settings',
                        lambda: Settings(checkpoint_path=tmp_path / 'empty.sqlite3'))
    graph.get_graph.cache_clear()
    with pytest.raises(ValueError, match='未找到'):
        graph.resume('missing')
    graph.get_graph.cache_clear()


def test_same_question_continues_pending_session(monkeypatch, tmp_path):
    import graph
    from agents import agent_main
    settings = Settings(checkpoint_path=tmp_path / 'pending.sqlite3')
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    config = {'configurable': {'thread_id': 'pending'}}
    graph.get_graph().invoke({'question':'2010年GDP是多少？', 'thread_id':'pending',
                              'request_id':'r', 'sub_tasks':[], 'results':{}},
                             config, interrupt_after=['parse_node'])
    assert graph.ask('2010年GDP是多少？', 'pending')['results']['indicator']['status'] == 'ok'
    graph.get_graph.cache_clear()

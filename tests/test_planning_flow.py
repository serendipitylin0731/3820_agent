from config import Settings
from contracts import KnowledgeHit, KnowledgeResult, SourceRef


def test_model_routes_general_strategic_layout_to_planning(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"spatial","question":"战略空间布局",'
                                                 '"keyword":"城市空间布局"}]')
    tasks = agent_main.split_task('3820战略工程对城市空间布局有什么安排？')
    assert [task['type'] for task in tasks] == ['planning']


def test_model_indicator_guess_needs_indicator_in_question(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"indicator","question":"量子芯片制程",'
                                                 '"key":"industry_output"}]')
    assert [task['type'] for task in agent_main.split_task('量子芯片的制程是多少？')] == ['planning']


def test_model_cannot_drop_explicit_achievement_request(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"indicator","question":"1995年GDP目标达成率",'
                                                 '"key":"gdp"}]')
    assert {task['type'] for task in agent_main.split_task('1995年GDP目标达成率是多少？')} == {
        'indicator', 'evaluation'}


def test_target_question_is_not_answered_with_observed_indicator_values(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"indicator","question":"1995年GDP目标",'
                                                 '"key":"gdp"}]')
    assert [task['type'] for task in agent_main.split_task('1995年GDP目标是多少？')] == ['planning']


def test_planning_report_has_sections_and_no_evidence_behavior(monkeypatch):
    from agents import agent_planning
    monkeypatch.setattr(agent_planning, 'get_settings', lambda: Settings())
    report = agent_planning.run_planning('三阶段目标', '[指南 1.2] 1995年主要指标翻一番。\n以侨引侨是实施路径。')
    assert set(report) == {'background','stage_goals','implementation_paths','evidence','risks','suggestions'}
    assert '1995' in report['stage_goals']
    assert '分析建议' in report['suggestions']
    assert agent_planning.run_planning('无依据', '') is None


def test_model_advice_cannot_replace_evidence(monkeypatch):
    from agents import agent_planning
    monkeypatch.setattr(agent_planning, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    import llm_client
    monkeypatch.setattr(llm_client, 'chat', lambda _messages: '{"risks":"需核对","suggestions":"补充原件"}')
    report = agent_planning.run_planning('三阶段目标', '[指南] 1995年指标翻一番。')
    assert report['stage_goals'] == '[指南] 1995年指标翻一番。'
    assert report['evidence'] == '[指南] 1995年指标翻一番。'
    assert report['suggestions'].startswith('分析建议：')


def test_retrieval_failure_isolated_to_planning(monkeypatch):
    import graph
    calls = []
    def fail(_query, **_kwargs):
        calls.append(1)
        raise TimeoutError('transient')
    monkeypatch.setattr(graph, 'search', fail)
    monkeypatch.setattr(graph, 'get_settings', lambda: Settings())
    state = {'question':'战略路径','request_id':'req','thread_id':'t'}
    fetched = graph.retrieve_node(state)
    assert len(calls) == 2
    assert fetched['kb_error'] == '检索暂不可用'
    result = graph.execute_node({**state, **fetched,
        'sub_tasks':[{'type':'planning','question':'战略路径'},
                     {'type':'indicator','question':'GDP','key':'gdp','years':[2010]}]})
    assert result['results']['planning_1']['status'] == 'error'
    assert result['results']['indicator_2']['status'] == 'ok'
    assert graph.route_node({'sub_tasks':[{'type':'indicator'}]}) == 'execute_node'


def test_retrieval_uses_single_hit_set(monkeypatch):
    import graph
    hit = KnowledgeHit(chunk_id='x', content='1995年翻一番',
                       source=SourceRef(source_file='guide.md', data_version='v1', verified=False))
    calls = []
    def fake(_query, **_kwargs):
        calls.append(1)
        return KnowledgeResult(status='ok', hits=[hit])
    monkeypatch.setattr(graph, 'search', fake)
    monkeypatch.setattr(graph, 'get_settings', lambda: Settings())
    result = graph.retrieve_node({'question':'1995年目标'})
    assert len(calls) == 1
    assert '1995年翻一番' in result['kb_context']
    assert result['kb_sources'][0]['source_file'] == 'guide.md'

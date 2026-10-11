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


def test_development_zone_and_old_city_route_to_planning_even_if_model_guesses_spatial(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"spatial","question":"开发区",'
                                                 '"keyword":"开发区"}]')
    question = '福州经济技术开发区和老市区分别承担什么作用？'
    tasks = agent_main.split_task(question)
    assert [task['type'] for task in tasks] == ['planning']
    assert tasks[0]['question'] == question


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
    tasks = agent_main.split_task('1995年GDP目标是多少？')
    assert [task['type'] for task in tasks] == ['indicator']
    assert tasks[0]['target'] is True


def test_growth_intent_is_preserved_from_question(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings', lambda: Settings())
    task = agent_main.split_task('1995年比1990年GDP增长率是多少？')[0]
    assert task['years'] == [1990, 1995]
    assert task['growth'] is True


def test_picture_question_routes_to_evidence_search(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"spatial",'
                                                 '"question":"投资示意图有哪些区域",'
                                                 '"keyword":"闽江口金三角"}]')
    tasks = agent_main.split_task('福州市闽江口金三角经济圈投资示意图有哪些区域？')
    assert [task['type'] for task in tasks] == ['planning']


def test_airport_history_uses_planning_instead_of_spatial_lookup(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings', lambda: Settings())
    tasks = agent_main.split_task('长乐国际机场在哪一年正式通航？它与3820工程有什么关系？')
    assert [task['type'] for task in tasks] == ['planning']


def test_model_cannot_add_evaluation_to_plain_indicator_query(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"evaluation","question":"1995年GDP是多少？"}]')
    tasks = agent_main.split_task('1995年GDP是多少？')
    assert [task['type'] for task in tasks] == ['indicator']


def test_three_industry_structure_uses_recorded_percentages(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings', lambda: Settings())
    tasks = agent_main.split_task('2010年福州三次产业结构如何？')
    assert {task['key'] for task in tasks} == {
        'industry_primary', 'industry_secondary', 'industry_tertiary'}
    assert all(task['years'] == [2010] for task in tasks)


def test_planned_airport_date_is_not_used_as_opening_date(monkeypatch):
    from agents import agent_planning
    monkeypatch.setattr(agent_planning, 'get_settings', lambda: Settings())
    report = agent_planning.run_planning('长乐国际机场哪年正式通航？',
                                         '规划称长乐国际机场计划在1996年建成投入使用。')
    assert 'insufficient_evidence' in report


def test_split_planning_keeps_the_full_original_question(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat', lambda *_args, **_kwargs: (
        '[{"type":"planning","question":"正式通航年份"},'
        '{"type":"planning","question":"与工程的关系"}]'))
    question = '长乐国际机场哪年正式通航？它与3820工程有什么关系？'
    tasks = agent_main.split_task(question)
    assert len(tasks) == 1
    assert tasks[0]['type'] == 'planning'
    assert tasks[0]['question'] == question


def test_whether_qualitative_goal_achieved_routes_to_evaluation(monkeypatch):
    from agents import agent_main
    monkeypatch.setattr(agent_main, 'get_settings', lambda: Settings())
    tasks = agent_main.split_task('2000年目标是否已经达成？')
    assert any(task['type'] == 'evaluation' for task in tasks)


def test_map_answer_uses_reviewed_labels_when_scan_page_is_retrieved(monkeypatch):
    from agents import agent_planning
    monkeypatch.setattr(agent_planning, 'get_settings', lambda: Settings())
    text = '[原始扫描件 OCR 预览第27页] 福州市闽江口金三角经济圈投资示意图\n福州经济技术开发区'
    answer = agent_planning.run_planning('投资示意图有哪些区域？', text)
    assert '罗源湾投资区' in answer['implementation_paths']
    assert '元洪开发区' in answer['implementation_paths']
    assert '人工转录' in answer['evidence']


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


def test_layout_retrieval_uses_original_section_and_passage(monkeypatch):
    import graph
    from agents import agent_planning
    queries = []
    hit = KnowledgeHit(chunk_id='scan-40',
                       content='四、战略布局\n以福州经济技术开发区为前导，以老市区为依托，建设闽江口金三角经济圈。',
                       source=SourceRef(source_file='scan', page_or_slide='预览第40页',
                                        data_version='scan-v1', verified=False))
    monkeypatch.setattr(graph, 'search', lambda query, **_kw: (
        queries.append(query) or KnowledgeResult(status='ok', hits=[hit])))
    monkeypatch.setattr(graph, 'get_settings', lambda: Settings())
    fetched = graph.retrieve_node({'question':'3820战略工程对城市空间布局有什么安排？'})
    assert queries == ['福州市20年经济社会发展战略设想 战略布局']
    monkeypatch.setattr(agent_planning, 'get_settings', lambda: Settings())
    report = agent_planning.run_planning('3820战略工程对城市空间布局有什么安排？',
                                         fetched['kb_context'])
    assert '闽江口金三角经济圈' in report['implementation_paths']

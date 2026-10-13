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


def test_jiang_hai_question_routes_to_cited_planning_answer(monkeypatch):
    import graph
    from agents import agent_main, agent_planning
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"spatial","question":"沿江向海",'
                                                 '"keyword":"空间"}]')
    monkeypatch.setattr(graph, 'get_settings', lambda: Settings())
    monkeypatch.setattr(graph, 'search', lambda *_args, **_kwargs:
                        KnowledgeResult(status='insufficient_evidence'))
    question = '为什么强调沿江向海'
    tasks = agent_main.split_task(question)
    assert [task['type'] for task in tasks] == ['planning']
    fetched = graph.retrieve_node({'question': question})
    assert len(fetched['kb_sources']) == 1
    executed = graph.execute_node({'question': question, 'sub_tasks': tasks, **fetched})
    assert executed['results']['planning']['status'] == 'ok'
    result = graph.answer_node({'question': question, **executed})
    assert '沿江向海' in result['answer']
    assert '港口开放' in result['answer']
    assert '暂时无法' not in result['answer']
    assert [source['section'] for source in result['results']['planning']['sources']] == [
        '预览第40页：战略布局']


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


def test_economic_circle_question_uses_local_scans_without_partial_failure(monkeypatch):
    import graph
    from agents import agent_main
    question = '福州当时为什么要建设闽江口金三角经济圈？涉及哪些区域？'
    monkeypatch.setattr(agent_main, 'get_settings',
                        lambda: Settings(ark_api_key='fake', llm_model='fake'))
    monkeypatch.setattr(agent_main, 'chat',
                        lambda *_args, **_kwargs: '[{"type":"spatial","question":"涉及哪些区域",'
                                                 '"keyword":"闽江口金三角"},'
                                                 '{"type":"planning","question":"建设原因"}]')
    tasks = agent_main.split_task(question)
    assert [task['type'] for task in tasks] == ['planning']
    fetched = graph.retrieve_node({'question': question})
    assert {source['source_file'] for source in fetched['kb_sources']} == {
        'knowledge/library/media/原件扫描_page_0027.png',
        'knowledge/library/media/原件扫描_page_0040.png',
    }
    executed = graph.execute_node({'question': question, 'sub_tasks': tasks, **fetched})
    assert executed['results']['planning']['status'] == 'ok'
    assert {source['source_file'] for source in executed['results']['planning']['sources']} == {
        'knowledge/library/media/原件扫描_page_0027.png',
        'knowledge/library/media/原件扫描_page_0040.png',
    }


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
    text = '[原始扫描件 OCR 预览第27页] 福州市闽江口金三角经济圈投资示意图\n福州经济技术开发区'
    answer = agent_planning.run_planning('投资示意图有哪些区域？', text)
    assert '罗源湾投资区' in answer['implementation_paths']
    assert '元洪开发区' in answer['implementation_paths']
    assert '人工转录' in answer['evidence']


def test_planning_requires_reviewed_evidence():
    from agents import agent_planning
    report = agent_planning.run_planning('三阶段目标', '[指南 1.2] 1995年主要指标翻一番。\n以侨引侨是实施路径。')
    assert 'insufficient_evidence' in report
    assert agent_planning.run_planning('无依据', '') is None


def test_reviewed_evidence_is_not_vetoed_by_model_advice(monkeypatch):
    from agents import agent_planning
    import llm_client
    monkeypatch.setattr(llm_client, 'chat', lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError('规划证据判定不应再调用模型')))
    from knowledge.curated import direct_hits
    from knowledge.knowledge_base import format_context
    report = agent_planning.run_planning('1995年阶段目标是什么？',
                                         format_context(KnowledgeResult(status='ok',
                                                                        hits=direct_hits('1995年阶段目标是什么？'))))
    assert '1995' in report['implementation_paths']
    assert report['source_sections'] == ['3820 战略工程三阶段目标']


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


def test_retrieval_uses_single_hit_set_when_no_reviewed_section_matches(monkeypatch):
    import graph
    hit = KnowledgeHit(chunk_id='x', content='1995年翻一番',
                       source=SourceRef(source_file='guide.md', data_version='v1', verified=False))
    calls = []
    def fake(_query, **_kwargs):
        calls.append(1)
        return KnowledgeResult(status='ok', hits=[hit])
    monkeypatch.setattr(graph, 'search', fake)
    monkeypatch.setattr(graph, 'get_settings', lambda: Settings())
    result = graph.retrieve_node({'question':'罕见专题'})
    assert len(calls) == 1
    assert '1995年翻一番' in result['kb_context']
    assert any(source['source_file'] == 'guide.md' for source in result['kb_sources'])


def test_reviewed_layout_section_avoids_noisy_search(monkeypatch):
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
    assert queries == []
    report = agent_planning.run_planning('3820战略工程对城市空间布局有什么安排？',
                                         fetched['kb_context'])
    assert '闽江口金三角经济圈' in report['implementation_paths']

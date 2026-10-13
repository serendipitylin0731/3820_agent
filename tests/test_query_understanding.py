import pytest

from config import Settings
from knowledge.curated import direct_hits
from knowledge.query_understanding import resolve_question


@pytest.mark.parametrize('question', [
    '《习近平生态文明思想概论》第100页主要讲什么？',
    '党的十九大报告提出的新时代中国特色社会主义思想核心内容是什么？',
    '习近平在福建推动林权制度改革的背景和做法是什么？',
])
def test_named_documents_are_not_rewritten_as_the_3820_background(question):
    resolved = resolve_question(question, '3820战略工程是什么？', settings=Settings())
    assert resolved == question.replace('？', '?')


@pytest.mark.parametrize('question', [
    '3820战略工程具体内容',
    '3820工程主要内容是什么？',
    '3820战略工程都包括哪些方面？',
    '介绍一下3820战略工程',
    '这个工程包含哪些内容？',
    '福州3820到底讲了什么？',
    '这个战略工程讲了哪些事情？',
    '3820的核心安排是什么？',
    '福州三八二零工程有什么内容？',
    '介绍一下这份二十年规划？',
])
def test_overview_paraphrases_reach_reviewed_sources(question):
    resolved = resolve_question(question, settings=Settings())
    sections = {hit.source.section for hit in direct_hits(resolved)}
    assert '3820 战略工程三阶段目标' in sections
    assert '预览第40页：战略布局' in sections
    assert '背景导读·05 重点工程' in sections


@pytest.mark.parametrize('question', [
    '三个结算是什么？',
    '三个阶段是什么？',
    '分几步实施？',
    '3820分为哪三个时期？',
    '三步目标分别是什么？',
    '3、8、20分别代表什么？',
])
def test_stage_paraphrases_and_typo_reach_phase_evidence(question):
    resolved = resolve_question(question, settings=Settings())
    assert '3820' in resolved
    assert any(hit.source.section == '3820 战略工程三阶段目标'
               for hit in direct_hits(resolved))


@pytest.mark.parametrize(('question', 'section'), [
    ('当时为什么要搞这个战略？', '背景导读·01 起点与问题'),
    ('这项工程有哪些重点项目？', '背景导读·05 重点工程'),
])
def test_other_implicit_project_paraphrases(question, section):
    resolved = resolve_question(question, settings=Settings())
    assert any(hit.source.section == section for hit in direct_hits(resolved))


def test_ecology_question_uses_environment_source():
    resolved = resolve_question('3820的生态建设如何安排？', settings=Settings())
    assert any(hit.source.section == '背景导读·06 城市与生活'
               for hit in direct_hits(resolved))


def test_followups_reuse_the_previous_question_without_leaking_other_topics():
    settings = Settings()
    assert resolve_question('那第二阶段呢？', '3820战略工程的三个阶段是什么？',
                            settings=settings) == '3820战略工程的第二阶段目标是什么？'
    assert resolve_question('那八年那个阶段呢？', '3820战略工程的三个阶段是什么？',
                            settings=settings) == '3820战略工程的第二阶段目标是什么？'
    assert resolve_question('那2000年呢？', '1995年GDP是多少？',
                            settings=settings) == '2000年GDP是多少?'
    assert resolve_question('那GNP呢？', '1995年GDP是多少？',
                            settings=settings) == '1995年GNP？'
    assert resolve_question('那GNP呢？', '1995年GDP目标是多少？',
                            settings=settings) == '1995年GNP目标？'
    assert resolve_question('这些目标都实现了吗？', '1995年GNP目标？',
                            history=['1995年GDP目标是多少？', '1995年GNP目标？'],
                            settings=settings) == '1995年GDP和GNP目标实现了吗？'
    assert '2000年目标实现了吗' in resolve_question('这个目标实现了吗？',
                                               '3820战略工程2000年目标是什么？',
                                               settings=settings)
    assert '2000年目标实现了吗' in resolve_question('目标实现了吗？',
                                               '2000年阶段的目标是什么？', settings=settings)
    assert resolve_question('这个数字为什么有不同版本？', '2010年福州GDP是多少？',
                            settings=settings) == '2010年GDP为什么有不同版本？'
    assert '长乐国际机场' in resolve_question('它有什么作用？',
                                          '长乐国际机场建设与3820工程有什么关系？',
                                          settings=settings)
    assert resolve_question('和第一阶段相比有什么变化？',
                            '3820战略工程的第二阶段目标是什么？', settings=settings).startswith(
                                '3820战略工程的第二阶段和第一阶段相比')
    assert resolve_question('它和3820有什么关系？', '海上福州是什么？',
                            settings=settings).startswith('海上福州和3820')
    assert resolve_question('今天北京天气如何？', '3820战略工程是什么？',
                            settings=settings) == '今天北京天气如何?'


def test_model_can_classify_unfamiliar_paraphrase_but_only_to_known_topic(monkeypatch):
    from knowledge import query_understanding as understanding
    settings = Settings(ark_api_key='fake', llm_model='fake')
    monkeypatch.setattr(understanding, 'chat', lambda *_a, **_k: '{"topic":"overview"}')
    assert understanding.resolve_question('3820这套方案的来龙去脉', settings=settings) == \
        '3820战略工程的主要内容是什么？'
    assert understanding.resolve_question('说说这套蓝图的脉络', settings=settings) == \
        '3820战略工程的主要内容是什么？'
    monkeypatch.setattr(understanding, 'chat', lambda *_a, **_k: '{"topic":"invalid"}')
    assert understanding.resolve_question('3820这套方案的来龙去脉', settings=settings) == \
        '3820这套方案的来龙去脉'
    monkeypatch.setattr(understanding, 'chat', lambda *_a, **_k: '{"topic":"stages"}')
    assert understanding.resolve_question('1997年3820的GDP是多少？', settings=settings) == \
        '1997年3820的GDP是多少?'


def test_full_graph_keeps_followup_inside_its_thread(monkeypatch, tmp_path):
    import graph
    from agents import agent_main
    settings = Settings(checkpoint_path=tmp_path / 'question-context.sqlite3')
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    try:
        overview = graph.ask('3820战略工程具体内容', 'conversation-a')
        assert overview['results']['planning']['status'] == 'ok'
        assert '1995' in overview['answer']
        assert '闽江口' in overview['answer']
        assert overview['resolved_question'] == '3820战略工程具体内容'
        followup = graph.ask('那第二阶段呢？', 'conversation-a')
        assert followup['resolved_question'] == '3820战略工程的第二阶段目标是什么？'
        assert followup['results']['planning']['status'] == 'ok'
        assert '2000' in followup['answer']
        comparison = graph.ask('和第一阶段相比有什么变化？', 'conversation-a')
        assert comparison['results']['planning']['status'] == 'ok'
        assert '第一阶段着重' in comparison['answer']
        separate = graph.ask('三个结算是什么？', 'conversation-b')
        assert separate['resolved_question'] == '3820战略工程的三个阶段是什么?'
        assert separate['results']['planning']['status'] == 'ok'
        first = graph.ask('2000年目标是什么？', 'conversation-c')
        assert first['results']['planning']['status'] == 'ok'
        goal_followup = graph.ask('这个目标实现了吗？', 'conversation-c')
        assert goal_followup['results']['evaluation_1']['status'] == 'insufficient_evidence'
        assert '不能' in goal_followup['answer']
        graph.ask('1995年GDP目标是多少？', 'conversation-d')
        graph.ask('那GNP呢？', 'conversation-d')
        both = graph.ask('这些目标都实现了吗？', 'conversation-d')
        assert both['resolved_question'] == '1995年GDP和GNP目标实现了吗？'
        evaluation = next(result for result in both['results'].values()
                          if result['role'] == 'evaluation')
        assert evaluation['status'] == 'ok'
        assert {row['目标'] for row in evaluation['data']} == {204.8, 221}
    finally:
        graph.get_graph.cache_clear()


def test_chat_api_uses_saved_thread_for_short_followup(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app as api
    import graph
    from agents import agent_main
    settings = Settings(checkpoint_path=tmp_path / 'api-context.sqlite3')
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    try:
        with TestClient(api.app) as client:
            first = client.post('/chat', json={
                'thread_id': 'topic-a', 'question': '3820战略工程的三个阶段是什么？'})
            assert first.status_code == 200
            second = client.post('/chat', json={
                'thread_id': 'topic-a', 'question': '那第二阶段呢？'})
            assert second.status_code == 200
            assert second.json()['results']['planning']['status'] == 'ok'
            assert '2000' in second.json()['answer']
            assert second.json()['results']['planning']['sources']
            independent = client.post('/chat', json={
                'thread_id': 'topic-b', 'question': '三个结算是什么？'})
            assert independent.status_code == 200
            assert '1995' in independent.json()['answer']
            for question in ('1995年GDP目标是多少？', '那GNP呢？'):
                assert client.post('/chat', json={
                    'thread_id': 'metric-followup', 'question': question}).status_code == 200
            combined = client.post('/chat', json={
                'thread_id': 'metric-followup', 'question': '这些目标都实现了吗？'})
            assert combined.status_code == 200
            assert '224.2%' in combined.json()['answer']
            assert '226.6%' in combined.json()['answer']
    finally:
        graph.get_graph.cache_clear()

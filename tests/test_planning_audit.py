"""Broad question coverage for the complete offline answer path."""

import json
from pathlib import Path

import pytest

from config import Settings


pytestmark = pytest.mark.offline
CASES = json.loads((Path(__file__).with_name('fixtures') / 'planning_audit_cases.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def offline_runtime():
    import graph
    from agents import agent_main
    from knowledge import knowledge_base

    settings = Settings(vector_max_distance=None)
    original = [(module, module.get_settings) for module in (graph, agent_main, knowledge_base)]
    for module, _ in original:
        module.get_settings = lambda: settings
    yield graph, agent_main
    for module, getter in original:
        module.get_settings = getter


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['question'])
def test_question_audit(offline_runtime, case):
    graph, agent_main = offline_runtime
    question = case['question']
    state = {'question': question, 'sub_tasks': agent_main.split_task(question)}
    if graph.route_node(state) == 'retrieve_node':
        state.update(graph.retrieve_node(state))
    state.update(graph.execute_node(state))
    state.update(graph.answer_node(state))
    answer = state['answer']
    sources = [source for item in state['results'].values() for source in item.get('sources') or []]
    if case.get('unsupported'):
        assert not sources, (question, sources)
        assert all(item['status'] != 'ok' for item in state['results'].values())
        return
    assert sources, question
    assert '暂时无法给出可靠回答' not in answer, question
    assert '资料未提及' not in answer, question
    assert '[资料 ' not in answer, question
    for term in case['contains']:
        assert term in answer, (question, term, answer)

"""The four reported questions should use the supplied material directly."""

from pathlib import Path

import pytest

from config import Settings


pytestmark = pytest.mark.offline


@pytest.fixture
def offline_graph(monkeypatch, tmp_path):
    import graph
    from agents import agent_main
    from knowledge import knowledge_base

    settings = Settings(ark_api_key=None, llm_model=None, embed_model=None,
                        vector_max_distance=None, checkpoint_path=tmp_path / 'reported.sqlite3')
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    monkeypatch.setattr(knowledge_base, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    yield graph
    graph.get_graph.cache_clear()


@pytest.mark.parametrize(('question', 'terms'), [
    ('福州经济技术开发区和老市区分别承担什么作用？', ('福州经济技术开发区', '前导', '老市区', '依托')),
    ('1995年GDP目标和GNP目标有什么区别？', ('204.80', '221', 'GDP', 'GNP', '指南表4')),
    ('1995年福州地区生产总值是多少？', ('464.14', '亿元', '指南表1')),
    ('3820工程分为哪三个阶段？各阶段的目标是什么？', ('1995', '2000', '2010', '翻一番')),
])
def test_reported_question_is_grounded(offline_graph, question, terms):
    result = offline_graph.ask(question, thread_id=question)
    assert all(term in result['answer'] for term in terms)
    assert '待核验' not in result['answer']
    assert '未找到' not in result['answer']
    assert any(item['sources'] for item in result['results'].values())


def test_readme_and_instructions_have_distinct_roles():
    root = Path(__file__).resolve().parents[1]
    readme = (root / 'README.md').read_text(encoding='utf-8')
    instructions = (root / 'docs' / 'project' / 'INSTRUCTION.md').read_text(encoding='utf-8')
    assert '如何运行' in readme
    assert 'serendipity_lin@sjtu.edu.cn' in readme
    assert '# 10 附录' in instructions

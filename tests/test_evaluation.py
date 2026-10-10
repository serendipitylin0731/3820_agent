# tests/test_evaluation.py
def test_gdp_1995_achievement():
    # 1990年GDP 102.40亿元，翻番目标204.80亿元，1995年实际464.14亿元
    from agents.agent_evaluation import compute_achievement
    assert compute_achievement(464.14, 204.80) == 226.6
def test_ratio_direction():
    from agents.agent_evaluation import compute_achievement
    assert compute_achievement(80, 100, direction='down') == 100.0
def test_kb_retrieve(monkeypatch):
    import pytest
    pytest.importorskip('faiss')
    pytest.importorskip('openai')
    pytest.importorskip('pptx')
    from knowledge import knowledge_base
    monkeypatch.setattr(knowledge_base, 'embed_texts', lambda texts: [[0.0, 0.0] for _ in texts])
    chunks = ['1995年翻一番目标']
    index = knowledge_base.build_index(chunks)
    hits = knowledge_base.retrieve(index, chunks, '1995年翻一番目标')
    assert len(hits) >= 1
# 运行：pytest tests/ -v

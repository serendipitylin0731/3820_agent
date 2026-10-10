import pytest
from config import Settings
from knowledge import knowledge_base as kb


def test_rebuild_search_and_stale_mapping(monkeypatch, tmp_path):
    pytest.importorskip('faiss')
    settings = Settings(embed_model='fake-embed', index_path=tmp_path, vector_max_distance=0.1)
    monkeypatch.setattr(kb, 'get_settings', lambda: settings)
    monkeypatch.setattr(kb, 'embed_texts', lambda texts, **kwargs: [[float(len(t) % 7), 1.0] for t in texts])
    sample = kb.load_markdown()[:2]
    monkeypatch.setattr(kb, 'get_knowledge_base', lambda: sample)
    assert kb.rebuild_vector_store() == 2
    result = kb.vector_search(sample[0].content, max_distance=0.1)
    assert result.status == 'ok'
    assert result.hits[0].source.verified is False
    monkeypatch.setattr(kb, 'get_knowledge_base', lambda: sample[:1])
    with pytest.raises(ValueError, match='重建索引'):
        kb.vector_search('问题', max_distance=0.1)

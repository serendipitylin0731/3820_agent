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


def test_close_primary_source_is_kept_with_raw_distance():
    from contracts import KnowledgeHit, SourceRef
    def hit(label, source, score):
        return KnowledgeHit(chunk_id=label, content=label, score=score, score_kind='l2_distance',
                            source=SourceRef(source_file=source, data_version='v1', verified=False))
    candidates = [hit('a', 'secondary', 0.70), hit('b', 'other', 0.75),
                  hit('original', kb.ORIGINAL_ARTICLE_URL, 0.85)]
    chosen = kb._prefer_primary_source(candidates, 2)
    assert [item.chunk_id for item in chosen] == ['original', 'a']
    assert chosen[0].score == 0.85
    assert [item.chunk_id for item in kb._prefer_primary_source(candidates[:-1], 2)] == ['a', 'b']

from contracts import KnowledgeHit, SourceRef
from knowledge.knowledge_base import load_markdown, search


def test_guide_search_has_line_reference():
    hits = load_markdown()
    assert hits
    table = next(hit for hit in hits if '| 地区收入总值（GNP）' in hit.content)
    assert '| 农村居民人均纯收入' in table.content
    result = search('三阶段目标 翻一番', chunks=hits)
    assert result.status == 'ok'
    assert result.hits[0].source.page_or_slide.startswith('L')
    assert result.hits[0].source.verified is True


def test_no_evidence():
    hit = KnowledgeHit(chunk_id='1', content='港口', source=SourceRef(
        source_file='x', data_version='v1', verified=False))
    assert search('量子芯片', chunks=[hit], min_score=0.5).status == 'insufficient_evidence'


def test_stale_vector_index_falls_back_to_text(monkeypatch, tmp_path):
    from config import Settings
    from knowledge import knowledge_base as kb
    (tmp_path / 'index.faiss').write_bytes(b'old')
    hit = KnowledgeHit(chunk_id='guide:layout', content='福州经济技术开发区战略布局',
                       source=SourceRef(source_file='guide.md', data_version='v1', verified=True))
    monkeypatch.setattr(kb, 'get_settings',
                        lambda: Settings(index_path=tmp_path, vector_max_distance=0.1))
    monkeypatch.setattr(kb, 'get_knowledge_base', lambda: [hit])
    monkeypatch.setattr(kb, 'vector_search', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('stale')))
    assert kb.search('福州经济技术开发区战略布局').hits[0].chunk_id == 'guide:layout'


def test_changed_source_reloads_chunks(monkeypatch, tmp_path):
    from config import Settings
    from knowledge import knowledge_base as kb
    guide = tmp_path / 'guide.md'
    guide.write_text('# 1 概述\n旧内容\n', encoding='utf-8')
    monkeypatch.setattr(kb, 'GUIDE', guide)
    monkeypatch.setattr(kb, 'get_settings', lambda: Settings())
    kb._load_knowledge_base.cache_clear()
    old = kb.get_knowledge_base()
    guide.write_text('# 1 概述\n新内容\n', encoding='utf-8')
    new = kb.get_knowledge_base()
    assert old[0].source.data_version != new[0].source.data_version
    assert '新内容' in new[0].content
    kb._load_knowledge_base.cache_clear()

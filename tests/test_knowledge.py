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
    assert result.hits[0].source.verified is False


def test_no_evidence():
    hit = KnowledgeHit(chunk_id='1', content='港口', source=SourceRef(
        source_file='x', data_version='v1', verified=False))
    assert search('量子芯片', chunks=[hit], min_score=0.5).status == 'insufficient_evidence'

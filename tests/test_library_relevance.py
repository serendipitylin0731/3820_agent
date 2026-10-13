"""Search ranking and fuzzy matching against realistic page and title layouts."""

import json

from knowledge import library_search as library


def _catalog(tmp_path, monkeypatch, documents):
    folder = tmp_path / 'knowledge' / 'library' / 'literature'
    folder.mkdir(parents=True)
    entries = []
    for identifier, title, body in documents:
        path = folder / f'{identifier}.md'
        path.write_text(body, encoding='utf-8')
        entries.append({'id': identifier, 'title': title,
                        'path': path.relative_to(tmp_path).as_posix(),
                        'category': 'literature', 'bytes': path.stat().st_size,
                        'searchable': True})
    catalog = tmp_path / 'knowledge' / 'library' / 'catalog.json'
    catalog.write_text(json.dumps({'entries': entries}), encoding='utf-8')
    monkeypatch.setattr(library, 'ROOT', tmp_path)
    monkeypatch.setattr(library, 'CATALOG', catalog)
    library._read_catalog.cache_clear()
    library._text.cache_clear()


def test_title_and_local_phrase_beat_scattered_or_noisy_matches(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch, [
        ('title', '福建的林权制度改革', '# 正文\n\n林业改革的背景。'),
        ('body', '福建改革访谈', '# 正文\n\n集体林权制度改革改善了林农收入。'),
        ('scattered', '福建杂谈', '# 正文\n\n林权问题。\n' + '其他内容。' * 180 + '\n制度改革另行讨论。'),
    ])
    exact = library.search_documents('林权制度改革')
    fuzzy = library.search_documents('林权制改革')
    assert [item['id'] for item in exact[:2]] == ['title', 'body']
    assert [item['id'] for item in fuzzy[:2]] == ['title', 'body']
    assert all(item['id'] != 'scattered' for item in fuzzy)


def test_punctuation_alias_finds_real_page_and_highlights_visible_text(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch, [
        ('plan', '福州发展规划', '# 规划\n\n## 第 1 页\n\n无关文字。\n\n'
         '## 第 2 页\n\n规划了福州的 3 年、8 年、20 年发展步骤。'),
    ])
    result = library.search_documents('三年八年二十年')[0]
    assert result['match_page'] == 2
    assert '3 年、8 年、20 年' in result['snippet']
    assert any('3 年、8 年、20 年' in term for term in result['highlight_terms'])


def test_compound_keywords_can_find_document_without_same_sentence(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch, [
        ('both', '福州对外开放规划', '# 规划\n\n## 第 1 页\n\n港口建设。\n\n'
         '## 第 2 页\n\n扩大对外开放。'),
        ('one', '港口简介', '# 简介\n\n只谈港口建设。'),
    ])
    results = library.search_documents('港口与对外开放')
    assert results[0]['id'] == 'both'
    assert results[0]['match_page'] in {1, 2}
    assert all(item['id'] != 'one' for item in results)


def test_fuzzy_matching_does_not_change_numeric_identifiers(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch, [
        ('plan', '3820战略工程30年回顾', '# 回顾\n\n3820战略工程。'),
    ])
    assert library.search_documents('3830') == []
    assert library.search_documents('382O')[0]['id'] == 'plan'

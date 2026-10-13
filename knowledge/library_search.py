"""Public document catalog: explicit allowlist, keyword ranking and safe file access."""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'knowledge' / 'library' / 'catalog.json'
PUBLIC_CATEGORIES = frozenset({'documents', 'papers', 'literature', 'pdf', 'media'})
TEXT_SUFFIXES = frozenset({'.md', '.txt'})


@lru_cache(maxsize=4)
def _read_catalog(version: int) -> tuple[dict, ...]:
    if not CATALOG.is_file():
        return ()
    records = json.loads(CATALOG.read_text(encoding='utf-8')).get('entries', [])
    return tuple(item for item in records if item.get('searchable') is True
                 and item.get('category') in PUBLIC_CATEGORIES)


def _catalog() -> tuple[dict, ...]:
    return _read_catalog(CATALOG.stat().st_mtime_ns if CATALOG.is_file() else 0)


def _safe_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT) or not (path.is_relative_to(ROOT / 'knowledge' / 'library')
                                             or path.is_relative_to(ROOT / 'docs')):
        raise ValueError('file outside document library')
    return path


def public_record(doc_id: str) -> tuple[dict, Path] | None:
    for item in _catalog():
        if item['id'] == doc_id:
            path = _safe_path(item['path'])
            return (item, path) if path.is_file() else None
    return None


def cited_record(source_file: str) -> tuple[dict, Path] | None:
    """Resolve a chat citation through catalog paths, never an arbitrary file path."""
    if not source_file or len(source_file) > 500:
        return None
    if source_file == 'docs/基于3820战略工程内容的多智能体系统搭建指南.md':
        path = ROOT / source_file
        return ({'title': '基于3820战略工程内容的多智能体系统搭建指南',
                 'category': 'documents',
                 'download_path': 'docs/基于3820战略工程内容的多智能体系统搭建指南.docx'}, path) if path.is_file() else None
    if source_file == 'docs/3820背景.md':
        path = ROOT / source_file
        return ({'title': '3820背景', 'category': 'documents'}, path) if path.is_file() else None
    if not CATALOG.is_file():
        return None
    records = json.loads(CATALOG.read_text(encoding='utf-8')).get('entries', [])
    for item in records:
        if item.get('path') != source_file:
            continue
        if not (item.get('searchable') and item.get('category') in PUBLIC_CATEGORIES) \
                and item.get('category') != 'presentations':
            return None
        path = _safe_path(item['path'])
        if not path.is_file():
            return None
        return item, path
    return None


@lru_cache(maxsize=512)
def _text(path: Path) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding='utf-8-sig', errors='replace')
    if path.suffix.lower() == '.docx':
        from docx import Document
        doc = Document(path)
        return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
    return ''


def _normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).lower()
    value = value.replace('三八二零', '3820').replace('三八二〇', '3820')
    value = re.sub(r'382[o〇零]', '3820', value)
    value = value.replace('二十年', '20年').replace('八年', '8年').replace('三年', '3年')
    return re.sub(r'[^\u4e00-\u9fffa-z0-9]', '', value)


def _terms(query: str) -> list[str]:
    words = re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+', unicodedata.normalize('NFKC', query).lower())
    result = []
    for word in words:
        result.append(word)
        if re.search(r'[\u4e00-\u9fff]', word) and len(word) > 3:
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
    return list(dict.fromkeys(result))


def _snippet(content: str, terms: list[str]) -> str:
    lowered = content.lower()
    locations = [lowered.find(term) for term in terms if len(term) > 1 and term in lowered]
    start = max(0, min(locations) - 75) if locations else 0
    result = re.sub(r'\s+', ' ', content[start:start + 260]).strip()
    return ('…' if start else '') + result + ('…' if start + 260 < len(content) else '')


def _match_context(passage: str, query: str) -> tuple[str, str]:
    """Map a normalized or fuzzy hit back to visible source text."""
    chars, offsets = [], []
    for position, char in enumerate(passage):
        for converted in unicodedata.normalize('NFKC', char).lower():
            if re.match(r'[\u4e00-\u9fffa-z0-9]', converted):
                chars.append(converted)
                offsets.append(position)
    normalized = ''.join(chars)
    for original, replacement in (('三八二零', '3820'), ('三八二〇', '3820'),
                                  ('382o', '3820'), ('二十年', '20年'),
                                  ('八年', '8年'), ('三年', '3年')):
        while original in normalized:
            at = normalized.index(original)
            offsets[at:at + len(original)] = [offsets[at]] * len(replacement)
            normalized = normalized[:at] + replacement + normalized[at + len(original):]
    start = normalized.find(query)
    if start >= 0:
        length = len(query)
    else:
        match = SequenceMatcher(None, query, normalized, autojunk=False).find_longest_match(
            0, len(query), 0, len(normalized))
        start, length = match.b, match.size
    if not offsets or length <= 0 or start >= len(offsets):
        return _snippet(passage, []), ''
    raw_start = offsets[start]
    raw_end = offsets[min(len(offsets) - 1, start + length - 1)] + 1
    context_start = max(0, raw_start - 75)
    context_end = min(len(passage), max(raw_end + 170, context_start + 260))
    excerpt = re.sub(r'\s+', ' ', passage[context_start:context_end]).strip()
    snippet = ('…' if context_start else '') + excerpt + ('…' if context_end < len(passage) else '')
    return snippet, passage[raw_start:raw_end].strip()[:100]


PAGE_HEADING = re.compile(r'(?m)^## 第\s*(\d+)\s*页(?:\s*·[^\n]*)?$')


def _bigrams(value: str) -> set[str]:
    return {value[i:i + 2] for i in range(len(value) - 1)}


def _fuzzy_coverage(query: str, candidate: str) -> float:
    if len(query) < 4 or query.isdigit():
        return 0.0  # Short terms and numeric codes need a literal match.
    grams = _bigrams(query)
    if not grams:
        return 0.0
    return len(grams & _bigrams(candidate)) / len(grams)


def _passages(content: str):
    """Yield small local windows, keeping the real PDF page number when known."""
    markers = list(PAGE_HEADING.finditer(content))
    sections = ((int(marker.group(1)), content[marker.end():markers[index + 1].start()
                if index + 1 < len(markers) else len(content)])
                for index, marker in enumerate(markers)) if markers else ((None, content),)
    for page, section in sections:
        for start in range(0, len(section), 480):
            yield page, section[start:start + 640]


def _passage_score(query: str, passage: str) -> tuple[float, bool]:
    normalized = _normalize(passage)
    if query in normalized:
        return 100.0, True
    coverage = _fuzzy_coverage(query, normalized)
    if coverage < (0.67 if len(query) < 10 else 0.72):
        return 0.0, False
    # A local window must contain a substantial contiguous part of the query;
    # scattered common bigrams across a long OCR page are not enough.
    longest = SequenceMatcher(None, query, normalized, autojunk=False).find_longest_match(
        0, len(query), 0, len(normalized)).size
    if longest < max(2, min(5, len(query) // 3)):
        return 0.0, False
    return 25.0 + coverage * 65.0 + longest / len(query) * 10.0, False


def _best_passage(content: str, query: str) -> tuple[float, int | None, str, bool, str]:
    best = (0.0, None, '', False)
    for page, passage in _passages(content):
        score, exact = _passage_score(query, passage)
        if score > best[0]:
            best = (score, page, passage, exact)
    if not best[0]:
        return 0.0, None, '', False, ''
    snippet, matched = _match_context(best[2], query)
    return best[0], best[1], snippet, best[3], matched


def search_documents(query: str, limit: int = 30) -> list[dict]:
    query = query.strip()[:120]
    if not query:
        return []
    normalized_query = _normalize(query)
    if not normalized_query:
        return []
    terms = _terms(query)
    components = [_normalize(part) for part in re.split(r'[\s,，、;；]+|(?<=[\u4e00-\u9fff])[和与及](?=[\u4e00-\u9fff])', query)]
    components = list(dict.fromkeys(part for part in components if len(part) >= 2))
    ranked = []
    for item in _catalog():
        if item.get('category') == 'pdf' and item.get('text_path'):
            continue  # A single result offers Markdown reading and the original PDF.
        path = _safe_path(item['path'])
        if not path.is_file():
            continue
        title = _normalize(item['title'])
        text_path = _safe_path(item['text_path']) if item.get('text_path') else path
        content = _text(text_path) if text_path.suffix.lower() in TEXT_SUFFIXES | {'.docx'} else ''
        title_score = 0.0
        if normalized_query in title:
            title_score = 210.0 + min(20, len(normalized_query))
        else:
            coverage = _fuzzy_coverage(normalized_query, title)
            if coverage >= (0.65 if len(normalized_query) < 10 else 0.72):
                ratio = SequenceMatcher(None, normalized_query, title, autojunk=False).ratio()
                if ratio >= 0.35:
                    title_score = 75.0 + coverage * 85.0 + ratio * 20.0
        if normalized_query == '3年8年20年' and '3820' in title:
            title_score = max(title_score, 160.0)
        if normalized_query == '二十大报告' and '第二十次全国代表大会' in title and '报告' in title:
            title_score = max(title_score, 210.0)
        passage_score, match_page, snippet, exact, matched_text = (
            _best_passage(content, normalized_query) if content else (0.0, None, '', False, ''))
        normalized_content = _normalize(content) if content else ''
        if (not title_score and not passage_score and len(components) > 1 and
                all(part in normalized_content for part in components)):
            passage_score = 20.0 + sum(min(10, normalized_content.count(part)) for part in components)
            _, match_page, snippet, _, matched_text = _best_passage(content, max(components, key=len))
        if title_score or passage_score:
            # One strong local hit outweighs a long document's repeated weak hits.
            # Repeated exact mentions can break ties without dominating the ranking.
            exact_mentions = min(4, normalized_content.count(normalized_query)) if exact else 0
            score = max(title_score, passage_score + exact_mentions * 5)
            if title_score and passage_score:
                score += min(12.0, passage_score / 10.0)
            if (item['category'] == 'media' and
                    Path(item['path']).name.startswith('原件扫描_page_') and
                    not any(term in query for term in ('图片', '图像', '扫描', '第', '页'))):
                score *= 0.55  # Keep page images available without crowding their parent document.
            lowered = content.lower()
            highlights = ([query] if query.lower() in lowered else
                          sorted((term for term in terms if len(term) > 1 and term in lowered),
                                 key=len, reverse=True)[:6])
            if matched_text and matched_text not in highlights:
                highlights.insert(0, matched_text)
            if '3820' in normalized_query and '3820' in lowered and '3820' not in highlights:
                highlights.insert(0, '3820')
            result = {key: item[key] for key in ('id', 'title', 'category', 'bytes')}
            result.update({'snippet': snippet, 'format': path.suffix.lower().lstrip('.') or 'file',
                           'match_page': match_page,
                           'page_count': max(item.get('pages', []), default=0),
                           'indexed_page_count': len(item.get('pages', [])),
                           'collection': item.get('collection'), 'source_url': item.get('source_url'),
                           'pdf_id': item.get('pdf_id'), 'highlight_terms': highlights})
            ranked.append((score, result))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]['title']))
    selected = []
    for _, item in ranked:
        selected.append(item)
        if len(selected) >= max(1, min(limit, 50)):
            break
    return selected


def preview_text(item: dict, path: Path) -> str | None:
    if path.suffix.lower() in TEXT_SUFFIXES | {'.docx'}:
        return _text(path)
    return None


def media_text(item: dict) -> str | None:
    if item.get('category') != 'media' or not item.get('text_path'):
        return None
    path = _safe_path(item['text_path'])
    return _text(path) if path.is_file() else None


def download_file(item: dict, path: Path) -> Path:
    value = item.get('download_path')
    if value:
        candidate = _safe_path(value)
        if candidate.is_file():
            return candidate
    if path.suffix.lower() == '.md':
        raise FileNotFoundError('Word download has not been generated')
    return path

"""Public document catalog: explicit allowlist, keyword ranking and safe file access."""
from __future__ import annotations

import json
import re
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


@lru_cache(maxsize=512)
def _text(path: Path) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding='utf-8-sig', errors='replace')
    if path.suffix.lower() == '.docx':
        from docx import Document
        doc = Document(path)
        return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
    return ''


def _terms(query: str) -> list[str]:
    words = re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+', query.lower())
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


PAGE_HEADING = re.compile(r'(?m)^## 第\s*(\d+)\s*页(?:\s*·[^\n]*)?$')


def _best_page(content: str, query: str, terms: list[str]) -> tuple[int | None, str]:
    markers = list(PAGE_HEADING.finditer(content))
    if not markers:
        return None, _snippet(content, terms)
    best = (0, 0, '')
    for index, marker in enumerate(markers):
        section = content[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(content)]
        lowered = section.lower()
        score = (20 if query.lower() in lowered else 0) + sum(min(lowered.count(term), 3)
                                                              for term in terms if len(term) > 1)
        if score > best[0]:
            best = (score, int(marker.group(1)), _snippet(section, terms))
    if best[0]:
        return best[1], best[2]
    return int(markers[0].group(1)), _snippet(content[markers[0].end():], terms)


def search_documents(query: str, limit: int = 30) -> list[dict]:
    query = query.strip()[:120]
    if not query:
        return []
    terms = _terms(query)
    ranked = []
    for item in _catalog():
        if item.get('category') == 'pdf' and item.get('text_path'):
            continue  # A single result offers Markdown reading and the original PDF.
        path = _safe_path(item['path'])
        if not path.is_file():
            continue
        title = item['title'].lower()
        text_path = _safe_path(item['text_path']) if item.get('text_path') else path
        content = _text(text_path) if text_path.suffix.lower() in TEXT_SUFFIXES | {'.docx'} else ''
        lowered = content.lower()
        score = sum(12 if term in title else 0 for term in terms)
        score += sum(min(4, lowered.count(term)) for term in terms if len(term) > 1)
        if query.lower() in title:
            score += 30
        if query.lower() in lowered:
            score += 15
        if item['category'] != 'media':
            score += 8 if score else 0
        if score:
            match_page, snippet = _best_page(content, query, terms) if content else (None, '')
            highlights = ([query] if query.lower() in lowered else
                          sorted((term for term in terms if len(term) > 1 and term in lowered),
                                 key=len, reverse=True)[:5])
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


def download_file(item: dict, path: Path) -> Path:
    value = item.get('download_path')
    if value:
        candidate = _safe_path(value)
        if candidate.is_file():
            return candidate
    if path.suffix.lower() == '.md':
        raise FileNotFoundError('Word download has not been generated')
    return path

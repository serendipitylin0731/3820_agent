import json
from hashlib import sha256

from fastapi.testclient import TestClient

import app as api
from config import Settings
from knowledge import library_search as library


def test_public_search_preview_download_and_private_exclusions(tmp_path, monkeypatch):
    root = tmp_path
    public = root / 'knowledge' / 'library' / 'papers'
    private = root / 'knowledge' / 'library' / 'courses'
    slides = root / 'knowledge' / 'library' / 'presentations'
    for folder in (public, private, slides):
        folder.mkdir(parents=True)
    paper = public / '3820战略论文.md'
    paper.write_text('# 3820战略论文\n\n闽江口金三角经济圈有明确的空间布局。', encoding='utf-8')
    (public / '3820战略论文.docx').write_bytes(b'word-download')
    course = private / '闽江口教学案例.md'
    course.write_text('闽江口课程资料', encoding='utf-8')
    ppt = slides / '闽江口课件.pptx'
    ppt.write_bytes(b'ppt-file')

    def item(path, category, identifier, searchable):
        return {'id': identifier, 'title': path.stem, 'path': path.relative_to(root).as_posix(),
                'category': category, 'bytes': path.stat().st_size,
                'sha256': sha256(path.read_bytes()).hexdigest(), 'searchable': searchable,
                'download_path': (public / '3820战略论文.docx').relative_to(root).as_posix() if identifier == 'paper' else None}

    catalog = root / 'knowledge' / 'library' / 'catalog.json'
    catalog.write_text(json.dumps({'entries': [item(paper, 'papers', 'paper', True),
                                                item(course, 'courses', 'course', False),
                                                item(ppt, 'presentations', 'ppt', False)]}), encoding='utf-8')
    monkeypatch.setattr(library, 'ROOT', root)
    monkeypatch.setattr(library, 'CATALOG', catalog)
    library._read_catalog.cache_clear()
    library._text.cache_clear()
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    try:
        with TestClient(api.app) as client:
            response = client.get('/library/search', params={'q': '闽江口'})
            assert response.status_code == 200
            assert [item['id'] for item in response.json()['results']] == ['paper']
            assert '金三角' in response.json()['results'][0]['snippet']
            assert client.get('/library/paper/preview').json()['content'].startswith('# 3820战略论文')
            download = client.get('/library/paper/download')
            assert download.content == b'word-download'
            assert 'attachment' in download.headers['content-disposition']
            for identifier in ('course', 'ppt', '..', 'missing'):
                assert client.get(f'/library/{identifier}/download').status_code == 404
                assert client.get(f'/library/{identifier}/preview').status_code == 404
    finally:
        library._read_catalog.cache_clear()
        library._text.cache_clear()

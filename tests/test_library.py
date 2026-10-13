import json
from hashlib import sha256

from fastapi.testclient import TestClient

import app as api
from config import Settings
from knowledge import library_search as library
from scripts.organize_library import sanitize_markdown, clean_title


def test_public_search_preview_download_and_private_exclusions(tmp_path, monkeypatch):
    root = tmp_path
    public = root / 'knowledge' / 'library' / 'papers'
    private = root / 'knowledge' / 'library' / 'courses'
    slides = root / 'knowledge' / 'library' / 'presentations'
    media = root / 'knowledge' / 'library' / 'media'
    derived = root / 'knowledge' / 'library' / 'derived'
    for folder in (public, private, slides, media, derived):
        folder.mkdir(parents=True)
    paper = public / '3820战略论文.md'
    paper.write_text('# 3820战略论文\n\n闽江口金三角经济圈有明确的空间布局。', encoding='utf-8')
    (public / '3820战略论文.docx').write_bytes(b'word-download')
    course = private / '闽江口教学案例.md'
    course.write_text('闽江口课程资料', encoding='utf-8')
    ppt = slides / '闽江口课件.pptx'
    ppt.write_bytes(b'ppt-file')
    image = media / '闽江口规划.png'
    image.write_bytes(b'png-file')
    video = media / '闽江口纪录.mp4'
    video.write_bytes(b'mp4-file')
    (derived / 'image.txt').write_text('# 闽江口规划\n\n图片显示沿江布局', encoding='utf-8')
    (derived / 'video.txt').write_text('# 闽江口纪录\n\n[音频 00:00:03] 闽江口规划', encoding='utf-8')

    def item(path, category, identifier, searchable):
        return {'id': identifier, 'title': path.stem, 'path': path.relative_to(root).as_posix(),
                'category': category, 'bytes': path.stat().st_size,
                'sha256': sha256(path.read_bytes()).hexdigest(), 'searchable': searchable,
                'download_path': (public / '3820战略论文.docx').relative_to(root).as_posix() if identifier == 'paper' else None}

    catalog = root / 'knowledge' / 'library' / 'catalog.json'
    image_item = item(image, 'media', 'image', True)
    video_item = item(video, 'media', 'video', True)
    image_item['text_path'] = 'knowledge/library/derived/image.txt'
    video_item['text_path'] = 'knowledge/library/derived/video.txt'
    catalog.write_text(json.dumps({'entries': [item(paper, 'papers', 'paper', True),
                                                item(course, 'courses', 'course', False),
                                                item(ppt, 'presentations', 'ppt', False),
                                                image_item, video_item]}), encoding='utf-8')
    monkeypatch.setattr(library, 'ROOT', root)
    monkeypatch.setattr(library, 'CATALOG', catalog)
    library._read_catalog.cache_clear()
    library._text.cache_clear()
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    try:
        with TestClient(api.app) as client:
            response = client.get('/library/search', params={'q': '闽江口'})
            assert response.status_code == 200
            assert {'paper', 'image', 'video'} <= {item['id'] for item in response.json()['results']}
            assert any('金三角' in item['snippet'] for item in response.json()['results'])
            assert client.get('/library/paper/preview').json()['content'].startswith('# 3820战略论文')
            download = client.get('/library/paper/download')
            assert download.content == b'word-download'
            assert 'attachment' in download.headers['content-disposition']
            assert client.get('/library/image/preview').status_code == 200
            assert '沿江布局' in client.get('/library/image/text').json()['content']
            assert client.get('/library/video/download').content == b'mp4-file'
            assert '00:00:03' in client.get('/library/video/text').json()['content']
            for identifier in ('course', 'ppt', '..', 'missing'):
                assert client.get(f'/library/{identifier}/download').status_code == 404
                assert client.get(f'/library/{identifier}/preview').status_code == 404
    finally:
        library._read_catalog.cache_clear()
        library._text.cache_clear()


def test_importer_metadata_is_not_exposed_and_real_pages_are_retained():
    raw = '''# 习近平总书记关于党的建设的重要思想概论 (中共中央组织部) (z-library.sk)

来源：微信压缩包内 PDF（214 页）
提取方式：OCR 自动转写
【第1页】第一章 党的建设
第一段文字换行
继续叙述。
【第2页】第二章 基层治理
涉及林权制度改革。
'''
    clean, title, source, pages = sanitize_markdown(raw)
    assert title == '习近平总书记关于党的建设的重要思想概论 (中共中央组织部)'
    assert source is None
    assert pages == [1, 2]
    assert '微信压缩包' not in clean and '提取方式' not in clean
    assert '## 第 2 页' in clean and '第一段文字换行继续叙述。' in clean
    assert clean_title('文献 (z-library.sk)') == '文献'


def test_search_picks_matching_page_and_does_not_repeat_paired_pdf(tmp_path, monkeypatch):
    root = tmp_path
    folder = root / 'knowledge' / 'library' / 'literature'
    pdf_folder = root / 'knowledge' / 'library' / 'pdf'
    folder.mkdir(parents=True)
    pdf_folder.mkdir(parents=True)
    article = folder / '原文.md'
    article.write_text('# 原文\n\n## 第 1 页\n\n别的内容。\n\n## 第 2 页\n\n林权制度改革的内容。\n', encoding='utf-8')
    pdf = pdf_folder / '原文.pdf'
    pdf.write_bytes(b'%PDF-mock')
    catalog = root / 'knowledge' / 'library' / 'catalog.json'
    catalog.write_text(json.dumps({'entries': [
        {'id': 'text', 'title': '原文', 'path': article.relative_to(root).as_posix(),
         'category': 'literature', 'bytes': article.stat().st_size, 'searchable': True,
         'pages': [1, 2], 'pdf_id': 'pdf'},
        {'id': 'pdf', 'title': '原文', 'path': pdf.relative_to(root).as_posix(),
         'text_path': article.relative_to(root).as_posix(), 'category': 'pdf',
         'bytes': pdf.stat().st_size, 'searchable': True, 'pages': [1, 2]},
    ]}), encoding='utf-8')
    monkeypatch.setattr(library, 'ROOT', root)
    monkeypatch.setattr(library, 'CATALOG', catalog)
    library._read_catalog.cache_clear()
    library._text.cache_clear()
    try:
        results = library.search_documents('林权制度改革')
        assert len(results) == 1
        assert results[0]['match_page'] == 2
        assert results[0]['page_count'] == 2
        assert results[0]['indexed_page_count'] == 2
        assert results[0]['pdf_id'] == 'pdf'
        assert results[0]['highlight_terms']
    finally:
        library._read_catalog.cache_clear()
        library._text.cache_clear()

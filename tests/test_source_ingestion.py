from pathlib import Path
from zipfile import ZipFile

from pptx import Presentation

from config import Settings
from knowledge import knowledge_base as kb


def test_ppt_keeps_actual_slide_number(tmp_path):
    path = tmp_path / 'slides.ppt'
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = '三年目标'
    prs.save(path)
    chunks = kb.load_ppt_chunks(path)
    assert len(chunks) == 1
    assert chunks[0].source.page_or_slide == 2
    assert chunks[0].content == '三年目标'


def test_word_uses_paragraph_and_table_positions(tmp_path):
    path = tmp_path / 'source.doc'
    document = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>福州</w:t></w:r></w:p>'
                '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>指标</w:t></w:r></w:p></w:tc>'
                '<w:tc><w:p><w:r><w:t>1995</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                '</w:body></w:document>')
    with ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', document)
    chunks = kb.load_word_chunks(path)
    assert [hit.content for hit in chunks] == ['福州', '指标 | 1995']
    assert [hit.source.page_or_slide for hit in chunks] == ['段落1', '段落2']


def test_duplicate_deck_is_excluded(tmp_path, monkeypatch):
    for name in ('3820PPT+视频.ppt', '3820视频.pptx'):
        (tmp_path / name).touch()
    monkeypatch.setattr(kb, 'DATA_DIR', tmp_path)
    paths = kb._source_paths(Settings())
    assert [path.name for path in paths] == ['3820视频.pptx']


def test_scan_ocr_page_retains_preview_page_and_unverified_status(tmp_path):
    path = tmp_path / 'page_0037.txt'
    path.write_text('1995 年主要指标翻一番', encoding='utf-8')
    chunks = kb.load_scan_page_chunk(path, {'article_url': 'https://example.test/original'})
    assert chunks[0].source.page_or_slide == '预览第37页'
    assert chunks[0].source.source_file == 'https://example.test/original'
    assert chunks[0].source.verified is False


def test_vision_embedding_uses_multimodal_endpoint_and_query_instruction():
    class Client:
        def __init__(self):
            self.calls = []

        def post(self, path, **kwargs):
            self.calls.append((path, kwargs))
            return {'data': {'embedding': [1.0, 2.0]}}

    client = Client()
    settings = Settings(embed_model='doubao-embedding-vision-251215')
    assert kb.embed_texts(['文档'], settings=settings, client=client) == [[1.0, 2.0]]
    assert kb.embed_texts(['问题'], settings=settings, client=client, role='query') == [[1.0, 2.0]]
    assert all(path == '/embeddings/multimodal' for path, _ in client.calls)
    assert client.calls[0][1]['body']['instructions'] != client.calls[1][1]['body']['instructions']

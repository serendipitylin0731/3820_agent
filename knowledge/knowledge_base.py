"""带来源的知识切片、离线文本检索和可选向量索引。"""
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import Lock
from xml.etree import ElementTree
from zipfile import ZipFile

from contracts import KnowledgeHit, KnowledgeResult, SourceRef
from config import Settings, get_settings
from resilience import transient_error
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

GUIDE = Path(__file__).resolve().parent.parent / 'docs' / '基于3820战略工程内容的多智能体系统搭建指南.md'
DATA_DIR = Path(__file__).resolve().parent / 'data'
WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
EMBEDDING_SCHEMA = 2
_retrieval_counts = Counter()
_retrieval_lock = Lock()


def retrieval_metrics():
    with _retrieval_lock:
        return dict(_retrieval_counts)


def _record_retrieval(status, low_relevance=False):
    with _retrieval_lock:
        _retrieval_counts['requests'] += 1
        _retrieval_counts[status] += 1
        if low_relevance:
            _retrieval_counts['low_relevance'] += 1


def _version(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def load_markdown(path=GUIDE):
    path = Path(path)
    lines = path.read_text(encoding='utf-8').splitlines()
    chunks, heading, block, start = [], '', [], 1
    in_code = False
    started = False
    table_mode = False
    def flush():
        if not block:
            return
        content = '\n'.join(block).strip()
        if content:
            display_path = str(path.relative_to(GUIDE.parent.parent)) if path.is_relative_to(GUIDE.parent.parent) else path.name
            source = SourceRef(source_file=display_path, page_or_slide=f'L{start}',
                               section=heading or None, data_version=_version(path), verified=False)
            chunks.append(KnowledgeHit(chunk_id=f'{path.name}:{start}', content=content, source=source))
        block.clear()
    for line_no, line in enumerate(lines, 1):
        if not started:
            if re.match(r'^# 1\b', line):
                started = True
            else:
                continue
        if line.lstrip().startswith(('```', '~~~')):
            in_code = not in_code
            continue
        if line.startswith('<a id='):
            continue
        if in_code or line.startswith('# ') and re.match(r'# (?:3|4|5|6|7|8|9|10)\b', line):
            if not in_code and line.startswith('# '):
                break
            continue
        is_table_row = line.lstrip().startswith('|')
        if is_table_row and not table_mode:
            flush(); table_mode = True
        elif table_mode and not is_table_row:
            flush(); table_mode = False
        if re.match(r'^#{1,4} \d', line):
            flush(); heading = line.lstrip('# ').strip(); start = line_no
        if not block:
            start = line_no
        if line.strip():
            block.append(line.strip())
        if not table_mode and sum(map(len, block)) >= 700:
            flush()
    flush()
    return chunks


def load_ppt_text(path):
    from pptx import Presentation
    prs = Presentation(path)
    chunks = []
    for idx, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, 'has_text_frame', False) and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
            if getattr(shape, 'has_table', False):
                for row in shape.table.rows:
                    texts.append(' | '.join(cell.text.strip() for cell in row.cells))
        if texts:
            chunks.append(f'[第{idx}页] ' + '\n'.join(texts))
    return chunks


def load_ppt_chunks(path):
    path = Path(path)
    from pptx import Presentation
    version = _version(path)
    chunks = []
    for n, slide in enumerate(Presentation(path).slides, 1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, 'has_text_frame', False) and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
            if getattr(shape, 'has_table', False):
                texts.extend(' | '.join(cell.text.strip() for cell in row.cells)
                             for row in shape.table.rows)
        content = '\n'.join(texts).strip()
        if content:
            chunks.append(KnowledgeHit(chunk_id=f'{path.name}:slide:{n}', content=content,
                                       source=SourceRef(source_file=_display_path(path), page_or_slide=n,
                                                        data_version=version, verified=False)))
    return chunks


def _display_path(path):
    path = Path(path)
    root = GUIDE.parent.parent
    return str(path.relative_to(root)) if path.is_relative_to(root) else path.name


def load_word_chunks(path):
    """读取 OOXML Word 的段落和表格；按文件内容识别，不依赖 .docx 后缀。"""
    path = Path(path)
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read('word/document.xml'))
    body = root.find(f'{WORD_NS}body')
    if body is None:
        return []
    version = _version(path)
    chunks = []
    paragraph_no = 0
    for element in body:
        if element.tag == f'{WORD_NS}p':
            paragraph_no += 1
            content = ''.join(node.text or '' for node in element.iter(f'{WORD_NS}t')).strip()
        elif element.tag == f'{WORD_NS}tbl':
            rows = []
            for row in element.iter(f'{WORD_NS}tr'):
                cells = [''.join(t.text or '' for t in cell.iter(f'{WORD_NS}t')).strip()
                         for cell in row.iter(f'{WORD_NS}tc')]
                if any(cells):
                    rows.append(' | '.join(cells))
            content = '\n'.join(rows).strip()
            paragraph_no += 1
        else:
            continue
        if content:
            chunks.append(KnowledgeHit(chunk_id=f'{path.name}:paragraph:{paragraph_no}', content=content,
                                       source=SourceRef(source_file=_display_path(path),
                                                        page_or_slide=f'段落{paragraph_no}',
                                                        data_version=version, verified=False)))
    return chunks


def load_public_text_chunks(path, metadata):
    path = Path(path)
    content = path.read_text(encoding='utf-8')
    version = _version(path)
    chunks = []
    for n, paragraph in enumerate(content.split('\n\n'), 1):
        paragraph = paragraph.strip()
        if paragraph:
            chunks.append(KnowledgeHit(chunk_id=f'{path.stem}:paragraph:{n}', content=paragraph,
                                       source=SourceRef(source_file=metadata.get('url', _display_path(path)),
                                                        page_or_slide=f'段落{n}', section=metadata.get('title'),
                                                        data_version=version, verified=False)))
    return chunks


def _source_paths(settings):
    files = [path for path in DATA_DIR.iterdir() if path.is_file() and path.suffix.lower() in
             {'.ppt', '.pptx', '.doc', '.docx'}] if DATA_DIR.is_dir() else []
    if settings.ppt_path and settings.ppt_path.is_file():
        files.append(settings.ppt_path)
    # 两份演示文稿的 29 页文字完全重复；保留页码齐全的 PPTX。
    names = {path.name for path in files}
    if '3820视频.pptx' in names:
        files = [path for path in files if path.name != '3820PPT+视频.ppt']
    public_dir = DATA_DIR / 'public_sources'
    if public_dir.is_dir():
        files.extend(public_dir.glob('*.txt'))
        if (public_dir / 'manifest.json').is_file():
            files.append(public_dir / 'manifest.json')
    return tuple(sorted({path.resolve() for path in files}, key=str))


def get_knowledge_base():
    settings = get_settings()
    paths = _source_paths(settings)
    signatures = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    return _load_knowledge_base(_version(GUIDE), signatures)


@lru_cache(maxsize=4)
def _load_knowledge_base(_guide_version, signatures):
    hits = load_markdown(GUIDE)
    public_dir = DATA_DIR / 'public_sources'
    manifest_path = public_dir / 'manifest.json'
    metadata = ({item['id']: item for item in json.loads(manifest_path.read_text(encoding='utf-8'))}
                if manifest_path.is_file() else {})
    for name, _, _ in signatures:
        path = Path(name)
        if path.suffix.lower() in {'.ppt', '.pptx'}:
            hits.extend(load_ppt_chunks(path))
        elif path.suffix.lower() in {'.doc', '.docx'}:
            hits.extend(load_word_chunks(path))
        elif path.suffix.lower() == '.txt':
            hits.extend(load_public_text_chunks(path, metadata.get(path.stem, {})))
    return hits


def _tokens(text):
    chars = re.findall(r'[\u4e00-\u9fff]|[A-Za-z0-9]+', text.lower())
    return set(chars + [chars[i] + chars[i+1] for i in range(len(chars)-1)])


def search(query, *, chunks=None, top_k=5, min_score=0.35):
    if top_k < 1 or not query.strip():
        _record_retrieval('insufficient_evidence')
        return KnowledgeResult(status='insufficient_evidence')
    settings = get_settings()
    if chunks is None and settings.vector_max_distance is not None and (settings.index_path / 'index.faiss').is_file():
        result = vector_search(query, top_k=top_k, max_distance=settings.vector_max_distance,
                               directory=settings.index_path)
        _record_retrieval(result.status)
        return result
    chunks = get_knowledge_base() if chunks is None else chunks
    query_tokens = _tokens(query)
    ranked = []
    for hit in chunks:
        overlap = len(query_tokens & _tokens(hit.content))
        score = overlap / max(1, len(query_tokens))
        if score >= min_score:
            ranked.append((score, hit))
    ranked.sort(key=lambda x: x[0], reverse=True)
    hits = [hit.model_copy(update={'score': round(score, 4), 'score_kind': 'similarity'})
            for score, hit in ranked[:top_k]]
    result = KnowledgeResult(status='ok', hits=hits) if hits else KnowledgeResult(status='insufficient_evidence')
    _record_retrieval(result.status, low_relevance=not hits and any(_tokens(query) & _tokens(hit.content) for hit in chunks))
    return result


def format_context(result):
    if result.status != 'ok':
        return '知识库暂无充分依据。'
    return '\n\n'.join(f'[{hit.source.section or "资料"} {hit.source.page_or_slide}; '
                       f'verified={str(hit.source.verified).lower()}] {hit.content}' for hit in result.hits)


def retrieve_context(query, top_k=None):
    result = search(query, top_k=top_k or get_settings().top_k)
    return format_context(result)


def get_client(settings: Settings | None = None):
    from openai import OpenAI
    settings = settings or get_settings()
    return OpenAI(base_url=settings.ark_base_url, api_key=settings.require_api_key(),
                  timeout=settings.request_timeout)


def embed_texts(texts, *, settings: Settings | None = None, client=None, role='document'):
    settings = settings or get_settings()
    active_client = client or get_client(settings)
    model = settings.require_embed_model()
    if model.startswith('doubao-embedding-vision-'):
        if role not in {'document', 'query'}:
            raise ValueError('向量角色必须是 document 或 query')
        instructions = ('Target_modality: text.\nInstruction:从资料中检索能回答问题的内容\nQuery:'
                        if role == 'query' else
                        'Target_modality: text.\nInstruction:为中文资料建立可供问答检索的索引\nQuery:')
        def embed_one(item):
            body = {'model': model, 'input': [{'type': 'text', 'text': item}],
                    'encoding_format': 'float'}
            if model >= 'doubao-embedding-vision-251215':
                body['instructions'] = instructions
            for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8),
                                    retry=retry_if_exception(transient_error), reraise=True):
                with attempt:
                    response = active_client.post('/embeddings/multimodal', cast_to=dict, body=body,
                                                  options={'timeout': settings.request_timeout})
            embedding = response.get('data', {}).get('embedding')
            if not isinstance(embedding, list) or not embedding:
                raise ValueError('向量服务未返回稠密向量')
            return embedding
        if len(texts) < 2:
            return [embed_one(item) for item in texts]
        with ThreadPoolExecutor(max_workers=min(4, len(texts))) as executor:
            return list(executor.map(embed_one, texts))
    response = active_client.embeddings.create(model=model, input=texts,
                                               timeout=settings.request_timeout)
    return [item.embedding for item in response.data]


def build_index(chunks):
    import faiss
    import numpy as np
    if not chunks:
        raise ValueError('知识库没有可索引的文本片段')
    vectors = np.asarray(embed_texts(chunks), dtype='float32')
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks) or not vectors.shape[1]:
        raise ValueError('向量数量或维度与知识片段不一致')
    index = faiss.IndexFlatL2(vectors.shape[1]); index.add(vectors)
    return index


def retrieve(index, chunks, query, top_k=5):
    import numpy as np
    if index is None or not chunks or not index.ntotal or top_k <= 0:
        return []
    top_k = min(top_k, index.ntotal, len(chunks))
    vector = np.asarray(embed_texts([query], role='query'), dtype='float32')
    if vector.ndim != 2 or vector.shape[1] != index.d:
        raise ValueError('查询向量维度与索引不一致')
    distances, ids = index.search(vector, top_k)
    return [(chunks[i], float(distances[0][j])) for j, i in enumerate(ids[0]) if 0 <= i < len(chunks)]


def rebuild_vector_store(directory=None):
    """基于当前资料生成向量索引和完整来源映射。"""
    settings = get_settings()
    hits = get_knowledge_base()
    index = build_index([hit.content for hit in hits])
    directory = directory or settings.index_path
    import faiss
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(directory / 'index.faiss'))
    metadata = {'model': settings.require_embed_model(), 'embedding_schema': EMBEDDING_SCHEMA,
                'hits': [hit.model_dump() for hit in hits]}
    (directory / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    return len(hits)


def vector_search(query, *, top_k=5, max_distance, directory=None):
    """索引版本、模型和片段位置必须与当前资料一致。"""
    import faiss
    import numpy as np
    settings = get_settings()
    directory = Path(directory or settings.index_path)
    metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    current = get_knowledge_base()
    saved = [KnowledgeHit.model_validate(item) for item in metadata['hits']]
    if (metadata['model'] != settings.require_embed_model() or
            metadata.get('embedding_schema') != EMBEDDING_SCHEMA or
            [h.model_dump() for h in saved] != [h.model_dump() for h in current]):
        raise ValueError('资料或向量模型已变化，请重建索引')
    index = faiss.read_index(str(directory / 'index.faiss'))
    if index.ntotal != len(saved):
        raise ValueError('索引和来源映射数量不一致')
    vector = np.asarray(embed_texts([query], role='query'), dtype='float32')
    if vector.ndim != 2 or vector.shape[1] != index.d:
        raise ValueError('查询向量维度与索引不一致')
    distances, ids = index.search(vector, min(top_k, index.ntotal))
    hits = [saved[i].model_copy(update={'score': float(distances[0][j]), 'score_kind':'l2_distance'})
            for j, i in enumerate(ids[0]) if i >= 0 and distances[0][j] <= max_distance]
    return KnowledgeResult(status='ok', hits=hits) if hits else KnowledgeResult(status='insufficient_evidence')


if __name__ == '__main__':
    print(f'索引片段数：{rebuild_vector_store()}')

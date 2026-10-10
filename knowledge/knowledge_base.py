"""带来源的知识切片、离线文本检索和可选向量索引。"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from contracts import KnowledgeHit, KnowledgeResult, SourceRef
from config import Settings, get_settings

GUIDE = Path(__file__).resolve().parent.parent / 'docs' / '基于3820战略工程内容的多智能体系统搭建指南.md'


def _version(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def load_markdown(path=GUIDE):
    path = Path(path)
    lines = path.read_text(encoding='utf-8').splitlines()
    chunks, heading, block, start = [], '', [], 1
    in_code = False
    started = False
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
        if in_code or line.startswith('# ') and re.match(r'# (?:3|4|5|6|7|8|9|10)\b', line):
            if not in_code and line.startswith('# '):
                break
            continue
        if re.match(r'^#{1,4} \d', line):
            flush(); heading = line.lstrip('# ').strip(); start = line_no
        if not block:
            start = line_no
        if line.strip():
            block.append(line.strip())
        if sum(map(len, block)) >= 700:
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
    return [KnowledgeHit(chunk_id=f'{path.name}:{n}', content=text,
                         source=SourceRef(source_file=str(path), page_or_slide=n,
                                          data_version=_version(path), verified=False))
            for n, text in enumerate(load_ppt_text(path), 1)]


@lru_cache(maxsize=1)
def get_knowledge_base():
    settings = get_settings()
    if settings.ppt_path and settings.ppt_path.is_file():
        return load_ppt_chunks(settings.ppt_path)
    return load_markdown()


def _tokens(text):
    chars = re.findall(r'[\u4e00-\u9fff]|[A-Za-z0-9]+', text.lower())
    return set(chars + [chars[i] + chars[i+1] for i in range(len(chars)-1)])


def search(query, *, chunks=None, top_k=5, min_score=0.35):
    if top_k < 1 or not query.strip():
        return KnowledgeResult(status='insufficient_evidence')
    settings = get_settings()
    if chunks is None and settings.vector_max_distance is not None and (settings.index_path / 'index.faiss').is_file():
        return vector_search(query, top_k=top_k, max_distance=settings.vector_max_distance,
                             directory=settings.index_path)
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
    return KnowledgeResult(status='ok', hits=hits) if hits else KnowledgeResult(status='insufficient_evidence')


def retrieve_context(query, top_k=None):
    top_k = top_k or get_settings().top_k
    result = search(query, top_k=top_k)
    if result.status != 'ok':
        return '知识库暂无充分依据。'
    return '\n\n'.join(f'[{hit.source.section or "资料"} {hit.source.page_or_slide}; '
                       f'verified={str(hit.source.verified).lower()}] {hit.content}' for hit in result.hits)


def get_client(settings: Settings | None = None):
    from openai import OpenAI
    settings = settings or get_settings()
    return OpenAI(base_url=settings.ark_base_url, api_key=settings.require_api_key(),
                  timeout=settings.request_timeout)


def embed_texts(texts, *, settings: Settings | None = None, client=None):
    settings = settings or get_settings()
    active_client = client or get_client(settings)
    response = active_client.embeddings.create(model=settings.require_embed_model(), input=texts,
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
    vector = np.asarray(embed_texts([query]), dtype='float32')
    if vector.ndim != 2 or vector.shape[1] != index.d:
        raise ValueError('查询向量维度与索引不一致')
    distances, ids = index.search(vector, top_k)
    return [(chunks[i], float(distances[0][j])) for j, i in enumerate(ids[0]) if 0 <= i < len(chunks)]


def save_index(index, chunks, directory):
    import faiss
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    if index.ntotal != len(chunks):
        raise ValueError('向量数量与片段数量不一致')
    faiss.write_index(index, str(directory / 'index.faiss'))
    (directory / 'metadata.json').write_text(json.dumps({'chunks': chunks}, ensure_ascii=False), encoding='utf-8')


def load_index(directory):
    import faiss
    directory = Path(directory)
    chunks = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))['chunks']
    index = faiss.read_index(str(directory / 'index.faiss'))
    if index.ntotal != len(chunks):
        raise ValueError('索引与元数据不匹配')
    return index, chunks


def rebuild_vector_store(directory=None):
    """基于当前资料生成向量索引和完整来源映射。"""
    settings = get_settings()
    hits = get_knowledge_base()
    index = build_index([hit.content for hit in hits])
    directory = directory or settings.index_path
    import faiss
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(directory / 'index.faiss'))
    metadata = {'model': settings.require_embed_model(),
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
    if metadata['model'] != settings.require_embed_model() or [h.model_dump() for h in saved] != [h.model_dump() for h in current]:
        raise ValueError('资料或向量模型已变化，请重建索引')
    index = faiss.read_index(str(directory / 'index.faiss'))
    if index.ntotal != len(saved):
        raise ValueError('索引和来源映射数量不一致')
    vector = np.asarray(embed_texts([query]), dtype='float32')
    if vector.ndim != 2 or vector.shape[1] != index.d:
        raise ValueError('查询向量维度与索引不一致')
    distances, ids = index.search(vector, min(top_k, index.ntotal))
    hits = [saved[i].model_copy(update={'score': float(distances[0][j]), 'score_kind':'l2_distance'})
            for j, i in enumerate(ids[0]) if i >= 0 and distances[0][j] <= max_distance]
    return KnowledgeResult(status='ok', hits=hits) if hits else KnowledgeResult(status='insufficient_evidence')


if __name__ == '__main__':
    print(f'索引片段数：{rebuild_vector_store()}')

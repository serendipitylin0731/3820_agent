# knowledge/knowledge_base.py
import os
import numpy as np
import faiss
from openai import OpenAI
from pptx import Presentation
from dotenv import load_dotenv
from functools import lru_cache
load_dotenv()
BASE_URL = os.getenv('ARK_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3')
EMBED_MODEL = os.getenv('EMBED_MODEL', 'doubao-embedding-large-text-240915')
def get_client():
    api_key = os.getenv('ARK_API_KEY')
    if not api_key:
        raise RuntimeError('请先配置ARK_API_KEY')
    return OpenAI(base_url=BASE_URL, api_key=api_key)
def load_ppt_text(path):
    # 按页读取演示文稿文本，每页作为一个知识片段
    prs = Presentation(path)
    chunks = []
    for idx, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, 'has_text_frame', False):
                text = shape.text_frame.text.strip()
                if text:
                    texts.append(text)
            elif getattr(shape, 'has_table', False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        texts.append(' | '.join(cells))
        if texts:
            chunks.append(f'[第{idx}页] ' + ' '.join(texts))
    return chunks
def embed_texts(texts):
    resp = get_client().embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]
def build_index(chunks):
    if not chunks:
        raise ValueError('知识库没有可索引的文本片段')
    vectors = np.asarray(embed_texts(chunks), dtype='float32')
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
        raise ValueError('向量数量或维度与知识片段不一致')
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)
    return index
def retrieve(index, chunks, query, top_k=5):
    # 返回[(片段, L2距离)]；距离仅表示向量距离，不代表事实可靠性
    if index is None or not chunks or index.ntotal == 0 or top_k <= 0:
        return []
    top_k = min(top_k, index.ntotal, len(chunks))
    qv = np.asarray(embed_texts([query]), dtype='float32')
    distances, ids = index.search(qv, top_k)
    return [(chunks[i], float(distances[0][j])) for j, i in enumerate(ids[0]) if 0 <= i < len(chunks)]
@lru_cache(maxsize=1)
def get_knowledge_base():
    path = os.getenv('PPT_PATH')
    if not path:
        raise RuntimeError('请配置PPT_PATH')
    chunks = load_ppt_text(path)
    return chunks, build_index(chunks)
def retrieve_context(query, top_k=5):
    chunks, index = get_knowledge_base()
    hits = retrieve(index, chunks, query, top_k)
    if not hits:
        return '知识库暂无相关依据。'
    return '\n\n'.join(piece for piece, _distance in hits)
if __name__ == '__main__':
    chunks = load_ppt_text(os.environ['PPT_PATH'])
    index = build_index(chunks)
    for piece, dist in retrieve(index, chunks, '1995年GDP翻一番目标'):
        print(dist, piece[:60])

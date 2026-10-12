"""Create a self-contained Linux web deployment directory without local secrets."""

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / '3820_agent_web'
ROOT_MODULES = ('app.py', 'graph.py', 'llm_client.py', 'resilience.py',
                'config.py', 'contracts.py', 'requirements.lock', '.env.example')
RUNTIME_DOCS = ('3820背景.md', '基于3820战略工程内容的多智能体系统搭建指南.md')


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_runtime_data(target: Path) -> None:
    source = ROOT / 'knowledge' / 'data'
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix.lower() in {'.doc', '.docx', '.ppt', '.pptx'}:
            if path.name != '3820PPT+视频.ppt':
                copy_file(path, target / path.name)

    public = source / 'public_sources'
    if public.is_dir():
        for path in public.iterdir():
            if path.is_file() and (path.suffix == '.txt' or path.name == 'manifest.json'):
                copy_file(path, target / 'public_sources' / path.name)

    scan = source / 'original_3820'
    if scan.is_dir():
        for name in ('manifest.json', 'catalog.json'):
            if (scan / name).is_file():
                copy_file(scan / name, target / 'original_3820' / name)
        for path in (scan / 'pages').glob('page_*.txt'):
            copy_file(path, target / 'original_3820' / 'pages' / path.name)

    ocr = source / 'ppt_ocr'
    if (ocr / 'manifest.json').is_file():
        copy_file(ocr / 'manifest.json', target / 'ppt_ocr' / 'manifest.json')
        for path in ocr.glob('*/slide_*.txt'):
            copy_file(path, target / 'ppt_ocr' / path.parent.name / path.name)


def copy_compatible_index(target: Path) -> None:
    index = ROOT / 'var' / 'knowledge_index'
    if not all((index / name).is_file() for name in ('index.faiss', 'metadata.json')):
        print('No vector index found; server will use text search until an index is built')
        return

    sys.path.insert(0, str(ROOT))
    from contracts import KnowledgeHit
    from knowledge.knowledge_base import EMBEDDING_SCHEMA, get_knowledge_base

    metadata = json.loads((index / 'metadata.json').read_text(encoding='utf-8'))
    saved = [KnowledgeHit.model_validate(item) for item in metadata['hits']]
    current = get_knowledge_base()
    same_vectors = (metadata.get('embedding_schema') == EMBEDDING_SCHEMA
                    and len(saved) == len(current)
                    and all((old.chunk_id, old.content) == (new.chunk_id, new.content)
                            for old, new in zip(saved, current)))
    if not same_vectors:
        print('Vector index differs from current text; excluded. Rebuild it on the server')
        return

    copy_file(index / 'index.faiss', target / 'index.faiss')
    metadata['hits'] = [hit.model_dump() for hit in current]
    (target / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    print(f"Included {len(current)} vector records; model: {metadata.get('model')}")


def build(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f'{output} 已存在；请先备份或移走旧目录，再重新生成')
    output.mkdir(parents=True)
    try:
        for name in ROOT_MODULES:
            copy_file(ROOT / name, output / name)
        for folder in ('agents', 'web'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    copy_file(path, output / path.relative_to(ROOT))
        for folder in ('knowledge',):
            for path in (ROOT / folder).iterdir():
                if path.is_file() and path.suffix in {'.py', '.json'}:
                    copy_file(path, output / folder / path.name)
        for name in ('__init__.py', 'runtime.py'):
            copy_file(ROOT / 'desktop_app' / name, output / 'desktop_app' / name)
        for name in RUNTIME_DOCS:
            copy_file(ROOT / 'docs' / name, output / 'docs' / name)
        copy_runtime_data(output / 'knowledge' / 'data')

        (output / 'var').mkdir(exist_ok=True)
        copy_compatible_index(output / 'var' / 'knowledge_index')

        for name in ('Dockerfile', '.dockerignore', 'README.md'):
            copy_file(ROOT / 'packaging' / 'server' / name, output / name)
    except Exception:
        shutil.rmtree(output)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output.resolve())
    print(f'Server bundle: {args.output.resolve()}')

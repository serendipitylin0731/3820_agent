"""按序执行子任务，保留部分失败，并使用 SQLite 保存会话快照。"""
import sqlite3
import time
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from contracts import AgentResult, ErrorInfo, KnowledgeResult, SubTask
from config import get_settings
from agents.agent_main import split_task
from agents.answer_writer import compose_answer, natural_fallback
from agents.agent_planning import run_planning
from agents.agent_indicator import query_indicator, query_target, INDICATOR_DATA
from agents.agent_spatial import query_spatial
from agents.agent_evaluation import eval_1995_phase
from knowledge.knowledge_base import EXACT_ENTITIES, format_context, search
from knowledge.curated import direct_hits
from knowledge.model_fallback import answer_from_model, needs_model
from knowledge.query_understanding import resolve_question
from resilience import find_checkpoint, log_event, timeout_error, transient_error


class TaskState(TypedDict, total=False):
    question: str
    previous_question: str
    question_history: list[str]
    resolved_question: str
    request_id: str
    thread_id: str
    sub_tasks: list
    kb_context: str
    kb_sources: list
    kb_error: str | None
    kb_error_code: str | None
    results: dict
    errors: list
    answer: str


def _query(state):
    return state.get('resolved_question') or state['question']


def parse_node(state):
    started = time.monotonic()
    try:
        resolved = resolve_question(state['question'], state.get('previous_question', ''),
                                    history=state.get('question_history', []),
                                    settings=get_settings())
        raw = split_task(resolved)
        if not isinstance(raw, list) or not raw:
            raise ValueError('未生成有效子任务')
        tasks = [SubTask.model_validate(item).model_dump(exclude_none=True) for item in raw]
    except Exception as exc:
        log_event('tasks_failed', state.get('request_id', ''), state.get('thread_id', ''),
                  level='warning', node='parse_node', error_type=type(exc).__name__,
                  duration_ms=round((time.monotonic() - started) * 1000, 1))
        raise
    log_event('tasks_parsed', state.get('request_id', ''), state.get('thread_id', ''),
              node='parse_node', duration_ms=round((time.monotonic() - started) * 1000, 1))
    return {'sub_tasks': tasks, 'resolved_question': resolved,
            'question_history': [*state.get('question_history', []), resolved][-4:]}


def route_node(state):
    return 'retrieve_node' if any(task['type'] == 'planning' for task in state['sub_tasks']) else 'execute_node'


def retrieve_node(state):
    started = time.monotonic()
    question = _query(state)
    direct = direct_hits(question)
    if direct and (direct[0].chunk_id == 'reviewed:investment_map' or
                   not any(term in question for term in ('示意图', '地图', '幻灯片', 'PPT', '图片'))):
        found = KnowledgeResult(status='ok', hits=direct)
        log_event('retrieval_finished', state.get('request_id', ''), state.get('thread_id', ''),
                  node='retrieve_node', duration_ms=round((time.monotonic() - started) * 1000, 1))
        return {'kb_context': format_context(found),
                'kb_sources': [hit.source.model_dump() for hit in direct],
                'kb_error': None, 'kb_error_code': None}
    query = ('福州市20年经济社会发展战略设想 战略布局'
             if '布局' in question and any(term in question for term in ('3820', '战略'))
             else '福州市20年经济社会发展战略设想 3820工程 调查研究 战略规划'
             if any(term in question for term in ('马克思', '习近平新时代', '方法论', '新发展理念'))
             else question)
    for attempt in range(2):
        try:
            found = search(query, top_k=get_settings().top_k)
            if direct:
                found = found.model_copy(update={'status': 'ok',
                    'hits': [*direct, *[hit for hit in found.hits
                                      if hit.chunk_id not in {item.chunk_id for item in direct}]][:get_settings().top_k]})
            anchors = [term for term in EXACT_ENTITIES if term in question]
            if anchors and found.hits:
                relevant = [hit for hit in found.hits if any(term in hit.content for term in anchors)]
                if relevant:
                    found = found.model_copy(update={'hits': relevant[:3]})
            log_event('retrieval_finished', state.get('request_id', ''), state.get('thread_id', ''),
                      node='retrieve_node', duration_ms=round((time.monotonic() - started) * 1000, 1))
            return {'kb_context': format_context(found),
                    'kb_sources': [hit.source.model_dump() for hit in found.hits],
                    'kb_error': None, 'kb_error_code': None}
        except Exception as exc:
            if attempt == 0 and transient_error(exc):
                continue
            if direct:
                found = KnowledgeResult(status='ok', hits=direct)
                return {'kb_context': format_context(found),
                        'kb_sources': [hit.source.model_dump() for hit in direct],
                        'kb_error': None, 'kb_error_code': None}
            log_event('retrieval_failed', state.get('request_id', ''), state.get('thread_id', ''),
                      level='warning', node='retrieve_node', error_type=type(exc).__name__,
                      duration_ms=round((time.monotonic() - started) * 1000, 1))
            return {'kb_context': '', 'kb_sources': [], 'kb_error': '检索暂不可用',
                    'kb_error_code': 'retrieval_timeout' if timeout_error(exc) else 'retrieval_error'}


def execute_node(state):
    results = {}
    for i, task in enumerate(state['sub_tasks'], 1):
        started = time.monotonic()
        role = task['type']
        label = f'{role}_{i}' if len(state['sub_tasks']) > 1 else role
        try:
            if role == 'indicator':
                if task.get('target'):
                    value = query_target(task['key'], task.get('years'))
                    sources = value.get('sources', [])
                    value = {key: item for key, item in value.items() if key != 'sources'}
                else:
                    value = query_indicator(task['key'], task.get('years'), growth=task.get('growth', False))
                    sources = [value['source']] if isinstance(value, dict) and 'source' in value else []
                    if isinstance(value, dict):
                        sources.extend(item['other']['source_ref'] for item in value.get('conflicts', []))
                        sources.extend(item['source_ref'] for item in value.get('incomparable', []))
            elif role == 'spatial':
                value = query_spatial(task['keyword'], task.get('stype'))
                sources = [item['source_ref'] for item in value] if isinstance(value, list) else []
            elif role == 'evaluation':
                if any(year in task['question'] for year in ('2000', '2010')) or (
                    '1995' not in task['question'] and '翻一番' not in task['question']
                ):
                    value = '缺少比较对象、年份、口径和判据，无法评估。'
                    sources = []
                else:
                    value = eval_1995_phase(INDICATOR_DATA)
                    indicator_keys = {item['key'] for item in state['sub_tasks']
                                      if item['type'] == 'indicator' and item.get('key') in INDICATOR_DATA}
                    if indicator_keys:
                        names = {INDICATOR_DATA[key]['name'] for key in indicator_keys}
                        value = [row for row in value if row['指标'] in names]
                    sources = list({source['source_file']: source for row in value
                                    for source in (row['来源'], row['目标来源'])}.values())
            else:
                if state.get('kb_error'):
                    result = AgentResult(role=role, status='error',
                                         error=ErrorInfo(code=state.get('kb_error_code') or 'retrieval_error',
                                                         message=state['kb_error']))
                    results[label] = result.model_dump()
                    log_event('agent_failed', state.get('request_id', ''), state.get('thread_id', ''),
                              level='warning', role=role, node='execute_node',
                              error_type=result.error.code,
                              duration_ms=round((time.monotonic() - started) * 1000, 1))
                    continue
                value = run_planning(task['question'], state.get('kb_context', ''))
                sources = state.get('kb_sources', [])
                if isinstance(value, dict) and value.get('source_sections'):
                    selected = set(value.pop('source_sections'))
                    sources = [source for source in sources if source.get('section') in selected]
            if isinstance(value, dict) and 'error' in value:
                if value.get('conflicts') or value.get('incomparable'):
                    alternatives = [item['other'] for item in value['conflicts']]
                    alternatives.extend(value['incomparable'])
                    result = AgentResult(role=role, status='insufficient_evidence', data=value,
                                         sources=[INDICATOR_DATA[task['key']]['source_ref']] +
                                         [item['source_ref'] for item in alternatives])
                else:
                    result = AgentResult(role=role, status='error', error=ErrorInfo(code='domain_error', message=value['error']))
            elif isinstance(value, dict) and 'insufficient_evidence' in value:
                result = AgentResult(role=role, status='insufficient_evidence',
                                     data=value['insufficient_evidence'], sources=[])
            elif (role == 'planning' or role == 'evaluation') and not sources:
                result = AgentResult(role=role, status='insufficient_evidence', data=value)
            else:
                result = AgentResult(role=role, status='ok', data=value, sources=sources)
        except Exception as exc:
            is_timeout = timeout_error(exc)
            result = AgentResult(role=role, status='error', error=ErrorInfo(
                code='agent_timeout' if is_timeout else 'agent_error',
                message='子任务执行超时' if is_timeout else '子任务执行失败'))
            log_event('agent_failed', state.get('request_id', ''), state.get('thread_id', ''),
                      level='warning', role=role, node='execute_node', error_type=type(exc).__name__,
                      duration_ms=round((time.monotonic() - started) * 1000, 1))
        else:
            failed = result.status == 'error'
            log_event('agent_failed' if failed else 'agent_finished',
                      state.get('request_id', ''), state.get('thread_id', ''),
                      level='warning' if failed else 'info', role=role, node='execute_node',
                      error_type=result.error.code if failed else None,
                      duration_ms=round((time.monotonic() - started) * 1000, 1))
        results[label] = result.model_dump()
    return {'results': results,
            'errors': [item['error'] for item in results.values() if item.get('error')]}


def answer_node(state):
    started = time.monotonic()
    question = _query(state)
    results = dict(state['results'])
    fallback = natural_fallback(question, results)
    answer, theory = compose_answer(question, results, fallback, settings=get_settings())
    if needs_model(question, results, answer):
        supplement = answer_from_model(question, settings=get_settings())
        if supplement:
            answer, model_result = supplement
            for item in results.values():
                if item.get('role') == 'planning':
                    item['status'] = 'insufficient_evidence'
                    item['sources'] = []
            results['model'] = model_result
    if theory:
        results['theory_context'] = AgentResult(
            role='theory', status='ok',
            data={'perspective': '当代理论参照，非1992年原始史料', 'used_ids': list(theory)},
            sources=[item['source'] for item in theory.values()],
        ).model_dump()
    log_event('answer_finished', state.get('request_id', ''), state.get('thread_id', ''),
              node='answer_node', duration_ms=round((time.monotonic() - started) * 1000, 1))
    return {'answer': answer, 'results': results}


builder = StateGraph(TaskState)
builder.add_node('parse_node', parse_node)
builder.add_node('retrieve_node', retrieve_node)
builder.add_node('execute_node', execute_node)
builder.add_node('answer_node', answer_node)
builder.add_edge(START, 'parse_node')
builder.add_conditional_edges('parse_node', route_node,
                              {'retrieve_node':'retrieve_node', 'execute_node':'execute_node'})
builder.add_edge('retrieve_node', 'execute_node')
builder.add_edge('execute_node', 'answer_node')
builder.add_edge('answer_node', END)


@lru_cache(maxsize=1)
def get_graph():
    path = get_settings().checkpoint_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return builder.compile(checkpointer=SqliteSaver(connection))


def ask(question, thread_id, request_id=None):
    config = {'configurable': {'thread_id': thread_id}}
    graph = get_graph()
    snapshot = graph.get_state(config)
    if snapshot.next:
        if snapshot.values.get('question') != question:
            raise ValueError('会话有未完成任务，请先恢复该会话')
        return graph.invoke(None, config)
    history = snapshot.values.get('question_history', [])
    previous = snapshot.values.get('resolved_question') or snapshot.values.get('question', '')
    if previous and (not history or history[-1] != previous):
        history = [*history, previous][-4:]
    return graph.invoke({'question': question, 'previous_question': previous,
                               'question_history': history, 'resolved_question': '',
                               'thread_id': thread_id,
                               'request_id': request_id or thread_id, 'sub_tasks': [],
                               'kb_context': '', 'kb_sources': [], 'kb_error': None,
                               'kb_error_code': None,
                               'results': {}, 'errors': [], 'answer': ''}, config)


def resume(thread_id, checkpoint_id=None):
    """显式恢复未完成快照；已完成的快照仅返回现有值。"""
    graph = get_graph()
    config = {'configurable': {'thread_id': thread_id}}
    snapshot = find_checkpoint(graph, thread_id, checkpoint_id) if checkpoint_id else graph.get_state(config)
    if snapshot is None or not snapshot.values:
        raise ValueError('未找到会话快照')
    if not snapshot.next:
        return snapshot.values
    return graph.invoke(None, snapshot.config)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description='恢复已保存的会话快照')
    parser.add_argument('thread_id')
    parser.add_argument('--checkpoint-id')
    args = parser.parse_args()
    print(json.dumps(resume(args.thread_id, args.checkpoint_id), ensure_ascii=False, default=str))

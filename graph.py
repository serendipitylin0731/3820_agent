"""按序执行子任务，保留部分失败，并使用 SQLite 保存会话快照。"""
import sqlite3
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from contracts import AgentResult, ErrorInfo, SubTask
from config import get_settings
from agents.agent_main import split_task, summarize
from agents.agent_planning import run_planning
from agents.agent_indicator import query_indicator, INDICATOR_DATA
from agents.agent_spatial import query_spatial
from agents.agent_evaluation import eval_1995_phase
from knowledge.knowledge_base import format_context, search
from resilience import find_checkpoint, log_event, transient_error


class TaskState(TypedDict, total=False):
    question: str
    request_id: str
    thread_id: str
    sub_tasks: list
    kb_context: str
    kb_sources: list
    kb_error: str | None
    results: dict
    errors: list
    answer: str


def parse_node(state):
    raw = split_task(state['question'])
    if not isinstance(raw, list) or not raw:
        raise ValueError('未生成有效子任务')
    tasks = [SubTask.model_validate(item).model_dump(exclude_none=True) for item in raw]
    log_event('tasks_parsed', state.get('request_id', ''), state.get('thread_id', ''),
              node='parse_node')
    return {'sub_tasks': tasks}


def route_node(state):
    return 'retrieve_node' if any(task['type'] == 'planning' for task in state['sub_tasks']) else 'execute_node'


def retrieve_node(state):
    for attempt in range(2):
        try:
            found = search(state['question'], top_k=get_settings().top_k)
            return {'kb_context': format_context(found),
                    'kb_sources': [hit.source.model_dump() for hit in found.hits],
                    'kb_error': None}
        except Exception as exc:
            if attempt == 0 and transient_error(exc):
                continue
            log_event('retrieval_failed', state.get('request_id', ''), state.get('thread_id', ''),
                      level='warning', node='retrieve_node', error_type=type(exc).__name__)
            return {'kb_context': '', 'kb_sources': [], 'kb_error': '检索暂不可用'}


def execute_node(state):
    results = {}
    for i, task in enumerate(state['sub_tasks'], 1):
        role = task['type']
        label = f'{role}_{i}' if len(state['sub_tasks']) > 1 else role
        try:
            if role == 'indicator':
                value = query_indicator(task['key'], task.get('years'))
                sources = [value['source']] if isinstance(value, dict) and 'source' in value else []
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
                    sources = [INDICATOR_DATA[key]['source_ref'] for key in ('gnp','gdp','gdp_per_capita','urban_income','rural_income','industry_output')]
            else:
                if state.get('kb_error'):
                    result = AgentResult(role=role, status='error',
                                         error=ErrorInfo(code='retrieval_error', message=state['kb_error']))
                    results[label] = result.model_dump()
                    continue
                value = run_planning(task['question'], state.get('kb_context', ''))
                sources = state.get('kb_sources', [])
            if isinstance(value, dict) and 'error' in value:
                result = AgentResult(role=role, status='error', error=ErrorInfo(code='domain_error', message=value['error']))
            elif (role == 'planning' or role == 'evaluation') and not sources:
                result = AgentResult(role=role, status='insufficient_evidence', data=value)
            else:
                result = AgentResult(role=role, status='ok', data=value, sources=sources)
        except Exception as exc:
            result = AgentResult(role=role, status='error', error=ErrorInfo(code='agent_error', message='子任务执行失败'))
            log_event('agent_failed', state.get('request_id', ''), state.get('thread_id', ''),
                      level='warning', role=role, node='execute_node', error_type=type(exc).__name__)
        else:
            log_event('agent_finished', state.get('request_id', ''), state.get('thread_id', ''),
                      role=role, node='execute_node')
        results[label] = result.model_dump()
    return {'results': results,
            'errors': [item['error'] for item in results.values() if item.get('error')]}


def answer_node(state):
    return {'answer': summarize(state['question'], state['results'])}


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
    return graph.invoke({'question': question, 'thread_id': thread_id,
                               'request_id': request_id or thread_id, 'sub_tasks': [],
                               'kb_context': '', 'kb_sources': [], 'kb_error': None,
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

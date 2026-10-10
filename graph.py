# graph.py —— LangGraph 编排（orchestrator-worker 模式）
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agents.agent_main import split_task, summarize
from agents.agent_planning import run_planning
from agents.agent_indicator import query_indicator, INDICATOR_DATA
from agents.agent_spatial import query_spatial
from agents.agent_evaluation import eval_1995_phase
from knowledge.knowledge_base import retrieve_context
class TaskState(TypedDict):
    question: str        # 用户问题
    sub_tasks: list      # 主智能体拆分结果
    kb_context: str      # 知识库检索上下文
    results: dict        # 各智能体结果
    answer: str          # 最终答案
def parse_node(state):
    tasks = split_task(state['question'])
    if not tasks:
        raise ValueError('主智能体未生成有效子任务')
    for task in tasks:
        if task.get('type') not in ('planning', 'indicator', 'spatial', 'evaluation'):
            raise ValueError('子任务type不在允许范围内')
        if task.get('type') == 'indicator' and not task.get('key'):
            raise ValueError('指标子任务缺少key字段')
        if task.get('type') == 'spatial' and not task.get('keyword'):
            raise ValueError('空间子任务缺少keyword字段')
    needs_context = any(t.get('type') in ('planning', 'spatial', 'evaluation') for t in tasks)
    kb_context = retrieve_context(state['question']) if needs_context else ''
    return {'sub_tasks': tasks, 'kb_context': kb_context}
def route_node(state):
    # 根据子任务类型决定下一节点
    if len(state['sub_tasks']) == 1:
        task_type = state['sub_tasks'][0]['type']
        return {'planning': 'planning_node', 'indicator': 'indicator_node',
                'spatial': 'spatial_node', 'evaluation': 'evaluation_node'}[task_type]
    return 'parallel_node'
def planning_node(state):
    task = state['sub_tasks'][0]
    return {'results': {'planning': run_planning(task['question'], state['kb_context'])}}
def indicator_node(state):
    task = state['sub_tasks'][0]
    key = task.get('key', 'gdp')
    years = task.get('years')
    return {'results': {'indicator': query_indicator(key, years)}}
def spatial_node(state):
    task = state['sub_tasks'][0]
    return {'results': {'spatial': query_spatial(task.get('keyword'), task.get('stype'))}}
def evaluation_node(state):
    # 该节点目前仅演示固定的1995年翻番评估，其他阶段需显式传入目标规则
    return {'results': {'evaluation': eval_1995_phase(INDICATOR_DATA)}}
def parallel_node(state):
    # 多类型子任务按序执行；真正并行需另行实现并测试
    results = {}
    for i, task in enumerate(state['sub_tasks'], start=1):
        t = task['type']
        if t == 'planning':
            results[f'{t}_{i}'] = run_planning(task['question'], state['kb_context'])
        elif t == 'indicator':
            results[f'{t}_{i}'] = query_indicator(task.get('key', 'gdp'), task.get('years'))
        elif t == 'spatial':
            results[f'{t}_{i}'] = query_spatial(task.get('keyword'), task.get('stype'))
        elif t == 'evaluation':
            results[f'{t}_{i}'] = eval_1995_phase(INDICATOR_DATA)
    return {'results': results}
def answer_node(state):
    return {'answer': summarize(state['question'], state['results'])}
builder = StateGraph(TaskState)
builder.add_node('parse_node', parse_node)
builder.add_node('planning_node', planning_node)
builder.add_node('indicator_node', indicator_node)
builder.add_node('spatial_node', spatial_node)
builder.add_node('evaluation_node', evaluation_node)
builder.add_node('parallel_node', parallel_node)
builder.add_node('answer_node', answer_node)
builder.add_edge(START, 'parse_node')
builder.add_conditional_edges('parse_node', route_node, {
    'planning_node': 'planning_node',
    'indicator_node': 'indicator_node',
    'spatial_node': 'spatial_node',
    'evaluation_node': 'evaluation_node',
    'parallel_node': 'parallel_node',
})
for node in ('planning_node', 'indicator_node', 'spatial_node', 'evaluation_node', 'parallel_node'):
    builder.add_edge(node, 'answer_node')
builder.add_edge('answer_node', END)
checkpointer = MemorySaver()   # 内存Checkpoint；生产建议 SqliteSaver 持久化
app = builder.compile(checkpointer=checkpointer)
def ask(question, thread_id):
    config = {'configurable': {'thread_id': thread_id}}
    return app.invoke({
        'question': question,
        'sub_tasks': [],
        'kb_context': '',
        'results': {},
    }, config)

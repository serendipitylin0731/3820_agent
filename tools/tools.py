# tools/tools.py —— 工具注册与统一调用
from knowledge.knowledge_base import retrieve_context
from agents.agent_indicator import query_indicator
from agents.agent_spatial import query_spatial
TOOL_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'knowledge_retrieve',
            'description': '检索“3820”战略工程知识库（目标、路径、成效等事实）',
            'parameters': {
                'type': 'object',
                'properties': {'query': {'type': 'string', 'description': '检索问题或关键词'}},
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'query_indicator',
            'description': '查询主要经济指标（GDP、人均GDP、GNP、城乡收入等）',
            'parameters': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string'},
                    'years': {'type': 'array', 'items': {'type': 'integer'}},
                },
                'required': ['key'],
            },
        },
    },
  {
     'type': 'function',
     'function': {
        'name': 'query_spatial',
        'description': '按关键词与类型查询空间要素',
        'parameters': {
           'type': 'object',
           'properties': {'keyword': {'type': 'string'}, 'stype': {'type': 'string'}},
           'required': ['keyword'],
        },
     },
  },
]
def call_tool(name, arguments):
    # 工具分发：知识检索、指标查询与空间查询均走此入口
    if name == 'knowledge_retrieve':
        return retrieve_context(arguments['query'])
    if name == 'query_indicator':
        return query_indicator(arguments['key'], arguments.get('years'))
    if name == 'query_spatial':
        return query_spatial(arguments.get('keyword'), arguments.get('stype'))
    raise ValueError(f'未知工具：{name}')
# 大模型请求示例：messages + tools=TOOL_SCHEMA，模型返回 tool_calls 后
# 循环调用 call_tool，把工具结果回填 messages 后继续对话（function calling 标准流程）

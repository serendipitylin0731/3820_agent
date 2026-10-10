"""三项只读工具的统一参数校验。"""
from pydantic import BaseModel, ConfigDict, Field
from knowledge.knowledge_base import search
from agents.agent_indicator import query_indicator
from agents.agent_spatial import query_spatial


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RetrieveArgs(Arguments):
    query: str = Field(min_length=1)


class IndicatorArgs(Arguments):
    key: str = Field(min_length=1)
    years: list[int] | None = None


class SpatialArgs(Arguments):
    keyword: str = Field(min_length=1)
    stype: str | None = None


TOOL_SCHEMA = [
    {'type':'function','function':{'name':'knowledge_retrieve','description':'检索战略资料',
      'parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query'],'additionalProperties':False}}},
    {'type':'function','function':{'name':'query_indicator','description':'查询经济指标',
      'parameters':{'type':'object','properties':{'key':{'type':'string'},'years':{'type':'array','items':{'type':'integer'}}},'required':['key'],'additionalProperties':False}}},
    {'type':'function','function':{'name':'query_spatial','description':'查询空间要素',
      'parameters':{'type':'object','properties':{'keyword':{'type':'string'},'stype':{'type':'string'}},'required':['keyword'],'additionalProperties':False}}},
]


def call_tool(name, arguments):
    if name == 'knowledge_retrieve':
        args = RetrieveArgs.model_validate(arguments)
        return search(args.query).model_dump()
    if name == 'query_indicator':
        args = IndicatorArgs.model_validate(arguments)
        return query_indicator(args.key, args.years)
    if name == 'query_spatial':
        args = SpatialArgs.model_validate(arguments)
        return query_spatial(args.keyword, args.stype)
    raise ValueError(f'未知工具：{name}')

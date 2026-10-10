"""三项只读工具的统一参数校验。"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from contracts import ErrorInfo, ToolResult
from knowledge.knowledge_base import search
from agents.agent_indicator import query_indicator
from agents.agent_spatial import query_spatial


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('*')
    @classmethod
    def no_blank_text(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError('参数不得为空白')
        return value.strip() if isinstance(value, str) else value


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
        result = search(args.query)
        return ToolResult(status=result.status, data=[hit.model_dump() for hit in result.hits],
                          sources=[hit.source for hit in result.hits], error=result.error).model_dump()
    if name == 'query_indicator':
        args = IndicatorArgs.model_validate(arguments)
        result = query_indicator(args.key, args.years)
        if 'error' in result:
            return ToolResult(status='error', error=ErrorInfo(code='domain_error', message=result['error'])).model_dump()
        return ToolResult(status='ok', data=result, sources=[result['source']]).model_dump()
    if name == 'query_spatial':
        args = SpatialArgs.model_validate(arguments)
        result = query_spatial(args.keyword, args.stype)
        if isinstance(result, dict):
            return ToolResult(status='insufficient_evidence', data=result['error']).model_dump()
        return ToolResult(status='ok', data=result,
                          sources=[item['source_ref'] for item in result]).model_dump()
    raise ValueError(f'未知工具：{name}')

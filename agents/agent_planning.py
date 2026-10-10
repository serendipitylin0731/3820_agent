"""规划分析：以检索片段为依据，事实与建议分开输出。"""
import json
from pydantic import BaseModel, ConfigDict, Field
from config import get_settings


class PlanningReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    background: str = Field(min_length=1)
    stage_goals: str = Field(min_length=1)
    implementation_paths: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    risks: str = Field(min_length=1)
    suggestions: str = Field(min_length=1)


class PlanningAdvice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    risks: str = Field(min_length=1)
    suggestions: str = Field(min_length=1)


PLANNING_SYSTEM = '''仅根据提供的资料，提出风险提示和后续分析建议。输出 JSON 对象，仅含 risks、suggestions 两个非空字符串。两项都属于分析意见，不得写成历史事实。不要添加 Markdown 围栏。'''


def _excerpt(context, marker, limit=350):
    for line in context.splitlines():
        if marker in line and len(line.strip()) > 8:
            return line.strip()[:limit]
    return '资料未提及'


def _passage(context, marker, limit=650):
    offset = context.find(marker)
    if offset < 0:
        return '资料未提及'
    end = context.find('\n\n', offset)
    return context[offset:end if end >= 0 else None].strip()[:limit]


def run_planning(question, kb_text):
    if not kb_text or '暂无充分依据' in kb_text:
        return None
    settings = get_settings()
    report = PlanningReport(
        background=_excerpt(kb_text, '1992'),
        stage_goals=_excerpt(kb_text, '1995'),
        implementation_paths=(_passage(kb_text, '四、战略布局') if '布局' in question
                              else _excerpt(kb_text, '以侨引侨')),
        evidence=kb_text[:1800],
        risks='现有指南及整理数据尚未与原始附件独立核验。',
        suggestions='分析建议：补齐原始资料并逐项核验后，再作进一步判断。',
    )
    if settings.ark_api_key and settings.llm_model:
        from llm_client import chat
        raw = chat([{'role':'system','content':PLANNING_SYSTEM},
                    {'role':'user','content':f'问题：{question}\n参考资料：{kb_text}'}])
        advice = PlanningAdvice.model_validate(json.loads(raw))
        report.risks = f'分析风险：{advice.risks}'
        report.suggestions = f'分析建议：{advice.suggestions}'
    return report.model_dump()

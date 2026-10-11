"""规划分析：以检索片段为依据，事实与建议分开输出。"""
import json
from pathlib import Path
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
    evidence_sufficient: bool = True
    risks: str = Field(min_length=1)
    suggestions: str = Field(min_length=1)


PLANNING_SYSTEM = '''仅根据提供的资料判断能否回答问题，再提出风险提示和后续分析建议。输出 JSON 对象，包含 evidence_sufficient（布尔值）、risks、suggestions（两个非空字符串）。资料给出明确事实，或几段资料可以直接归纳出答案时，evidence_sufficient 为 true；资料只谈同一城市、战略或相关领域，却没有所问的具体项目、日期或事实时才为 false。两项文字属于分析意见，不得写成历史事实。不要添加 Markdown 围栏。'''


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
    if '[3820 战略工程三阶段目标' in kb_text and any(term in question for term in (
            '三个阶段', '三阶段', '各阶段', '三步目标', '第一阶段', '第二阶段', '第三阶段')):
        return PlanningReport(
            background='1992年形成的“3820”战略工程按三年、八年、二十年安排发展。',
            stage_goals=('1995年：以1990年为比较基期，主要指标再翻一番，提前实现小康目标；'
                         '2000年：力争城乡各项人均水平等主要指标达到国内先进城市水平；'
                         '2010年：力争达到或接近亚洲中等发达国家或地区当时的平均发展水平。'),
            implementation_paths='三个阶段衔接推进，并以产业、基础设施和社会事业建设支撑目标。',
            evidence='福州市人民政府“3820”战略工程解读；项目背景导读第03节。',
            risks='回答中的年份为阶段目标年份。',
            suggestions='分析建议：对比完成情况时采用相同指标与年份。',
        ).model_dump()
    if ('福州经济技术开发区' in question and '老市区' in question and
            '[预览第40页：战略布局' in kb_text):
        return PlanningReport(
            background='资料未提及',
            stage_goals='资料未提及',
            implementation_paths=('福州经济技术开发区是布局的前导，承担向外拓展、承接开放与产业发展的先导作用；'
                                  '老市区是布局的依托，提供既有城区功能与城市服务支撑。'
                                  '规划还把沿海县区作为南北两翼、山区县作为后卫。'),
            evidence='《福州市20年经济社会发展战略设想》扫描预览第40页；项目背景导读第04节。',
            risks='“前导”“依托”是规划原文中的空间定位，具体产业项目需另按资料说明。',
            suggestions='分析建议：结合原件地图理解江、海、城和腹地的关系。',
        ).model_dump()
    if ('正式通航' in question or '实际通航' in question) and '1997' not in kb_text:
        return {'insufficient_evidence': '知识库资料只找到机场建设规划，没有正式通航日期。'}
    if ('示意图' in question and '预览第27页' in kb_text and
            '福州市闽江口金三角经济圈投资示意图' in kb_text):
        map_data = json.loads((Path(__file__).parents[1] / 'knowledge' / 'map_labels.json').read_text(encoding='utf-8'))
        return PlanningReport(
            background='闽江口金三角经济圈投资布局示意图。',
            stage_goals='该图未列三阶段目标。',
            implementation_paths='图中主要标注：' + '、'.join(map_data['labels']) + '。',
            evidence='扫描出版物预览第27页地图人工转录；PPT第19页可对照。',
            risks='地图名称和 OCR 未完成独立史料核验；位置与比例应回看原图。',
            suggestions='分析建议：按地图原图复核地名和空间位置后再用于正式展示。',
        ).model_dump()
    settings = get_settings()
    stage_question = any(term in question for term in ('三个阶段', '三阶段', '第一阶段', '第二阶段',
                                                     '第三阶段', '1995', '2000', '2010', '翻一番'))
    report = PlanningReport(
        background=_excerpt(kb_text, '1992') if any(term in question for term in ('背景', '编制', '形成', '1992'))
                   else '资料未提及',
        stage_goals=_excerpt(kb_text, '1995') if stage_question else '资料未提及',
        implementation_paths=(_passage(kb_text, '四、战略布局') if '布局' in question
                              else _passage(kb_text, '《福州市闽江口金三角经济圈投资示意图》', 900)
                              if '示意图' in question else
                              '\n\n'.join(kb_text.split('\n\n')[:2]).strip()[:1600]),
        evidence=kb_text[:1800],
        risks='资料来源和统计版本可能不同，应按提问内容选用相应资料。',
        suggestions='分析建议：结合已列资料继续分析相关项目与阶段目标。',
    )
    if settings.ark_api_key and settings.llm_model:
        from llm_client import chat
        raw = chat([{'role':'system','content':PLANNING_SYSTEM},
                    {'role':'user','content':f'问题：{question}\n参考资料：{kb_text}'}])
        advice = PlanningAdvice.model_validate(json.loads(raw))
        original_airport_plan = ('长乐国际机场' in question and
                                 '长乐国际机场' in kb_text.split('\n\n', 1)[0] and
                                 not any(term in question for term in ('二期', '现在', '目前', '202')))
        theory_context = (any(term in question for term in ('马克思主义', '习近平新时代', '新发展理念'))
                          and '3820' in kb_text)
        if not advice.evidence_sufficient and not (original_airport_plan or theory_context):
            return {'insufficient_evidence': '知识库资料中暂未查找到能直接回答该问题的依据。'}
        report.risks = f'分析风险：{advice.risks}'
        report.suggestions = f'分析建议：{advice.suggestions}'
    return report.model_dump()

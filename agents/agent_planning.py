"""规划分析：先使用经整理的可追溯材料，避免把 OCR 噪声当答案。"""
import json
import re
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from knowledge.curated import answer_passage, source_sections
from knowledge.query_understanding import specific_document_question


class PlanningReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    background: str = Field(min_length=1)
    stage_goals: str = Field(min_length=1)
    implementation_paths: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    risks: str = Field(min_length=1)
    suggestions: str = Field(min_length=1)
    source_sections: list[str] = Field(default_factory=list)


def run_planning(question, kb_text):
    if not kb_text or '暂无充分依据' in kb_text:
        return None
    if specific_document_question(question):
        # These questions ask about the supplied book/interview itself. Pass
        # the retrieved text to the answer writer instead of applying the
        # fixed 3820 background report to an unrelated source.
        return {'source_excerpt': kb_text[:5500]}
    if ('[3820 战略工程三阶段目标' in kb_text and
            not any(term in question for term in ('提前完成', '提前实现', '是否完成', '完成情况')) and
            any(term in question for term in (
                '三个阶段', '三个时期', '三阶段', '各阶段', '三步目标', '分几步',
                '第一阶段', '第二阶段', '第三阶段'))):
        comparison = None
        if any(term in question for term in ('相比', '区别', '不同')):
            if '第二阶段' in question and '第一阶段' in question:
                comparison = ('第一阶段着重到1995年使主要指标在1990年基础上再翻一番；'
                              '第二阶段着重到2000年使城乡主要人均指标达到国内先进城市水平。')
            elif '第三阶段' in question and '第二阶段' in question:
                comparison = ('第二阶段着重到2000年达到国内先进城市水平；'
                              '第三阶段着重到2010年达到或接近亚洲中等发达国家或地区当时的平均水平。')
        return PlanningReport(
            background='1992年形成的“3820”战略工程按三年、八年、二十年安排发展。',
            stage_goals=('1995年：以1990年为比较基期，主要指标再翻一番，提前实现小康目标；'
                         '2000年：力争城乡各项人均水平等主要指标达到国内先进城市水平；'
                         '2010年：力争达到或接近亚洲中等发达国家或地区当时的平均发展水平。'),
            implementation_paths=comparison or '三个阶段衔接推进，并以产业、基础设施和社会事业建设支撑目标。',
            evidence='福州市人民政府“3820”战略工程解读；项目背景导读第03节。',
            risks='回答中的年份为阶段目标年份。',
            suggestions='分析建议：对比完成情况时采用相同指标与年份。',
            source_sections=['3820 战略工程三阶段目标'],
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
            source_sections=['预览第40页：战略布局'],
        ).model_dump()
    if ('正式通航' in question or '实际通航' in question) and '1997' not in kb_text:
        return {'insufficient_evidence': '知识库资料只找到机场建设规划，没有正式通航日期。'}
    if (any(term in question for term in ('示意图', '第27页', '投资区')) and
            '福州市闽江口金三角经济圈投资示意图' in kb_text):
        map_data = json.loads((Path(__file__).parents[1] / 'knowledge' / 'map_labels.json').read_text(encoding='utf-8'))
        return PlanningReport(
            background='闽江口金三角经济圈投资布局示意图。',
            stage_goals='资料未提及',
            implementation_paths='图中主要标注：' + '、'.join(map_data['labels']) + '。',
            evidence='扫描出版物预览第27页地图人工转录；PPT第19页可对照。',
            risks='地图标注的是历史投资区名称；具体位置与比例以原图为准。',
            suggestions='阅读时结合扫描页查看地名和空间位置。',
            source_sections=['福州市闽江口金三角经济圈投资示意图'],
        ).model_dump()
    sections = source_sections(question)
    passage = answer_passage(question)
    if passage and any(f'[{section} ' in kb_text for section in sections):
        return PlanningReport(
            background='资料未提及',
            stage_goals=passage if '3820 战略工程三阶段目标' in sections else '资料未提及',
            implementation_paths=passage,
            evidence='项目背景导读对应章节及其列明的原始资料和公开回顾。',
            risks='规划原文、后来实施和当代理论视角应按形成时间区分。',
            suggestions='分析建议：必要时查看所列原件和公开资料。',
            source_sections=sections,
        ).model_dump()
    if any(term in question for term in ('图片', '图像', '照片', '扫描件', '视频', '录像',
                                         '画面', '幻灯片', 'PPT', '课件')):
        media_sections = ('图片文字识别', '视频语音与画面文字', '演示文稿')
        passages = []
        used_sections = []
        for block in re.split(r'\n\n(?=\[)', kb_text):
            section = next((name for name in media_sections if block.startswith(f'[{name} ')), None)
            if section:
                used_sections.append(section)
                passages.append(re.sub(r'^\[[^\]]+\]\s*', '', block).strip()[:650])
            if len(passages) == 3:
                break
        if passages:
            return PlanningReport(
                background='资料未提及',
                stage_goals='资料未提及',
                implementation_paths='；'.join(passages).rstrip('。') + '。',
                evidence='所列图片、视频或演示文稿的提取文字及对应位置。',
                risks='自动语音转写和图片文字识别可能存在错字，具体表述以原件为准。',
                suggestions='阅读或播放来源文件可以核对文字和上下文。',
                source_sections=list(dict.fromkeys(used_sections)),
            ).model_dump()
    # Search overlap alone is not proof: OCR contains many long, unrelated
    # passages that share common words with the question.
    return {'insufficient_evidence': '现有资料没有直接支持该具体问题的片段。'}

"""知识库没有直接依据时，仅为 3820 相关问题提供豆包模型补充。"""

import logging

from config import get_settings
from contracts import AgentResult
from llm_client import chat

logger = logging.getLogger('3820_agent')
CITY_TERMS = ('福州', '闽江口', '长乐', '马尾', '元洪', '福清', '罗源', '平潭')
PROJECT_TERMS = ('南北两翼', '金三角经济圈', '海上福州')
DEVELOPMENT_TERMS = ('发展', '战略', '规划', '建设', '工程', '经济', '机场', '港口',
                     '开放', '产业', '投资', '招商', '交通', '开发区', '城市', '基础设施')
INSUFFICIENT_MARKERS = (
    '无法明确', '无法确定', '暂未查找到', '未查找到', '未找到', '未收录',
    '依据不足', '资料不足', '未提及', '缺乏具体', '无法给出',
)
PREFIX = '知识库资料中暂未查找到，以下是豆包模型提供的参考回答：'


def is_related(question: str) -> bool:
    return ('3820' in question or any(term in question for term in PROJECT_TERMS) or
            any(term in question for term in CITY_TERMS) and
            any(term in question for term in DEVELOPMENT_TERMS))


def needs_model(question: str, results: dict, answer: str) -> bool:
    if not is_related(question):
        return False
    # 数值冲突与目标达成判据缺失不能用模型常识替代原始统计依据。
    if any(item.get('role') in {'indicator', 'evaluation'} for item in results.values()):
        return False
    planning = [item for item in results.values() if item.get('role') == 'planning']
    return bool(planning) and (not any(item.get('status') == 'ok' for item in planning)
                               or any(marker in answer for marker in INSUFFICIENT_MARKERS))


def answer_from_model(question: str, *, settings=None):
    """返回 (答案, 角色结果)；模型不可用或拒答时返回 None。"""
    settings = settings or get_settings()
    if not (is_related(question) and settings.ark_api_key and settings.llm_model):
        return None
    try:
        raw = chat([
            {'role': 'system', 'content': (
                '你是福州“3820”战略工程知识助手。当前知识库未检索到直接依据，请根据你已有的知识'
                '独立回答用户的相关问题。用自然、完整、准确的中文；直接回答，不输出分析过程。'
                '区分历史规划、后来实施和当前情况；不确定的具体日期、数据和历史细节不要猜测，'
                '可以明确说明自己无法确认；对不成立的问题前提直接指出，不能编造项目或事件。'
                '不能声称外部没有公开资料。'
                '不得声称已经联网检索，不得虚构网页、引文或来源。'
                '只输出回答正文，不要复述“知识库未找到”或添加开场白。')},
            {'role': 'user', 'content': question},
        ], temperature=0.2, settings=settings)
        body = raw.strip()
        if not body or any(marker in body for marker in ('无法识别', '无法回答该问题', '无法提供相关信息')):
            return None
        result = AgentResult(role='model', status='ok',
                             data={'kind': 'model_knowledge', 'source_note': '模型补充，未检索外部资料'},
                             sources=[])
        return PREFIX + body, result.model_dump()
    except Exception as exc:
        logger.warning('豆包模型补充失败 error_type=%s', type(exc).__name__)
        return None

"""规划分析仅使用检索到的资料。"""
from config import get_settings

PLANNING_SYSTEM = '根据给定资料分析背景、阶段目标、实施路径和风险。只引用给定资料；区分事实与建议，并保留来源位置。'


def run_planning(question, kb_text):
    if not kb_text or '暂无充分依据' in kb_text:
        return '知识库暂无充分依据，无法给出有来源的规划分析。'
    settings = get_settings()
    if settings.ark_api_key and settings.llm_model:
        from llm_client import chat
        return chat([{'role':'system','content':PLANNING_SYSTEM},
                     {'role':'user','content':f'问题：{question}\n参考资料：{kb_text}'}])
    return f'依据指南样例（未独立核验），相关资料如下：\n{kb_text[:1800]}'

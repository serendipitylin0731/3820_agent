# agents/agent_planning.py
PLANNING_SYSTEM = '''
你是“3820”战略工程的规划分析智能体。
请结合知识库中的“3820”内容（三阶段目标、制定过程、四条实施路径、人民情怀主题），
对用户提出的战略规划类问题进行结构化分析，输出建议包含：
背景、阶段目标、路径举措、关键依据、风险与建议。
所有关键依据必须来自提供的参考资料片段。
'''
def run_planning(question, kb_text):
    from llm_client import client
    import os
    resp = client.chat.completions.create(
        model=os.environ.get('LLM_MODEL', 'doubao-seed-2-1-pro-260628'),
        messages=[
            {'role': 'system', 'content': PLANNING_SYSTEM},
        {'role': 'user', 'content': '问题：{}\n参考资料：{}'.format(question, kb_text or '无')},
        ],
    )
    return resp.choices[0].message.content

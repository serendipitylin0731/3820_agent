# agents/agent_main.py
import json
import os
from llm_client import chat, client
SPLIT_SYSTEM = '''
你是“3820”战略工程知识系统的总控智能体。
请把用户问题拆分为若干子任务，子任务类型只能从以下四类中选择：
- planning：战略规划与路径分析
- indicator：经济指标查询与计算
- spatial：空间布局（港口、园区、城市更新等）分析
- evaluation：目标达成率与效果评估
每个子任务至少包含type与question两个字段；indicator任务还应尽可能提供key（指标键）与years（年份数组），spatial任务应提供keyword及可选stype。只输出合法JSON数组。
注意：必须输出合法JSON，不要添加Markdown代码围栏；字符串键和值使用英文双引号。
示例：[ {"type":"indicator","question":"2010年福州GDP是多少？","key":"gdp","years":[2010]},
{"type":"evaluation","question":"1995年翻一番目标完成情况如何？"} ]
'''
def split_task(question):
    resp = client.chat.completions.create(
        model=os.environ.get('LLM_MODEL', 'doubao-seed-2-1-pro-260628'),
        messages=[
            {'role': 'system', 'content': SPLIT_SYSTEM},
            {'role': 'user', 'content': question},
        ],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)
def summarize(question, results):
    # 将各专业智能体结果汇总为最终答案（示例为结构化拼接）
    parts = [f'问题：{question}']
    for key, value in results.items():
        parts.append(f'[{key}结果] {value}')
    return '\n'.join(parts)

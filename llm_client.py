# llm_client.py —— 大模型客户端（火山方舟·豆包）
import os
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
BASE_URL = os.getenv('ARK_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3')
LLM_MODEL = os.getenv('LLM_MODEL', 'doubao-seed-2-1-pro-260628')  # 以控制台实际开通的模型ID为准
client = OpenAI(
    base_url=BASE_URL,
api_key=os.getenv('ARK_API_KEY') or (_ for _ in ()).throw(RuntimeError('请先配置ARK_API_KEY')),
)
def chat(messages, temperature=0.3):
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content

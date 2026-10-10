"""模型客户端在实际调用时创建，离线导入不要求 API 密钥。"""

from openai import OpenAI

from config import Settings, get_settings
from resilience import call_llm_safe


def get_client(settings: Settings | None = None) -> OpenAI:
    settings = settings or get_settings()
    return OpenAI(
        base_url=settings.ark_base_url,
        api_key=settings.require_api_key(),
        timeout=settings.request_timeout,
    )


def chat(messages, temperature=0.3, *, settings: Settings | None = None, client=None):
    settings = settings or get_settings()
    model = settings.require_chat_model()
    active_client = client if client is not None else get_client(settings)
    return call_llm_safe(active_client, model, messages, settings.request_timeout, temperature)

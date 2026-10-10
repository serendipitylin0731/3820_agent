# resilience.py —— 重试、超时与降级
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import get_settings
class ModelAPIError(Exception):
    # 模型调用异常（超时、限流、5xx等）
    pass
@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, max=8),
       retry=retry_if_exception_type((ModelAPIError, TimeoutError)),
       reraise=True)
def call_llm_safe(client, model, messages, timeout=None):
    if timeout is None:
        timeout = get_settings().request_timeout
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, timeout=timeout,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        # 仅对超时、限流和服务端瞬时错误重试；认证或参数错误不重试。
        if isinstance(exc, TimeoutError) or getattr(exc, 'status_code', None) in (429, 500, 502, 503, 504):
            raise ModelAPIError(str(exc)) from exc
        raise
def call_with_fallback(client, model, messages, backup_model=None):
    # 重试失败后的降级：备用模型或明确提示
    try:
        return call_llm_safe(client, model, messages)
    except ModelAPIError:
        if backup_model:
            return call_llm_safe(client, backup_model, messages)
        return '【降级】模型服务暂不可用，请稍后重试。'

# resilience.py 续：基于LangGraph Checkpoint的状态回滚
def find_checkpoint(app, thread_id, checkpoint_id):
    # 先定位历史快照；具体恢复/续跑接口应按安装的LangGraph版本实现
    config = {'configurable': {'thread_id': thread_id}}
    for checkpoint in app.get_state_history(config):
        current_id = checkpoint.config.get('configurable', {}).get('checkpoint_id')
        if current_id == checkpoint_id:
            return checkpoint
    return None
# 使用示例：先通过find_checkpoint定位目标快照，再按当前LangGraph版本文档调用恢复/续跑接口。
# checkpoint = rollback_to(app, thread_id='t001', step=1)

# resilience.py 续：结构化日志
import json
import logging
logger = logging.getLogger('3820_agent')
def log_event(event, request_id, thread_id, level='info', **extra):
    record = {
        'event': event,
        'request_id': request_id,
        'thread_id': thread_id,
        'level': level,
        **extra,
    }
    getattr(logger, level)(json.dumps(record, ensure_ascii=False))

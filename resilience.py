"""仅对临时模型错误重试；恢复从已存快照显式选择。"""
import json
import logging
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential
from openai import APIConnectionError, APITimeoutError

logger = logging.getLogger('3820_agent')


def transient_error(exc):
    return isinstance(exc, (TimeoutError, ConnectionError, APIConnectionError, APITimeoutError)) or getattr(exc, 'status_code', None) in (429, 500, 502, 503, 504)


def call_llm_safe(client, model, messages, timeout, temperature=0.3):
    for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8),
                            retry=retry_if_exception(transient_error), reraise=True):
        with attempt:
            result = client.chat.completions.create(model=model, messages=messages, timeout=timeout, temperature=temperature)
            return result.choices[0].message.content


def find_checkpoint(graph, thread_id, checkpoint_id):
    config = {'configurable': {'thread_id': thread_id}}
    for snapshot in graph.get_state_history(config):
        if snapshot.config.get('configurable', {}).get('checkpoint_id') == checkpoint_id:
            return snapshot
    return None


def log_event(event, request_id, thread_id, level='info', **extra):
    allowed = {key: value for key, value in extra.items() if key in ('role', 'node', 'duration_ms', 'error_type')}
    getattr(logger, level)(json.dumps({'event': event, 'request_id': request_id,
                                       'thread_id': thread_id, **allowed}, ensure_ascii=False))

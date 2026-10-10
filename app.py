"""HTTP 接口；默认离线可运行，配置 SERVICE_API_KEY 后启用请求认证。"""
import hmac
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import get_settings
from contracts import AgentResult, ChatError, ChatRequest, ChatResponse, ErrorInfo
from graph import ask

logger = logging.getLogger('3820_agent')
_counters = defaultdict(int)
_windows = defaultdict(deque)
_lock = Lock()


def _error(status, code, message, request_id=None):
    payload = ChatError(request_id=request_id or str(uuid.uuid4()),
                        error=ErrorInfo(code=code, message=message))
    return JSONResponse(status_code=status, content=payload.model_dump())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level))
    yield


app = FastAPI(title='3820多智能体系统', lifespan=lifespan)


@app.middleware('http')
async def protect_and_measure(request: Request, call_next):
    started = time.monotonic()
    request_id = str(uuid.uuid4())
    settings = get_settings()
    if request.url.path == '/health':
        return await call_next(request)
    if settings.service_api_key:
        supplied = request.headers.get('x-api-key', '')
        if not hmac.compare_digest(supplied, settings.service_api_key.get_secret_value()):
            return _error(401, 'unauthorized', '未授权请求', request_id)
    if request.headers.get('content-length'):
        try:
            if int(request.headers['content-length']) > settings.max_body_bytes:
                return _error(413, 'body_too_large', '请求体过大', request_id)
        except ValueError:
            return _error(400, 'invalid_request', '请求头格式无效', request_id)
    if request.url.path == '/chat':
        identity = request.headers.get('x-api-key') or (request.client.host if request.client else 'unknown')
        now = time.monotonic()
        with _lock:
            window = _windows[identity]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= settings.rate_limit_per_minute:
                return _error(429, 'rate_limited', '请求过于频繁', request_id)
            window.append(now)
    body = await request.body()
    if len(body) > settings.max_body_bytes:
        return _error(413, 'body_too_large', '请求体过大', request_id)
    response = await call_next(request)
    duration = time.monotonic() - started
    with _lock:
        _counters[f'{request.url.path}:{response.status_code}'] += 1
    logger.info('request_id=%s path=%s status=%s duration_ms=%.1f',
                request_id, request.url.path, response.status_code, duration * 1000)
    response.headers['X-Request-ID'] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, _exc: RequestValidationError):
    return _error(422, 'invalid_request', '请求字段缺失或格式无效')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/metrics')
def metrics():
    with _lock:
        return {'requests': dict(_counters)}


def _as_agent_result(role: str, raw) -> AgentResult:
    if isinstance(raw, dict) and 'status' in raw:
        return AgentResult.model_validate({**raw, 'role': raw.get('role', role.split('_')[0])})
    if isinstance(raw, dict) and 'error' in raw:
        return AgentResult(role=role.split('_')[0], status='error',
                           error=ErrorInfo(code='agent_error', message='该子任务暂无法完成'))
    return AgentResult(role=role.split('_')[0], status='ok', data=raw)


@app.post('/chat', response_model=ChatResponse)
def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())
    try:
        result = ask(req.question, thread_id=req.thread_id or request_id)
        results = {role: _as_agent_result(role, raw) for role, raw in result.get('results', {}).items()}
        failures = sum(item.status != 'ok' for item in results.values())
        status = 'error' if not results or failures == len(results) else 'partial' if failures else 'ok'
        return ChatResponse(request_id=request_id, status=status,
                            answer=result.get('answer', ''), results=results)
    except Exception:
        logger.error('处理请求失败 request_id=%s', request_id)
        return _error(500, 'internal_error', '服务暂时不可用，请稍后重试', request_id)

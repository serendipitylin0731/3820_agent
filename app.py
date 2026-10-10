"""HTTP 边界：请求契约、按客户端授权、限流与观测。"""
import hmac
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from config import ConfigurationError, get_settings
from contracts import AgentResult, ChatError, ChatRequest, ChatResponse, ErrorInfo
from graph import ask
from knowledge.knowledge_base import retrieval_metrics
from resilience import timeout_error

logger = logging.getLogger('3820_agent')
_counters = defaultdict(int)
_windows = defaultdict(deque)
_latencies = deque(maxlen=1000)
_lock = Lock()
_active = 0
_peak_active = 0
_agent_errors = 0
_timeout_requests = 0
_SCOPES = {'/chat':'chat', '/metrics':'metrics'}


def _error(status, code, message, request_id=None):
    payload = ChatError(request_id=request_id or str(uuid.uuid4()),
                        error=ErrorInfo(code=code, message=message))
    return JSONResponse(status_code=status, content=payload.model_dump())


def _client_registry(settings):
    if settings.service_clients_json is None:
        return {}
    try:
        clients = json.loads(settings.service_clients_json.get_secret_value())
        if not isinstance(clients, dict) or not clients:
            raise ValueError()
        for client_id, spec in clients.items():
            if (not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', client_id)
                or not isinstance(spec, dict)
                or not isinstance(spec.get('api_key'), str)
                or not spec['api_key']
                or not isinstance(spec.get('scopes'), list)
                or not set(spec['scopes']) <= {'chat', 'metrics', 'docs'}):
                raise ValueError()
        return clients
    except (ValueError, TypeError, KeyError):
        raise ConfigurationError('SERVICE_CLIENTS_JSON 格式无效') from None


def _authenticate(request, settings):
    clients = _client_registry(settings)
    if clients:
        client_id = request.headers.get('x-client-id', '')
        spec = clients.get(client_id)
        key = request.headers.get('x-api-key', '')
        if spec is None or not hmac.compare_digest(key, spec['api_key']):
            return None, 401
        needed = _SCOPES.get(request.url.path, 'docs')
        return (client_id, None) if needed in spec['scopes'] else (None, 403)
    if settings.service_api_key:
        key = request.headers.get('x-api-key', '')
        if not hmac.compare_digest(key, settings.service_api_key.get_secret_value()):
            return None, 401
        return 'default', None
    return 'anonymous', None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    _client_registry(settings)
    logging.basicConfig(level=getattr(logging, settings.log_level))
    yield


app = FastAPI(title='3820多智能体系统', lifespan=lifespan)


@app.middleware('http')
async def protect_and_measure(request: Request, call_next):
    global _active, _peak_active
    started = time.monotonic()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    settings = get_settings()

    def finish(response):
        duration = (time.monotonic() - started) * 1000
        with _lock:
            _counters[f'{request.url.path}:{response.status_code}'] += 1
            _latencies.append(duration)
        logger.info('request_id=%s path=%s status=%s duration_ms=%.1f',
                    request_id, request.url.path, response.status_code, duration)
        response.headers['X-Request-ID'] = request_id
        return response

    if request.url.path in ('/health', '/favicon.ico'):
        return finish(await call_next(request))
    principal, auth_error = _authenticate(request, settings)
    if auth_error:
        return finish(_error(auth_error, 'unauthorized' if auth_error == 401 else 'forbidden',
                             '未授权请求', request_id))
    request.state.principal = principal
    length = request.headers.get('content-length')
    if length is not None:
        try:
            if int(length) > settings.max_body_bytes:
                return finish(_error(413, 'body_too_large', '请求体过大', request_id))
        except ValueError:
            return finish(_error(400, 'invalid_request', '请求头格式无效', request_id))
    if request.url.path == '/chat':
        identity = principal if principal != 'anonymous' else (request.client.host if request.client else 'unknown')
        now = time.monotonic()
        with _lock:
            window = _windows[identity]
            while window and window[0] <= now - 60:
                window.popleft()
            limited = len(window) >= settings.rate_limit_per_minute
            if not limited:
                window.append(now)
        if limited:
            return finish(_error(429, 'rate_limited', '请求过于频繁', request_id))
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.max_body_bytes:
            return finish(_error(413, 'body_too_large', '请求体过大', request_id))
        chunks.append(chunk)
    request._body = b''.join(chunks)
    with _lock:
        _active += 1
        _peak_active = max(_peak_active, _active)
    try:
        response = await call_next(request)
    finally:
        with _lock:
            _active -= 1
    return finish(response)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, _exc: RequestValidationError):
    return _error(422, 'invalid_request', '请求字段缺失或格式无效', request.state.request_id)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/', include_in_schema=False)
def home():
    return RedirectResponse('/docs', status_code=302)


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get('/metrics')
def metrics():
    with _lock:
        ordered = sorted(_latencies)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * .95))] if ordered else None
        requests = dict(_counters)
        total = sum(requests.values())
        failed = sum(count for route, count in requests.items() if int(route.rsplit(':', 1)[1]) >= 500)
        chat_total = sum(count for route, count in requests.items() if route.startswith('/chat:'))
        snapshot = {'requests':requests, 'active':_active, 'peak_active':_peak_active,
                    'p95_ms':p95, 'http_error_rate':failed / total if total else 0,
                    'agent_errors':_agent_errors,
                    'timeout_requests':_timeout_requests,
                    'timeout_rate':_timeout_requests / chat_total if chat_total else 0}
    retrieval = retrieval_metrics()
    count = retrieval.get('requests', 0)
    snapshot['retrieval'] = {**retrieval,
                             'no_hit_rate': retrieval.get('insufficient_evidence', 0) / count if count else 0,
                             'low_relevance_rate': retrieval.get('low_relevance', 0) / count if count else 0}
    return snapshot


def _as_agent_result(role: str, raw) -> AgentResult:
    if isinstance(raw, dict) and 'status' in raw:
        return AgentResult.model_validate({**raw, 'role': raw.get('role', role.split('_')[0])})
    if isinstance(raw, dict) and 'error' in raw:
        return AgentResult(role=role.split('_')[0], status='error',
                           error=ErrorInfo(code='agent_error', message='该子任务暂无法完成'))
    return AgentResult(role=role.split('_')[0], status='ok', data=raw)


@app.post('/chat', response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    global _agent_errors, _timeout_requests
    request_id = request.state.request_id
    principal = request.state.principal
    thread_id = f'{principal}:{req.thread_id or request_id}'
    try:
        result = ask(req.question, thread_id=thread_id, request_id=request_id)
        results = {role: _as_agent_result(role, raw) for role, raw in result.get('results', {}).items()}
        failures = sum(item.status == 'error' for item in results.values())
        with _lock:
            _agent_errors += sum(item.status == 'error' for item in results.values())
            _timeout_requests += any(item.error and item.error.code.endswith('timeout')
                                     for item in results.values())
        status = 'error' if not results or failures == len(results) else 'partial' if failures else 'ok'
        return ChatResponse(request_id=request_id, status=status,
                            answer=result.get('answer', ''), results=results)
    except Exception as exc:
        with _lock:
            _timeout_requests += timeout_error(exc)
        logger.error('处理请求失败 request_id=%s error_type=%s', request_id, type(exc).__name__)
        return _error(500, 'internal_error', '服务暂时不可用，请稍后重试', request_id)

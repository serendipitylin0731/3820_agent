"""HTTP 边界：请求契约、按客户端授权、限流与观测。"""
import hmac
import asyncio
import json
import logging
import re
import time
import uuid
from urllib.parse import quote
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import websockets

from config import ConfigurationError, get_settings
from contracts import AgentResult, ChatError, ChatRequest, ChatResponse, ErrorInfo
from graph import ask
from knowledge.knowledge_base import retrieval_metrics
from knowledge.library_search import cited_record, cited_slide, download_file, media_text, preview_text, public_record, search_documents
from resilience import timeout_error
from voice_cloud import (VoiceServiceError, asr_headers, asr_init_packet, asr_packet,
                         parse_asr_response, synthesize_mp3)

logger = logging.getLogger('3820_agent')
_counters = defaultdict(int)
_windows = defaultdict(deque)
_latencies = deque(maxlen=1000)
_lock = Lock()
_active = 0
_peak_active = 0
_agent_errors = 0
_timeout_requests = 0
_SCOPES = {'/chat':'chat', '/voice/tts':'chat', '/metrics':'metrics'}
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


app = FastAPI(title='3820多智能体系统', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
_WEB_DIR = Path(__file__).with_name('web')
app.mount('/assets', StaticFiles(directory=_WEB_DIR), name='assets')


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

    if request.url.path in ('/', '/health', '/favicon.ico') or request.url.path.startswith('/assets/'):
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
    if request.url.path in ('/chat', '/voice/tts'):
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


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


@app.post('/voice/tts')
def voice_tts(req: VoiceSynthesisRequest, request: Request):
    settings = get_settings()
    if not settings.voice_api_key:
        return _error(503, 'voice_unconfigured', '语音服务尚未配置', request.state.request_id)
    try:
        audio = synthesize_mp3(req.text, settings)
    except VoiceServiceError as exc:
        return _error(502, 'voice_failed', str(exc), request.state.request_id)
    return Response(content=audio, media_type='audio/mpeg',
                    headers={'Cache-Control': 'no-store'})


def _voice_authorized(auth: dict, settings) -> bool:
    clients = _client_registry(settings)
    if clients:
        spec = clients.get(auth.get('client_id', ''))
        return bool(spec and 'chat' in spec['scopes'] and
                    hmac.compare_digest(auth.get('service_key', ''), spec['api_key']))
    if settings.service_api_key:
        return hmac.compare_digest(auth.get('service_key', ''),
                                   settings.service_api_key.get_secret_value())
    return True


@app.websocket('/voice/asr')
async def voice_asr(websocket: WebSocket):
    await websocket.accept()
    settings = get_settings()
    if not settings.voice_api_key:
        await websocket.send_json({'type': 'error', 'message': '语音服务尚未配置'})
        await websocket.close(code=4403)
        return
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=8)
        if not isinstance(auth, dict) or not _voice_authorized(auth, settings):
            await websocket.send_json({'type': 'error', 'message': '请先填写网站访问密码'})
            await websocket.close(code=4401)
            return
        identity = (auth.get('client_id') if settings.service_clients_json else
                    websocket.client.host if websocket.client else 'unknown')
        now = time.monotonic()
        with _lock:
            window = _windows[f'voice:{identity}']
            while window and window[0] <= now - 60:
                window.popleft()
            limited = len(window) >= settings.rate_limit_per_minute
            if not limited:
                window.append(now)
        if limited:
            await websocket.send_json({'type': 'error', 'message': '语音请求过于频繁，请稍后重试'})
            await websocket.close(code=4429)
            return
        async with websockets.connect(settings.voice_asr_ws_url,
                                      additional_headers=asr_headers(settings),
                                      open_timeout=12, max_size=2_000_000) as provider:
            await provider.send(asr_init_packet())

            async def read_results():
                latest = ''
                async for frame in provider:
                    if not isinstance(frame, bytes):
                        continue
                    payload, last = parse_asr_response(frame)
                    text = payload.get('result', {}).get('text', '').strip()
                    if text and text != latest:
                        latest = text
                        await websocket.send_json({'type': 'interim', 'text': text})
                    if last:
                        return latest
                return latest

            results = asyncio.create_task(read_results())
            sequence = 2
            pending = None
            total = 0
            try:
                while True:
                    if results.done():
                        await results
                    message = await asyncio.wait_for(websocket.receive(), timeout=40)
                    if message['type'] == 'websocket.disconnect':
                        return
                    chunk = message.get('bytes')
                    if chunk is not None:
                        if not chunk or len(chunk) > 32_000 or len(chunk) % 2:
                            raise VoiceServiceError('音频数据格式无效')
                        total += len(chunk)
                        if total > 1_280_000:
                            raise VoiceServiceError('语音提问不能超过 40 秒')
                        if pending is not None:
                            await provider.send(asr_packet(2, 1, sequence, pending,
                                                           serialization=0))
                            sequence += 1
                        pending = chunk
                        continue
                    if message.get('text'):
                        command = json.loads(message['text'])
                        if command.get('type') == 'finish':
                            break
                if pending is None:
                    raise VoiceServiceError('没有收到语音，请重新提问')
                await provider.send(asr_packet(2, 3, -sequence, pending,
                                               serialization=0))
                final = await asyncio.wait_for(results, timeout=12)
                if not final:
                    raise VoiceServiceError('没有识别到清晰的问题')
                await websocket.send_json({'type': 'final', 'text': final})
                await websocket.close()
            finally:
                if not results.done():
                    results.cancel()
    except WebSocketDisconnect:
        pass
    except (VoiceServiceError, TimeoutError, websockets.WebSocketException,
            OSError, ValueError, TypeError) as exc:
        logger.warning('语音识别失败 error_type=%s', type(exc).__name__)
        try:
            await websocket.send_json({'type': 'error', 'message':
                                       str(exc) if isinstance(exc, VoiceServiceError)
                                       else '语音识别暂时不可用，请稍后重试'})
            await websocket.close(code=1011)
        except RuntimeError:
            pass


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(_WEB_DIR / 'index.html')


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get('/library/search')
def library_search(q: str = ''):
    if len(q) > 120:
        return _error(422, 'invalid_request', '关键词过长')
    return {'results': search_documents(q), 'query': q.strip()}


@app.get('/library/{doc_id}/preview')
def library_preview(doc_id: str):
    found = public_record(doc_id)
    if found is None:
        return _error(404, 'not_found', '资料不存在')
    item, path = found
    content = preview_text(item, path)
    if content is not None:
        return {'id': doc_id, 'title': item['title'], 'format': path.suffix.lower().lstrip('.'),
                'content': content, 'pages': item.get('pages', []),
                'source_url': item.get('source_url'), 'collection': item.get('collection')}
    if path.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.m4v'}:
        return FileResponse(path, filename=path.name, content_disposition_type='inline',
                            headers={'X-Source-Title': quote(item['title'])})
    return _error(415, 'unsupported_preview', '该格式暂不支持在线预览')


@app.get('/library/{doc_id}/text')
def library_media_text(doc_id: str):
    found = public_record(doc_id)
    if found is None:
        return _error(404, 'not_found', '资料不存在')
    item, _ = found
    content = media_text(item)
    if content is None:
        return _error(404, 'not_found', '该资料没有可读取的文字')
    return {'id': doc_id, 'content': content}


@app.get('/library/{doc_id}/download')
def library_download(doc_id: str):
    found = public_record(doc_id)
    if found is None:
        return _error(404, 'not_found', '资料不存在')
    item, path = found
    try:
        target = download_file(item, path)
    except FileNotFoundError:
        return _error(404, 'not_found', '下载文件尚未生成')
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', item['title']).strip(' .')[:150]
    return FileResponse(target, filename=f'{safe_title}{target.suffix}', content_disposition_type='attachment')


@app.get('/sources/open')
def open_cited_source(file: str):
    found = cited_record(file)
    if found is None:
        return _error(404, 'not_found', '该来源没有可访问的原件')
    item, path = found
    if path.suffix.lower() == '.md' and item.get('download_path'):
        try:
            path = download_file(item, path)
        except FileNotFoundError:
            return _error(404, 'not_found', '下载文件尚未生成')
    inline = path.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.m4v', '.md'}
    return FileResponse(path, filename=path.name,
                        content_disposition_type='inline' if inline else 'attachment',
                        media_type='text/plain; charset=utf-8' if path.suffix.lower() == '.md' else None)


@app.get('/sources/preview')
def preview_cited_source(file: str):
    found = cited_record(file)
    if found is None:
        return _error(404, 'not_found', '该来源没有可预览的原件')
    item, path = found
    if item.get('category') == 'presentations':
        count = item.get('preview_page_count', 0)
        if not count or cited_slide(file, 1) is None:
            return _error(404, 'not_found', '演示文稿尚未生成逐页预览图')
        return {'title': item['title'], 'format': 'slides', 'page_count': count}
    content = preview_text(item, path)
    if content is not None:
        return {'title': item['title'], 'format': path.suffix.lower().lstrip('.'),
                'content': content, 'pages': item.get('pages', []),
                'source_url': item.get('source_url')}
    if path.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.m4v'}:
        return FileResponse(path, filename=path.name, content_disposition_type='inline',
                            headers={'X-Source-Title': quote(item['title'])})
    return _error(415, 'unsupported_preview', '该格式暂不支持在线预览')


@app.get('/sources/slide')
def preview_cited_slide(file: str, page: int):
    path = cited_slide(file, page)
    if path is None:
        return _error(404, 'not_found', '该页不存在')
    return FileResponse(path, media_type='image/webp', content_disposition_type='inline')


@app.get('/sources/text')
def cited_media_text(file: str):
    found = cited_record(file)
    if found is None:
        return _error(404, 'not_found', '资料不存在')
    content = media_text(found[0])
    return {'content': content} if content is not None else _error(404, 'not_found', '该资料没有可读取的文字')


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

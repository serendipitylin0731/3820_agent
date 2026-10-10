import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import get_settings
from contracts import AgentResult, ChatError, ChatRequest, ChatResponse, ErrorInfo
from graph import ask


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.require_service_ready()
    logging.basicConfig(level=getattr(logging, settings.log_level))
    yield


app = FastAPI(title='3820多智能体系统', lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, _exc: RequestValidationError):
    payload = ChatError(
        request_id=str(uuid.uuid4()),
        error=ErrorInfo(code='invalid_request', message='请求字段缺失或格式无效'),
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


def _as_agent_result(role: str, raw) -> AgentResult:
    if isinstance(raw, dict) and 'status' in raw:
        return AgentResult.model_validate({**raw, 'role': role})
    if isinstance(raw, dict) and 'error' in raw:
        return AgentResult(
            role=role,
            status='error',
            error=ErrorInfo(code='agent_error', message='该子任务暂无法完成'),
        )
    return AgentResult(role=role, status='ok', data=raw)


@app.post('/chat', response_model=ChatResponse, responses={422: {'model': ChatError}, 500: {'model': ChatError}})
def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())
    try:
        result = ask(req.question, thread_id=req.thread_id or request_id)
        results = {
            role: _as_agent_result(role, raw)
            for role, raw in result.get('results', {}).items()
        }
        failures = sum(item.status != 'ok' for item in results.values())
        status = 'error' if not results or failures == len(results) else 'partial' if failures else 'ok'
        return ChatResponse(
            request_id=request_id,
            status=status,
            answer=result.get('answer', ''),
            results=results,
        )
    except Exception as exc:
        logging.error(
            '处理/chat请求失败 request_id=%s error_type=%s',
            request_id, type(exc).__name__,
        )
        payload = ChatError(
            request_id=request_id,
            error=ErrorInfo(code='internal_error', message='服务暂时不可用，请稍后重试'),
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

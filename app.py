# app.py —— FastAPI 对外服务
import uuid
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from graph import ask
app = FastAPI(title='3820多智能体系统')
class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = None
class ChatResponse(BaseModel):
    request_id: str
    answer: str
    results: dict
@app.post('/chat', response_model=ChatResponse)
def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())
    try:
        result = ask(req.question, thread_id=req.thread_id or request_id)
        return ChatResponse(
            request_id=request_id,
            answer=result.get('answer', ''),
            results=result.get('results', {}),
        )
    except Exception as exc:
     logging.exception('处理/chat请求失败 request_id=%s', request_id)
     raise HTTPException(status_code=500, detail={'request_id': request_id, 'error': '服务暂时不可用，请稍后重试'})

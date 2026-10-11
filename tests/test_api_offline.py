from fastapi.testclient import TestClient
import pytest

import app as api
from config import ConfigurationError, Settings
from contracts import ChatError, ChatResponse


def test_startup_works_without_model_key(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: Settings())
    with TestClient(api.app) as client:
        assert client.get('/health').json() == {'status': 'ok'}


def test_browser_root_opens_chat_ui_without_api_docs(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    with TestClient(api.app) as client:
        root = client.get('/')
        assert root.status_code == 200
        assert '战略知识助手' in root.text
        assert 'id="chat-form"' in root.text
        assert '3820 背景' in root.text
        assert 'id="background-document"' in root.text
        assert 'id="history-list"' in root.text
        assert '<body data-view="chat">' in root.text
        assert 'id="background-timeline" hidden' in root.text
        assert 'href="/assets/logo.svg"' in root.text
        assert '我的 ID：_serendipity · 开发者' in root.text
        assert 'id="history-panel"' in root.text
        assert 'aria-controls="background-timeline"' not in root.text
        assert '接口文档' not in root.text
        assert client.get('/assets/style.css').status_code == 200
        frontend = client.get('/assets/app.js').text
        assert "fetch('/chat'" in frontend
        assert "historyPanel.hidden = true" in frontend
        assert "backgroundTimeline.hidden = true" in frontend
        assert '分析过程' not in frontend
        assert '待独立核验' not in frontend
        assert client.get('/assets/history_store.js').status_code == 200
        assert client.get('/assets/logo.svg').status_code == 200
        assert client.get('/docs').status_code == 404
        assert client.get('/redoc').status_code == 404
        assert client.get('/openapi.json').status_code == 404
        assert client.get('/favicon.ico').status_code == 204


def test_browser_can_open_ui_before_entering_service_key(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings(service_api_key='test-only-key'))
    with TestClient(api.app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        assert client.post('/chat', json={'question': '1995年GDP是多少？'}).status_code == 401
        assert client.get('/docs').status_code == 401


def test_chat_and_validation_use_shared_contract_without_network(monkeypatch):
    settings = Settings(ark_api_key="test-only-key", llm_model="fake-chat", embed_model="fake-embed")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(
        api, "ask", lambda question, thread_id, request_id=None: {
            "answer": "本地夹具答案",
            "results": {"indicator_1": {"value": 3123.41}},
        },
    )
    with TestClient(api.app) as client:
        response = client.post("/chat", json={"question": "GDP?", "thread_id": "offline-1"})
        assert response.status_code == 200
        payload = ChatResponse.model_validate(response.json())
        assert payload.status == "ok"
        assert payload.results["indicator_1"].sources == []

        invalid = client.post("/chat", json={"question": "   "})
        assert invalid.status_code == 422
        error = ChatError.model_validate(invalid.json())
        assert error.error.code == "invalid_request"


def test_internal_error_does_not_expose_exception(monkeypatch, caplog):
    settings = Settings(ark_api_key="test-only-key", llm_model="fake-chat", embed_model="fake-embed")
    monkeypatch.setattr(api, "get_settings", lambda: settings)

    def fail(_question, thread_id, request_id=None):
        raise RuntimeError("private-test-value")

    monkeypatch.setattr(api, "ask", fail)
    with TestClient(api.app) as client:
        response = client.post("/chat", json={"question": "GDP?"})
    assert response.status_code == 500
    assert ChatError.model_validate(response.json()).error.code == "internal_error"
    assert "private-test-value" not in response.text
    assert "private-test-value" not in caplog.text


def test_insufficient_evidence_is_handled_answer_not_service_error(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    monkeypatch.setattr(api, 'ask', lambda question, thread_id, request_id=None: {
        'answer': '缺少比较对象，无法评估',
        'results': {'evaluation': {'role': 'evaluation', 'status': 'insufficient_evidence',
                                   'data': '缺少比较对象，无法评估'}}})
    with TestClient(api.app) as client:
        payload = client.post('/chat', json={'question': '2000年目标是否达成？'}).json()
    assert payload['status'] == 'ok'
    assert payload['results']['evaluation']['status'] == 'insufficient_evidence'

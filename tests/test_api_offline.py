from fastapi.testclient import TestClient
import pytest

import app as api
from config import ConfigurationError, Settings
from contracts import ChatError, ChatResponse


def test_startup_works_without_model_key(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: Settings())
    with TestClient(api.app) as client:
        assert client.get('/health').json() == {'status': 'ok'}


def test_browser_root_opens_api_docs_without_missing_favicon(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    with TestClient(api.app) as client:
        root = client.get('/', follow_redirects=False)
        assert root.status_code == 302
        assert root.headers['location'] == '/docs'
        assert client.get('/docs').status_code == 200
        assert client.get('/favicon.ico').status_code == 204


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

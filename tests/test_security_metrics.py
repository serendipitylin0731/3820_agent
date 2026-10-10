import json
from fastapi.testclient import TestClient
import pytest

import app as api
from config import ConfigurationError, Settings


def test_scoped_clients_and_session_namespaces(monkeypatch):
    settings = Settings(service_clients_json=json.dumps({
        'alice': {'api_key':'alice-secret', 'scopes':['chat']},
        'bob': {'api_key':'bob-secret', 'scopes':['chat','metrics']},
    }))
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    calls = []
    def fake(question, thread_id, request_id=None):
        calls.append(thread_id)
        return {'answer':'ok','results':{'indicator':{'value':1}}}
    monkeypatch.setattr(api, 'ask', fake)
    api._windows.clear()
    with TestClient(api.app) as client:
        alice = {'X-Client-ID':'alice','X-API-Key':'alice-secret'}
        bob = {'X-Client-ID':'bob','X-API-Key':'bob-secret'}
        assert client.get('/metrics', headers=alice).status_code == 403
        assert client.post('/chat', json={'question':'GDP','thread_id':'same'}, headers=alice).status_code == 200
        assert client.post('/chat', json={'question':'GDP','thread_id':'same'}, headers=bob).status_code == 200
        assert calls == ['alice:same', 'bob:same']
        assert client.get('/metrics', headers=bob).json()['retrieval'] is not None
        assert client.post('/chat', json={'question':'GDP'}, headers={'X-Client-ID':'bob','X-API-Key':'wrong'}).status_code == 401


def test_streamed_body_limit_and_error_request_id(monkeypatch):
    settings = Settings(max_body_bytes=1024)
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    with TestClient(api.app) as client:
        response = client.post('/chat', content=(b'x' * 600 for _ in range(3)),
                               headers={'Content-Type':'application/json'})
        assert response.status_code == 413
        assert response.headers['X-Request-ID'] == response.json()['request_id']


def test_invalid_client_registry_fails_startup(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings(service_clients_json='{bad json'))
    with pytest.raises(ConfigurationError, match='SERVICE_CLIENTS_JSON'):
        with TestClient(api.app):
            pass


def test_metrics_include_timeout_and_retrieval_rates(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    monkeypatch.setattr(api, 'retrieval_metrics', lambda: {
        'requests': 4, 'insufficient_evidence': 2, 'low_relevance': 1})
    monkeypatch.setattr(api, 'ask', lambda question, thread_id, request_id=None: {
        'answer': '子任务执行超时',
        'results': {'indicator': {'role': 'indicator', 'status': 'error',
                                  'error': {'code': 'agent_timeout', 'message': '子任务执行超时'}}}})
    prior = api._timeout_requests
    with TestClient(api.app) as client:
        assert client.post('/chat', json={'question':'GDP?'}).status_code == 200
        body = client.get('/metrics').json()
    assert body['timeout_requests'] == prior + 1
    assert body['timeout_rate'] > 0
    assert body['retrieval']['no_hit_rate'] == 0.5
    assert body['retrieval']['low_relevance_rate'] == 0.25

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from config import Settings
from tools.tools import call_tool
import app as api


def test_tool_validation_and_sources():
    indicator = call_tool('query_indicator', {'key':'gdp','years':[2010]})
    assert indicator['data']['values'][2010] == 3123.41
    assert indicator['sources'][0]['verified'] is False
    assert call_tool('knowledge_retrieve', {'query':'三阶段目标'})['data']
    assert call_tool('query_spatial', {'keyword':'不存在'})['status'] == 'insufficient_evidence'
    assert call_tool('query_indicator', {'key':'bad'})['status'] == 'error'
    with pytest.raises(ValidationError):
        call_tool('query_indicator', {'key':'gdp','extra':1})
    with pytest.raises(ValueError):
        call_tool('unknown', {})


def test_authenticated_api_and_limits(monkeypatch):
    settings = Settings(service_api_key='local-secret', rate_limit_per_minute=2, max_body_bytes=1024)
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    monkeypatch.setattr(api, 'ask', lambda question, thread_id, request_id=None: {'answer':'ok','results':{'indicator': {'value':1}}})
    api._windows.clear()
    with TestClient(api.app) as client:
        assert client.post('/chat', json={'question':'GDP'}).status_code == 401
        headers = {'X-API-Key':'local-secret'}
        assert client.post('/chat', json={'question':'GDP'}, headers=headers).status_code == 200
        assert client.post('/chat', json={'question':'GDP'}, headers=headers).status_code == 200
        assert client.post('/chat', json={'question':'GDP'}, headers=headers).status_code == 429
        assert client.get('/metrics', headers=headers).status_code == 200

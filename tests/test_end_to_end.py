from fastapi.testclient import TestClient
import app as api
from config import Settings


def test_offline_chat_end_to_end(monkeypatch, tmp_path):
    import graph
    settings = Settings(checkpoint_path=tmp_path / 'sessions.sqlite3')
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(__import__('agents.agent_main', fromlist=['get_settings']), 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    with TestClient(api.app) as client:
        response = client.post('/chat', json={'question':'2010年GDP是多少？', 'thread_id':'a'})
        assert response.status_code == 200
        body = response.json()
        assert response.headers['X-Request-ID'] == body['request_id']
        assert body['results']['indicator']['data']['values']['2010'] == 3123.41
        assert body['results']['indicator']['sources'][0]['verified'] is False
        assert client.get('/metrics').json()['p95_ms'] is not None
    graph.get_graph.cache_clear()

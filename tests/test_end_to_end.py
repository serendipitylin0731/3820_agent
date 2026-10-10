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


def test_offline_target_and_growth_answers(monkeypatch, tmp_path):
    import graph
    from agents import agent_main
    settings = Settings(checkpoint_path=tmp_path / 'target_growth.sqlite3')
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    monkeypatch.setattr(agent_main, 'get_settings', lambda: settings)
    graph.get_graph.cache_clear()
    with TestClient(api.app) as client:
        target = client.post('/chat', json={'question':'1995年GDP目标是多少？'}).json()
        assert target['status'] == 'ok'
        assert '204.8' in target['answer'] and '并非原始目标表列值' in target['answer']
        assert '221' in target['answer']
        assert target['results']['indicator']['sources'][1]['page_or_slide'] == '预览第45页'

        growth = client.post('/chat', json={'question':'1990年至1995年GDP增长率是多少？'}).json()
        assert growth['status'] == 'ok'
        assert '353.3%' in growth['answer']

        blocked = client.post('/chat', json={'question':'1990年至2010年GDP增长率是多少？'}).json()
        assert blocked['status'] == 'ok'
        assert blocked['results']['indicator']['status'] == 'insufficient_evidence'
        assert '无法计算增长率' in blocked['answer'] or '须先核验后计算增长率' in blocked['answer']
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

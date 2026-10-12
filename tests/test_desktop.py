import sys

from fastapi.testclient import TestClient
import pytest

import app as api
from desktop_app import runtime as desktop_runtime
from config import Settings
from desktop_app.runtime import read_model_config, write_model_config
from knowledge.knowledge_base import _source_paths


pytestmark = pytest.mark.offline


def test_desktop_config_round_trip_keeps_secret_out_of_api(tmp_path, monkeypatch):
    saved = {}
    monkeypatch.setattr(api, 'desktop_mode', lambda: True)
    monkeypatch.setattr(api, 'profile_dir', lambda: tmp_path)
    monkeypatch.setattr(api, 'read_model_config', lambda: saved.copy())
    monkeypatch.setattr(api, 'write_model_config', lambda data: saved.update(data))
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    monkeypatch.setattr(api, 'apply_model_config', lambda _data: None)
    with TestClient(api.app, base_url='http://127.0.0.1:3820') as client:
        initial = client.get('/desktop/config').json()
        assert initial['configured'] is False
        assert 'api_key' not in initial
        payload = {'api_key': 'secret-value', 'llm_model': 'doubao-seed-character-260628',
                   'embed_model': 'doubao-embedding-vision-251215',
                   'base_url': 'https://ark.cn-beijing.volces.com/api/v3'}
        assert client.post('/desktop/config', json=payload).status_code == 403
        headers = {'X-Desktop-Settings': initial['token'],
                   'Origin': 'http://127.0.0.1:3820'}
        response = client.post('/desktop/config', json=payload, headers=headers)
        assert response.status_code == 200
        assert 'secret-value' not in response.text
        assert saved['ARK_API_KEY'] == 'secret-value'
        assert client.get('/desktop/config').json()['configured'] is True
        payload['api_key'] = ''
        payload['llm_model'] = 'another-model'
        assert client.post('/desktop/config', json=payload, headers=headers).status_code == 200
        assert saved['ARK_API_KEY'] == 'secret-value'
        assert saved['LLM_MODEL'] == 'another-model'
        payload['base_url'] = 'http://unsafe.example/api/v3'
        assert client.post('/desktop/config', json=payload, headers=headers).status_code == 400


def test_desktop_config_rejects_nonlocal_host_and_other_origin(monkeypatch):
    monkeypatch.setattr(api, 'desktop_mode', lambda: True)
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    with TestClient(api.app, base_url='http://127.0.0.1:3820') as client:
        assert client.get('/desktop/config', headers={'Host': 'malicious.example'}).status_code == 403
        assert client.get('/desktop/config', headers={'Origin': 'https://malicious.example'}).status_code == 403


def test_desktop_config_disabled_for_normal_web_server(monkeypatch):
    monkeypatch.setattr(api, 'desktop_mode', lambda: False)
    monkeypatch.setattr(api, 'get_settings', lambda: Settings())
    with TestClient(api.app, base_url='http://127.0.0.1:3820') as client:
        assert client.get('/desktop/config').status_code == 403


def test_encrypted_config_file_round_trip(tmp_path):
    config = {'ARK_API_KEY': 'secret-value', 'LLM_MODEL': 'chat-model',
              'EMBED_MODEL': 'embed-model', 'ARK_BASE_URL': 'https://example.com/api/v3'}
    # Inject a reversible stand-in because Windows DPAPI is unavailable on Linux CI.
    write_model_config(config, tmp_path, encrypt=lambda data: data[::-1])
    raw = (tmp_path / 'model_config.dpapi').read_bytes()
    assert b'secret-value' not in raw
    assert read_model_config(tmp_path, decrypt=lambda data: data[::-1]) == config


def test_config_write_falls_back_to_second_user_directory(tmp_path, monkeypatch):
    roaming, local = tmp_path / 'roaming', tmp_path / 'local'
    monkeypatch.setattr(desktop_runtime, '_config_dirs', lambda _home: [roaming, local])
    monkeypatch.setattr(desktop_runtime.time, 'time_ns', lambda: 1000)
    old_config = {'ARK_API_KEY': 'old-secret', 'LLM_MODEL': 'old-chat',
                  'EMBED_MODEL': '', 'ARK_BASE_URL': 'https://example.com/api/v3'}
    write_model_config(old_config, roaming, encrypt=lambda data: data[::-1])
    real_replace = desktop_runtime.os.replace

    def replace(source, destination):
        if destination.parent == roaming:
            raise PermissionError('roaming storage blocked')
        return real_replace(source, destination)

    monkeypatch.setattr(desktop_runtime.os, 'replace', replace)
    config = {'ARK_API_KEY': 'secret-value', 'LLM_MODEL': 'chat-model',
              'EMBED_MODEL': '', 'ARK_BASE_URL': 'https://example.com/api/v3'}
    stored = write_model_config(config, roaming, encrypt=lambda data: data[::-1])
    assert stored == local / 'model_config.dpapi'
    assert read_model_config(roaming, decrypt=lambda data: data[::-1]) == config


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI only')
def test_windows_dpapi_round_trip(tmp_path):
    config = {'ARK_API_KEY': 'secret-value', 'LLM_MODEL': 'chat-model',
              'EMBED_MODEL': '', 'ARK_BASE_URL': 'https://example.com/api/v3'}
    write_model_config(config, tmp_path)
    assert b'secret-value' not in (tmp_path / 'model_config.dpapi').read_bytes()
    assert read_model_config(tmp_path) == config


def test_desktop_import_dir_accepts_supported_text_documents(tmp_path, monkeypatch):
    (tmp_path / 'notes.txt').write_text('3820 发展资料', encoding='utf-8')
    (tmp_path / 'legacy.doc').write_bytes(b'not OOXML')
    monkeypatch.setenv('AGENT3820_EXTRA_DATA_DIR', str(tmp_path))
    paths = _source_paths(Settings())
    assert (tmp_path / 'notes.txt').resolve() in paths
    assert (tmp_path / 'legacy.doc').resolve() not in paths

import gzip
import json
import struct

import pytest
from fastapi.testclient import TestClient

import app as api
from config import Settings
from voice_cloud import asr_init_packet, asr_packet, parse_asr_response, spoken_text


@pytest.mark.offline
def test_asr_wire_format_and_result_parsing():
    request = asr_init_packet()
    assert request[:4] == bytes([0x11, 0x11, 0x11, 0])
    length = struct.unpack('>I', request[8:12])[0]
    payload = json.loads(gzip.decompress(request[12:12 + length]))
    assert payload['audio']['format'] == 'pcm'
    assert payload['audio']['rate'] == 16000
    encoded = gzip.compress(json.dumps({'result': {'text': '三个阶段是什么？'}}).encode())
    final = bytes([0x11, 0x92, 0x11, 0]) + struct.pack('>I', len(encoded)) + encoded
    data, last = parse_asr_response(final)
    assert data['result']['text'] == '三个阶段是什么？'
    assert last


@pytest.mark.offline
def test_tts_endpoint_keeps_secret_on_server_and_limits_text(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings(voice_api_key='private-test-key'))
    observed = []
    monkeypatch.setattr(api, 'synthesize_mp3', lambda text, settings:
                        observed.append((text, settings.require_voice_api_key())) or b'ID3test')
    with TestClient(api.app) as client:
        response = client.post('/voice/tts', json={'text': ' **三个阶段** 是什么？ '})
        assert response.status_code == 200
        assert response.content == b'ID3test'
        assert response.headers['content-type'] == 'audio/mpeg'
        assert client.post('/voice/tts', json={'text': 'x' * 3001}).status_code == 422
    assert observed == [(' **三个阶段** 是什么？ ', 'private-test-key')]
    assert spoken_text('[出处](https://example.com) **三个阶段**') == '出处 三个阶段'


@pytest.mark.offline
def test_asr_websocket_requires_site_password(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: Settings(
        voice_api_key='voice-secret', service_api_key='site-password'))
    with TestClient(api.app) as client:
        with client.websocket_connect('/voice/asr') as ws:
            ws.send_json({'type': 'auth', 'service_key': 'wrong', 'client_id': ''})
            assert ws.receive_json()['type'] == 'error'

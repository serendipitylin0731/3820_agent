import os
import subprocess
import sys

import pytest

from config import ConfigurationError, Settings, load_settings


def test_environment_overrides_dotenv_and_hides_secret(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ARK_API_KEY=填写实际密钥\nTOP_K=3\n", encoding="utf-8")
    settings = load_settings(
        environ={"ARK_API_KEY": "offline-secret", "TOP_K": "7"},
        dotenv_path=env_file,
    )
    assert settings.require_api_key() == "offline-secret"
    assert settings.top_k == 7
    assert "offline-secret" not in repr(settings)


def test_missing_and_invalid_configuration_has_safe_error(tmp_path):
    settings = load_settings(environ={}, dotenv_path=tmp_path / "absent")
    with pytest.raises(ConfigurationError, match="ARK_API_KEY"):
        settings.require_service_ready()
    with pytest.raises(ConfigurationError) as exc:
        load_settings(
            environ={"TOP_K": "invalid", "ARK_API_KEY": "private-test-value"},
            dotenv_path=tmp_path / "absent",
        )
    assert "TOP_K" in str(exc.value)
    assert "private-test-value" not in str(exc.value)

    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        Settings(ark_api_key="test-only-key").require_service_ready()
    with pytest.raises(ConfigurationError, match="EMBED_MODEL"):
        Settings(ark_api_key="test-only-key", llm_model="fake-chat").require_service_ready()


def test_voice_service_settings_are_separate_and_private(tmp_path):
    path = tmp_path / '.env'
    path.write_text('VOICE_API_KEY=填写语音服务API_Key\n', encoding='utf-8')
    missing = load_settings(environ={}, dotenv_path=path)
    with pytest.raises(ConfigurationError, match='VOICE_API_KEY'):
        missing.require_voice_api_key()

    settings = load_settings(environ={'VOICE_API_KEY': 'private-voice-key'}, dotenv_path=path)
    assert settings.require_voice_api_key() == 'private-voice-key'
    assert settings.voice_asr_resource_id == 'volc.seedasr.sauc.duration'
    assert settings.voice_tts_resource_id == 'seed-tts-2.0'
    assert 'private-voice-key' not in repr(settings)

    with pytest.raises(ConfigurationError, match='VOICE_ASR_WS_URL'):
        load_settings(environ={'VOICE_ASR_WS_URL': 'http://example.com'}, dotenv_path=path)
    with pytest.raises(ConfigurationError, match='VOICE_TTS_URL'):
        load_settings(environ={'VOICE_TTS_URL': 'http://example.com'}, dotenv_path=path)


def test_imports_work_without_key_or_source():
    env = os.environ.copy()
    for name in ("ARK_API_KEY", "LLM_MODEL", "EMBED_MODEL"):
        env.pop(name, None)
    code = """
import socket
def deny_network(*_args, **_kwargs):
    raise AssertionError('导入时不得联网')
socket.socket.connect = deny_network
import config, llm_client, knowledge.knowledge_base, agents.agent_main, graph, app
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_fake_client_uses_central_model_and_timeout(fake_chat_client):
    from llm_client import chat

    settings = Settings(llm_model="offline-model", request_timeout=12)
    content = chat([{"role": "user", "content": "GDP?"}], settings=settings, client=fake_chat_client)
    assert content.startswith("[")
    assert fake_chat_client.calls[0]["model"] == "offline-model"
    assert fake_chat_client.calls[0]["timeout"] == 12

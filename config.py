"""集中读取运行配置；导入本模块不会读取密钥或连接外部服务。"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator


class ConfigurationError(RuntimeError):
    """配置缺失或无效；错误消息只包含配置项名称，不包含密钥值。"""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    ark_api_key: SecretStr | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_model: str | None = None
    embed_model: str | None = None
    voice_api_key: SecretStr | None = None
    voice_asr_ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    voice_asr_resource_id: str = "volc.seedasr.sauc.duration"
    voice_tts_url: str = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    voice_tts_resource_id: str = "seed-tts-2.0"
    voice_tts_speaker: str = "zh_female_vv_uranus_bigtts"
    top_k: int = Field(default=5, ge=1, le=100)
    request_timeout: float = Field(default=30.0, gt=0, le=300)
    checkpoint_path: Path = Path("var/checkpoints.sqlite3")
    index_path: Path = Path("var/knowledge_index")
    vector_max_distance: float | None = Field(default=None, ge=0)
    log_level: str = "INFO"
    service_api_key: SecretStr | None = None
    service_clients_json: SecretStr | None = None
    max_body_bytes: int = Field(default=16384, ge=1024, le=1048576)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)

    @field_validator("ark_api_key", "voice_api_key", "llm_model", "embed_model", "service_api_key", "service_clients_json", mode="before")
    @classmethod
    def empty_or_placeholder_is_missing(cls, value):
        if value is None or not str(value).strip():
            return None
        if any(marker in str(value) for marker in ("填写", "您的API_KEY")):
            return None
        return str(value).strip()

    @field_validator("ark_base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username:
            raise ValueError("必须是无用户名的 HTTP(S) 地址")
        return value.rstrip("/")

    @field_validator("voice_asr_ws_url")
    @classmethod
    def valid_voice_asr_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme != "wss" or not parts.netloc or parts.username or parts.password:
            raise ValueError("必须是无用户名的 WSS 地址")
        return value

    @field_validator("voice_tts_url")
    @classmethod
    def valid_voice_tts_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
            raise ValueError("必须是无用户名的 HTTPS 地址")
        return value

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("日志级别无效")
        return level

    def require_api_key(self) -> str:
        if self.ark_api_key is None:
            raise ConfigurationError("缺少 ARK_API_KEY；请在本地 .env 或环境变量中配置")
        return self.ark_api_key.get_secret_value()

    def require_chat_model(self) -> str:
        if not self.llm_model:
            raise ConfigurationError("缺少 LLM_MODEL；请填写实际开通的模型 ID")
        return self.llm_model

    def require_embed_model(self) -> str:
        if not self.embed_model:
            raise ConfigurationError("缺少 EMBED_MODEL；请填写实际开通的向量模型 ID")
        return self.embed_model

    def require_voice_api_key(self) -> str:
        if self.voice_api_key is None:
            raise ConfigurationError("缺少 VOICE_API_KEY；请填写豆包语音服务 API Key")
        return self.voice_api_key.get_secret_value()

    def require_service_ready(self) -> None:
        self.require_api_key()
        self.require_chat_model()
        self.require_embed_model()


_ENV_FIELDS = {
    "ARK_API_KEY": "ark_api_key",
    "ARK_BASE_URL": "ark_base_url",
    "LLM_MODEL": "llm_model",
    "EMBED_MODEL": "embed_model",
    "VOICE_API_KEY": "voice_api_key",
    "VOICE_ASR_WS_URL": "voice_asr_ws_url",
    "VOICE_ASR_RESOURCE_ID": "voice_asr_resource_id",
    "VOICE_TTS_URL": "voice_tts_url",
    "VOICE_TTS_RESOURCE_ID": "voice_tts_resource_id",
    "VOICE_TTS_SPEAKER": "voice_tts_speaker",
    "TOP_K": "top_k",
    "REQUEST_TIMEOUT": "request_timeout",
    "CHECKPOINT_PATH": "checkpoint_path",
    "INDEX_PATH": "index_path",
    "VECTOR_MAX_DISTANCE": "vector_max_distance",
    "LOG_LEVEL": "log_level",
    "SERVICE_API_KEY": "service_api_key",
    "SERVICE_CLIENTS_JSON": "service_clients_json",
    "MAX_BODY_BYTES": "max_body_bytes",
    "RATE_LIMIT_PER_MINUTE": "rate_limit_per_minute",
}


def load_settings(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """读取项目 .env，再用环境变量覆盖；只选择已声明的配置项。"""
    path = dotenv_path if dotenv_path is not None else Path(__file__).with_name(".env")
    values = dict(dotenv_values(path)) if path.is_file() else {}
    values.update(os.environ if environ is None else environ)
    selected = {
        field: values[name]
        for name, field in _ENV_FIELDS.items()
        if values.get(name) is not None
    }
    try:
        return Settings.model_validate(selected)
    except ValidationError as exc:
        fields = ", ".join(sorted({str(error["loc"][0]).upper() for error in exc.errors()}))
        raise ConfigurationError(f"配置项无效：{fields}") from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

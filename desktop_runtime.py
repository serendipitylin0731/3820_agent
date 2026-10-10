"""Windows desktop profile and user supplied model credentials.

The installed program is read-only. Runtime state lives under the current user's
AppData directory; the model API key is encrypted with Windows DPAPI.
"""

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path


APP_NAME = "3820Agent"
DESKTOP_FLAG = "AGENT3820_DESKTOP_MODE"


def desktop_mode() -> bool:
    return os.environ.get(DESKTOP_FLAG) == "1"


def profile_dir() -> Path:
    override = os.environ.get("AGENT3820_DESKTOP_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform != "win32":
        raise RuntimeError("桌面安装版仅支持 Windows")
    root = os.environ.get("APPDATA")
    if not root:
        raise RuntimeError("找不到 Windows AppData 目录")
    return Path(root) / APP_NAME


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("密钥加密仅在 Windows 上可用")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = _blob(data)
    output = _DataBlob()
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                        0, ctypes.byref(output))
    else:
        # CRYPTPROTECT_UI_FORBIDDEN: no Windows confirmation dialog.
        ok = crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None,
                                      0x1, ctypes.byref(output))
    if not ok:
        raise OSError("无法读取或保存当前 Windows 用户的模型配置")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def read_model_config(home: Path | None = None, *, decrypt=None) -> dict:
    path = (home or profile_dir()) / "model_config.dpapi"
    if not path.is_file():
        return {}
    raw = (decrypt or (lambda value: _dpapi(value, decrypt=True)))(path.read_bytes())
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict) or parsed.get("version") != 1:
        raise ValueError("模型配置格式无效")
    return {key: str(parsed.get(key, "")) for key in
            ("ARK_API_KEY", "LLM_MODEL", "EMBED_MODEL", "ARK_BASE_URL")}


def write_model_config(config: dict, home: Path | None = None, *, encrypt=None) -> None:
    directory = home or profile_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, **{key: str(config.get(key, "")) for key in
                               ("ARK_API_KEY", "LLM_MODEL", "EMBED_MODEL", "ARK_BASE_URL")}}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    encrypted = (encrypt or (lambda value: _dpapi(value, decrypt=False)))(raw)
    temp = directory / "model_config.dpapi.tmp"
    temp.write_bytes(encrypted)
    os.replace(temp, directory / "model_config.dpapi")


def apply_model_config(config: dict) -> None:
    for name in ("ARK_API_KEY", "LLM_MODEL", "EMBED_MODEL", "ARK_BASE_URL"):
        value = config.get(name, "")
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    from config import get_settings
    get_settings.cache_clear()


def prepare_desktop() -> Path:
    home = profile_dir()
    home.mkdir(parents=True, exist_ok=True)
    sources = home / "knowledge" / "data"
    sources.mkdir(parents=True, exist_ok=True)
    os.environ[DESKTOP_FLAG] = "1"
    os.environ["AGENT3820_EXTRA_DATA_DIR"] = str(sources)
    os.environ["CHECKPOINT_PATH"] = str(home / "checkpoints.sqlite3")
    os.environ["INDEX_PATH"] = str(home / "knowledge_index")
    # The desktop edition calls the agent directly; no HTTP service is started.
    os.environ.pop("SERVICE_API_KEY", None)
    os.environ.pop("SERVICE_CLIENTS_JSON", None)
    try:
        apply_model_config(read_model_config(home))
    except (OSError, ValueError, UnicodeError):
        # A corrupted profile must not prevent users from opening settings.
        apply_model_config({})
    return home

"""豆包语音服务协议；密钥只在服务端使用。"""

import base64
import gzip
import json
import re
import struct
import uuid

import requests

from config import Settings


class VoiceServiceError(RuntimeError):
    pass


def asr_headers(settings: Settings) -> dict[str, str]:
    request_id = str(uuid.uuid4())
    return {
        'X-Api-Key': settings.require_voice_api_key(),
        'X-Api-Resource-Id': settings.voice_asr_resource_id,
        'X-Api-Request-Id': request_id,
        'X-Api-Connect-Id': request_id,
        'X-Api-Sequence': '-1',
    }


def asr_packet(message_type: int, flag: int, sequence: int, data: bytes,
               *, serialization: int = 1) -> bytes:
    compressed = gzip.compress(data)
    header = bytes([0x11, (message_type << 4) | flag, (serialization << 4) | 1, 0])
    return header + struct.pack('>iI', sequence, len(compressed)) + compressed


def asr_init_packet() -> bytes:
    payload = {
        'user': {'uid': '3820_voice'},
        'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
        'request': {'model_name': 'bigmodel', 'enable_itn': True, 'enable_punc': True,
                    'enable_ddc': True, 'show_utterances': True, 'enable_nonstream': False},
    }
    return asr_packet(1, 1, 1, json.dumps(payload).encode('utf-8'))


def parse_asr_response(frame: bytes) -> tuple[dict, bool]:
    if len(frame) < 8 or frame[0] >> 4 != 1:
        raise VoiceServiceError('语音识别返回了无效数据')
    message_type = frame[1] >> 4
    flags = frame[1] & 15
    offset = (frame[0] & 15) * 4
    if flags & 1:
        offset += 4
    if flags & 4:
        offset += 4
    if message_type == 15:
        offset += 4
    if len(frame) < offset + 4:
        raise VoiceServiceError('语音识别返回了不完整的数据')
    size = struct.unpack('>I', frame[offset:offset + 4])[0]
    if size > 2_000_000 or len(frame) < offset + 4 + size:
        raise VoiceServiceError('语音识别返回的数据长度异常')
    payload = frame[offset + 4:offset + 4 + size]
    if frame[2] & 15 == 1 and payload:
        payload = gzip.decompress(payload)
    data = json.loads(payload) if payload else {}
    if message_type == 15 or data.get('error'):
        raise VoiceServiceError('豆包语音识别失败，请稍后重试')
    return data, bool(flags & 2)


def spoken_text(value: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', value)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[*#`>]', '', text)
    return re.sub(r'\s+', ' ', text).strip()[:3000]


def synthesize_mp3(value: str, settings: Settings) -> bytes:
    text = spoken_text(value)
    if not text:
        raise VoiceServiceError('回答中没有可播报的文字')
    headers = {
        'X-Api-Key': settings.require_voice_api_key(),
        'X-Api-Resource-Id': settings.voice_tts_resource_id,
        'X-Api-Request-Id': str(uuid.uuid4()),
        'Content-Type': 'application/json',
    }
    body = {'req_params': {'text': text, 'speaker': settings.voice_tts_speaker,
                           'audio_params': {'format': 'mp3', 'sample_rate': 24000}}}
    audio = bytearray()
    try:
        with requests.post(settings.voice_tts_url, headers=headers, json=body,
                           stream=True, timeout=settings.request_timeout) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                item = json.loads(line)
                code = item.get('code', 0)
                if code not in (0, 20000000):
                    raise VoiceServiceError('豆包语音合成失败，请检查音色和服务额度')
                if item.get('data'):
                    audio.extend(base64.b64decode(item['data'], validate=True))
                    if len(audio) > 8 * 1024 * 1024:
                        raise VoiceServiceError('语音回答过长，已停止合成')
                if code == 20000000:
                    break
    except VoiceServiceError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise VoiceServiceError('语音合成服务暂时不可用') from exc
    if not audio:
        raise VoiceServiceError('语音合成没有返回音频')
    return bytes(audio)

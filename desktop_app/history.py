"""Persistent native desktop conversations, limited to the most recent 30 turns."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


LIMIT = 30
LEGACY_PREFIX = '知识库资料中暂未查找到，以下是豆包模型提供的参考回答：'
MODEL_NOTE = '知识库没有找到直接匹配的资料；此回答由豆包模型补充，未附资料来源。'


def _normalise(turn):
    if not isinstance(turn, dict):
        return None
    thread_id, question, answer = (turn.get('thread_id'), turn.get('question'), turn.get('answer'))
    if not all(isinstance(item, str) and item for item in (thread_id, question, answer)):
        return None
    sources = turn.get('sources')
    legacy = answer.startswith(LEGACY_PREFIX)
    return {'thread_id': thread_id, 'question': question[:4000],
            'answer': answer[len(LEGACY_PREFIX):] if legacy else answer,
            'created_at': str(turn.get('created_at') or datetime.now(timezone.utc).isoformat()),
            'note': MODEL_NOTE if legacy else str(turn.get('note') or '')[:300],
            'sources': [item for item in sources[:60] if isinstance(item, dict)]
            if isinstance(sources, list) else []}


def load_history(home: Path):
    try:
        data = json.loads((home / 'history.json').read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('turns'), list):
            return []
        return [item for item in (_normalise(turn) for turn in data['turns']) if item][-LIMIT:]
    except (OSError, ValueError, TypeError):
        return []


def save_history(home: Path, turns: list):
    home.mkdir(parents=True, exist_ok=True)
    cleaned = [item for item in (_normalise(turn) for turn in turns) if item][-LIMIT:]
    temp = home / 'history.json.tmp'
    temp.write_text(json.dumps({'version': 1, 'turns': cleaned}, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, home / 'history.json')
    return cleaned


def conversations(turns: list):
    grouped = {}
    for turn in turns:
        thread_id = turn['thread_id']
        if thread_id not in grouped:
            grouped[thread_id] = {'thread_id': thread_id, 'title': turn['question'], 'count': 0}
        else:
            grouped[thread_id] = grouped.pop(thread_id)
        grouped[thread_id]['count'] += 1
        grouped[thread_id]['updated_at'] = turn['created_at']
    return list(reversed(list(grouped.values())))

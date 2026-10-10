"""Persistent native desktop conversations, limited to the most recent 30 turns."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


LIMIT = 30


def _normalise(turn):
    if not isinstance(turn, dict):
        return None
    thread_id, question, answer = (turn.get('thread_id'), turn.get('question'), turn.get('answer'))
    if not all(isinstance(item, str) and item for item in (thread_id, question, answer)):
        return None
    sources = turn.get('sources')
    return {'thread_id': thread_id, 'question': question[:4000], 'answer': answer,
            'created_at': str(turn.get('created_at') or datetime.now(timezone.utc).isoformat()),
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

import json

import pytest

from desktop_gui import collect_sources
from desktop_history import LIMIT, conversations, load_history, save_history


pytestmark = pytest.mark.offline


def test_history_persists_recent_turns_and_groups_by_latest_activity(tmp_path):
    turns = [
        {'thread_id': 'first' if index % 2 == 0 else 'second',
         'question': f'问题 {index}', 'answer': f'回答 {index}',
         'sources': [{'source_file': 'guide.md', 'section': '目标'}]}
        for index in range(LIMIT + 5)
    ]
    saved = save_history(tmp_path, turns)
    assert len(saved) == LIMIT
    assert load_history(tmp_path) == saved
    assert conversations(saved)[0]['thread_id'] == 'first'
    assert conversations(saved)[0]['count'] == LIMIT // 2
    assert json.loads((tmp_path / 'history.json').read_text(encoding='utf-8'))['version'] == 1


def test_corrupt_history_does_not_prevent_startup(tmp_path):
    (tmp_path / 'history.json').write_text('{broken', encoding='utf-8')
    assert load_history(tmp_path) == []


def test_sources_are_deduplicated_across_agent_results():
    source = {'source_file': 'docs/guide.md', 'section': '目标', 'page_or_slide': 'L10'}
    result = {'kb_sources': [source], 'results': {'planning': {'sources': [source]}}}
    assert collect_sources(result) == [
        {**source, 'data_version': None}
    ]

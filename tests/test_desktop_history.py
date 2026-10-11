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


def test_model_note_is_restored_with_desktop_history(tmp_path):
    note = '此回答由豆包模型补充，未附资料来源。'
    saved = save_history(tmp_path, [{'thread_id': 'one', 'question': '问题',
                                     'answer': '回答', 'sources': [], 'note': note}])
    assert saved[0]['note'] == note
    assert load_history(tmp_path)[0]['note'] == note


def test_legacy_model_preface_moves_to_small_note(tmp_path):
    from desktop_history import LEGACY_PREFIX
    saved = save_history(tmp_path, [{'thread_id': 'old', 'question': '问题',
                                     'answer': LEGACY_PREFIX + '开发区推动开放。', 'sources': []}])
    assert saved[0]['answer'] == '开发区推动开放。'
    assert '豆包模型补充' in saved[0]['note']


def test_corrupt_history_does_not_prevent_startup(tmp_path):
    (tmp_path / 'history.json').write_text('{broken', encoding='utf-8')
    assert load_history(tmp_path) == []


def test_sources_are_deduplicated_across_agent_results():
    source = {'source_file': 'docs/guide.md', 'section': '目标', 'page_or_slide': 'L10'}
    result = {'kb_sources': [source], 'results': {'planning': {'sources': [source]}}}
    assert collect_sources(result) == [
        {**source, 'data_version': None}
    ]


def test_model_supplement_does_not_show_unrelated_retrieval_sources():
    result = {'kb_sources': [{'source_file': 'unrelated.md'}],
              'results': {'model': {'data': {'kind': 'model_knowledge'}, 'sources': []}}}
    assert collect_sources(result) == []


def test_unanswered_planning_result_does_not_claim_retrieval_hit_as_source():
    result = {'kb_sources': [{'source_file': 'nearby-but-not-used.md'}],
              'results': {'planning': {'status': 'insufficient_evidence', 'sources': []}}}
    assert collect_sources(result) == []

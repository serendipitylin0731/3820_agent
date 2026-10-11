"""最终回答只重述有来源的事实，理论视角按问题选用。"""

import json

from config import Settings
from agents import answer_writer
from knowledge.theory_context import select_theory


SOURCE = {'source_file': 'docs/指南.md', 'page_or_slide': 12,
          'section': '阶段目标', 'data_version': '本地测试', 'verified': False}
RESULTS = {'planning': {'role': 'planning', 'status': 'ok',
                        'data': {'stage_goals': '1995、2000、2010 三阶段'},
                        'sources': [SOURCE]}}
ONLINE_SETTINGS = Settings(ark_api_key='test-only-key', llm_model='fake-model')


def test_theory_is_selective_and_historically_labeled():
    assert select_theory('1995年GDP是多少？', RESULTS) == {}
    assert select_theory('3820体现了哪些马克思主义方法论？', RESULTS)
    assert select_theory('3820有哪些当代启示？', {'planning': {'status': 'insufficient_evidence',
                                                    'sources': []}}) == {}


def test_model_rewrites_grounded_result_as_natural_answer(monkeypatch):
    seen = []
    def fake_chat(messages, **_kwargs):
        seen.append(json.loads(messages[1]['content']))
        return json.dumps({'answer': '这项规划分三阶段推进：1995 年打基础，2000 年追赶，2010 年完成远景目标。',
                           'used_theory_ids': []}, ensure_ascii=False)
    monkeypatch.setattr(answer_writer, 'chat', fake_chat)
    answer, theory = answer_writer.compose_answer('3820的三个阶段是什么？', RESULTS, 'fallback',
                                                  settings=ONLINE_SETTINGS)
    assert answer.startswith('这项规划')
    assert theory is None
    assert seen[0]['theory_candidates'] == {}


def test_theory_source_only_attached_when_used_and_labeled(monkeypatch):
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: json.dumps({
        'answer': '从今天的理论视角看，系统观念有助于理解“3820”工程的长期规划。',
        'used_theory_ids': ['new_era_method']}, ensure_ascii=False))
    answer, theory = answer_writer.compose_answer('3820有哪些当代启示？', RESULTS, 'fallback',
                                                  settings=ONLINE_SETTINGS)
    assert '今天的理论视角' in answer
    assert theory['new_era_method']['source']['verified'] is True


def test_plain_model_answer_with_theory_ids_is_accepted(monkeypatch):
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: (
        '从今天的理论视角看，系统观念有助于理解这项长期规划。\n'
        'used_theory_ids: ["new_era_method"]'))
    answer, theory = answer_writer.compose_answer('3820有哪些当代启示？', RESULTS, 'fallback',
                                                  settings=ONLINE_SETTINGS)
    assert answer.startswith('从今天')
    assert list(theory) == ['new_era_method']


def test_unsubstantiated_quantity_falls_back_to_sourced_theory(monkeypatch):
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: (
        '从今天的理论视角看，规划设置了十二个战略重点。\n'
        'used_theory_ids: ["new_era_method"]'))
    answer, theory = answer_writer.compose_answer('3820有哪些当代启示？', RESULTS,
                                                  '规划分阶段推进。', settings=ONLINE_SETTINGS)
    assert '十二个' not in answer
    assert '从今天的理论视角看' in answer
    assert list(theory) == ['new_era_method']


def test_theory_fallback_does_not_repeat_truncated_ocr():
    results = {'planning': {'role': 'planning', 'status': 'ok', 'sources': [SOURCE],
                            'data': {'background': '1992年经过广泛调研。',
                                     'stage_goals': '用3年时间即到1995年使经济上一',
                                     'implementation_paths': '资料未提及'}}}
    fallback = answer_writer.natural_fallback('3820的规划方法有何启示？', results)
    assert '使经济上一' not in fallback
    answer, sources = answer_writer.compose_answer('3820的规划方法有何启示？', results,
                                                   fallback, settings=Settings())
    assert '使经济上一' not in answer
    assert '1992年经过广泛调研' in answer
    assert sources


def test_model_cannot_claim_no_evidence_when_planning_has_sources(monkeypatch):
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: (
        '现有知识库对此问题依据不足。从今天的理论视角看，实事求是有启示。\n'
        'used_theory_ids: ["marxist_method"]'))
    answer, sources = answer_writer.compose_answer('3820与马克思主义有什么关系？', RESULTS,
                                                   '已有规划资料。', settings=ONLINE_SETTINGS)
    assert '依据不足' not in answer
    assert sources


def test_missing_critical_number_or_unapproved_theory_falls_back(monkeypatch):
    results = {'indicator': {'role': 'indicator', 'status': 'ok',
                             'data': {'values': {'2010': 3123.41},
                                      'conflicts': [{'other': {'value': 3242.65}}]},
                             'sources': [SOURCE]}}
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: json.dumps({
        'answer': '2010 年 GDP 为 3123.41 亿元。', 'used_theory_ids': []}, ensure_ascii=False))
    assert answer_writer.compose_answer('2010年GDP是多少？', results, 'fallback',
                                        settings=ONLINE_SETTINGS) == ('fallback', None)
    monkeypatch.setattr(answer_writer, 'chat', lambda *_args, **_kwargs: json.dumps({
        'answer': '1995、2000、2010 年分三阶段。', 'used_theory_ids': ['made_up']}, ensure_ascii=False))
    assert answer_writer.compose_answer('3820的三个阶段是什么？', RESULTS, 'fallback',
                                        settings=ONLINE_SETTINGS) == ('fallback', None)

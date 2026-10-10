from config import Settings
from knowledge import model_fallback as fallback


def test_model_scope_and_evidence_boundary():
    missing = {'planning': {'role': 'planning', 'status': 'insufficient_evidence', 'sources': []}}
    assert fallback.needs_model('3820工程与福州机场有什么关系？', missing, '依据不足')
    assert fallback.needs_model('福州机场二期扩建何时完成？', missing, '依据不足')
    assert not fallback.needs_model('量子芯片制程是多少？', missing, '依据不足')
    assert not fallback.needs_model('福州明天天气如何？', missing, '依据不足')
    disputed = {'indicator': {'role': 'indicator', 'status': 'insufficient_evidence'}}
    assert not fallback.needs_model('福州2010年GDP增长率是多少？', disputed, '依据不足')


def test_model_answer_is_labeled_and_has_no_fake_sources(monkeypatch):
    monkeypatch.setattr(fallback, 'chat', lambda *args, **kwargs: '福州机场建设改善了对外交通条件。')
    answer, result = fallback.answer_from_model('3820工程与福州机场有什么关系？',
                                                 settings=Settings(ark_api_key='test', llm_model='test'))
    assert answer.startswith(fallback.PREFIX)
    assert result['role'] == 'model'
    assert result['sources'] == []


def test_model_unavailable_keeps_insufficient_evidence(monkeypatch):
    monkeypatch.setattr(fallback, 'chat', lambda *args, **kwargs: '抱歉，无法回答该问题。')
    assert fallback.answer_from_model('3820工程的问题',
                                       settings=Settings(ark_api_key='test', llm_model='test')) is None

from types import SimpleNamespace
import pytest
from resilience import call_llm_safe, transient_error


def test_retry_only_transient(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise TimeoutError('temporary')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert call_llm_safe(client, 'fake', [], 1) == 'ok'
    assert len(calls) == 3
    assert not transient_error(ValueError('bad input'))

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


def test_agent_timeout_has_structured_result_and_trace(monkeypatch, caplog):
    import graph
    monkeypatch.setattr(graph, 'query_indicator',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError('private-value')))
    with caplog.at_level('WARNING', logger='3820_agent'):
        result = graph.execute_node({'sub_tasks':[{'type':'indicator','question':'GDP','key':'gdp','years':[1995]}],
                                     'request_id':'trace-1','thread_id':'session-1'})
    assert result['results']['indicator']['error']['code'] == 'agent_timeout'
    assert 'trace-1' in caplog.text and 'duration_ms' in caplog.text
    assert 'private-value' not in caplog.text

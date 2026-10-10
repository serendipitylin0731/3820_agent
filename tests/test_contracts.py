import pytest
from pydantic import ValidationError

from contracts import (
    AgentResult, ChatRequest, ChatResponse, KnowledgeHit, KnowledgeResult,
    SourceRef, SubTask,
)


def test_example_fixture_validates_all_shared_contracts(contract_examples, fake_retriever):
    source = SourceRef.model_validate(contract_examples["source"])
    assert source.verified is False
    assert isinstance(fake_retriever("GDP").hits[0], KnowledgeHit)
    assert SubTask.model_validate(contract_examples["subtask"]).key == "gdp"
    response = ChatResponse.model_validate(contract_examples["chat_response"])
    assert response.results["indicator_1"].sources[0] == source


@pytest.mark.parametrize("payload", [
    {"type": "indicator", "question": "GDP?"},
    {"type": "spatial", "question": "园区?"},
    {"type": "planning", "question": "   "},
    {"type": "unknown", "question": "问题"},
])
def test_invalid_subtasks_are_rejected(payload):
    with pytest.raises(ValidationError):
        SubTask.model_validate(payload)


def test_result_states_and_sources_are_checked(contract_examples):
    with pytest.raises(ValidationError):
        KnowledgeResult(status="ok", hits=[])
    with pytest.raises(ValidationError):
        AgentResult(role="indicator", status="error")
    with pytest.raises(ValidationError):
        KnowledgeHit(
            chunk_id="x", content="text", source=contract_examples["source"], score=0.1,
        )


def test_blank_chat_request_is_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(question="   ")


def test_graph_rejects_bad_subtask_before_retrieval(monkeypatch):
    import graph

    monkeypatch.setattr(graph, "split_task", lambda _question: [{"type": "indicator", "question": "GDP?"}])
    monkeypatch.setattr(
        graph, "search", lambda _question, **_kwargs: pytest.fail("非法子任务不应检索"),
    )
    with pytest.raises(ValidationError):
        graph.parse_node({"question": "GDP?"})


def test_graph_routes_with_fake_model_and_retrieval(monkeypatch, fake_retriever):
    import graph

    monkeypatch.setattr(
        graph, "split_task",
        lambda _question: [{"type": "planning", "question": "指南中的 GDP 示例是什么？"}],
    )
    monkeypatch.setattr(
        graph, "search",
        lambda query, **_kwargs: fake_retriever(query),
    )
    monkeypatch.setattr(
        graph, "run_planning",
        lambda _question, context: f"依据片段：{context}",
    )
    result = graph.ask("指南中的 GDP 示例是什么？", "offline-planning")
    assert "3123.41" in result["results"]["planning"]["data"]
    assert result["results"]["planning"]["sources"]
    assert "planning" in result["answer"]

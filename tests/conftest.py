import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts import KnowledgeResult


@pytest.fixture(autouse=True)
def offline_by_default(monkeypatch, request):
    if request.node.get_closest_marker("online"):
        return

    original_connect = socket.socket.connect

    def deny_network(sock, address):
        # Windows asyncio creates its wake-up socket with a localhost socketpair.
        if isinstance(address, tuple) and address[0] in {'127.0.0.1', '::1'}:
            return original_connect(sock, address)
        raise AssertionError("离线测试不得建立网络连接")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)


def pytest_collection_modifyitems(items):
    for item in items:
        if not item.get_closest_marker("online"):
            item.add_marker(pytest.mark.offline)


@pytest.fixture
def contract_examples():
    path = Path(__file__).parent / "fixtures" / "contracts.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def fake_chat_client():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content='[{"type":"indicator","question":"GDP?","key":"gdp"}]')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.calls = calls
    return client


@pytest.fixture
def fake_retriever(contract_examples):
    result = KnowledgeResult.model_validate(contract_examples["knowledge_result"])
    return lambda _query: result

"""Exercises POST /query (app/ramq_chatbot/router.py's wiring of RAMQManualQueryEngine) end
to end, with the engine itself stubbed out — get_ramq_query_engine builds a real
BM25+vector retriever over the `manuel-omnipraticiens` LanceDB table (see
app/ramq_chatbot/factory.py), which this test suite must not depend on."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.ramq_chatbot.models import RAMQChatMessage


class _StubQueryEngine:
    def __init__(self, answer: str):
        self._answer = answer
        self.calls: list[tuple[str, list[RAMQChatMessage] | None]] = []

    async def acustom_query(self, query_str: str, chat_history: list[RAMQChatMessage] | None = None) -> str:
        self.calls.append((query_str, chat_history))
        return self._answer


def test_query_endpoint_returns_engine_answer():
    stub = _StubQueryEngine("La majoration de nuit est de 27,25$ selon le manuel RAMQ.")
    with patch("app.ramq_chatbot.router.get_ramq_query_engine", return_value=stub):
        with TestClient(app) as client:
            response = client.post("/query", json={"query": "Quelle est la majoration de nuit?"})

    assert response.status_code == 200
    assert response.json() == {"answer": "La majoration de nuit est de 27,25$ selon le manuel RAMQ."}
    assert stub.calls == [("Quelle est la majoration de nuit?", [])]


def test_query_endpoint_forwards_chat_history():
    stub = _StubQueryEngine("Pour un enfant, la majoration est différente.")
    history_payload = [
        {"role": "user", "content": "Quelle est la majoration de nuit?"},
        {"role": "assistant", "content": "27,25$ selon le manuel RAMQ."},
    ]
    with patch("app.ramq_chatbot.router.get_ramq_query_engine", return_value=stub):
        with TestClient(app) as client:
            response = client.post(
                "/query",
                json={"query": "Et pour un enfant?", "history": history_payload},
            )

    assert response.status_code == 200
    [(query_str, chat_history)] = stub.calls
    assert query_str == "Et pour un enfant?"
    assert chat_history == [
        RAMQChatMessage(role="user", content="Quelle est la majoration de nuit?"),
        RAMQChatMessage(role="assistant", content="27,25$ selon le manuel RAMQ."),
    ]

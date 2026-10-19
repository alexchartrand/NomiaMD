"""Metered LLM calls are stored with what they were for (app/extraction/recorder.py, the
chatbot route), and the admin console reports them (app/admin/usage.py, pricing.py)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import itertools
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin.pricing import ModelPrice, PriceTable
from app.auth import get_current_user
from app.clock import get_clock
from app.llm.usage import LLMCallRecord, default_recorder
from app.main import app
from app.postgresdb import (
    Encounter,
    LLMCall,
    LLMCallOwner,
    LLMCallRepository,
    UserRepository,
    UserRole,
    session_scope,
)
from tests.test_extraction import MOCK_RESULT, MOCK_SUMMARY_RESULT, _extract, _mock_response
from tests.test_extraction import _seed_patient as _seed_extraction_patient

_nams = itertools.count(1)


async def _seed_patient():
    # Its own NAM prefix: test_extraction's counter restarts when this module imports it.
    return await _seed_extraction_patient(ramq_number=f"USGE{next(_nams):08d}")


def _record(model: str, purpose: str, *, input_tokens=100, output_tokens=20, started_at=None) -> LLMCallRecord:
    return LLMCallRecord(
        kind="chat",
        provider="mistral",
        model=model,
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=250.0,
        started_at=started_at or datetime.now(timezone.utc),
        finish_reason="stop",
    )


def _metered(*outcomes):
    """A chat mock that reports each call to the recorder, as the real SDK clients do."""
    remaining = iter(outcomes)

    async def chat(*args, **kwargs):
        outcome = next(remaining)
        default_recorder.record(_record("mistral-small-latest", "test"))
        if isinstance(outcome, Exception):
            raise outcome
        return _mock_response(outcome)

    return chat


async def _calls_for_patient(patient_id: int) -> list[LLMCall]:
    async with session_scope() as session:
        encounter_ids = select(Encounter.id).where(Encounter.patient_id == patient_id)
        return list(await session.scalars(select(LLMCall).where(LLMCall.encounter_id.in_(encounter_ids))))


async def test_an_extraction_stores_its_calls_on_the_run():
    with TestClient(app) as client:
        patient = await _seed_patient()
        response, _ = _extract(client, patient_id=patient.id, side_effect=_metered(MOCK_SUMMARY_RESULT, MOCK_RESULT))

    assert response.status_code == 200
    calls = await _calls_for_patient(patient.id)
    assert len(calls) == 2
    assert {c.run_id for c in calls} == {response.json()["extraction_run_id"]}
    assert {c.user_id for c in calls} == {1}
    assert all(c.input_tokens == 100 for c in calls)


async def test_a_failed_extraction_still_stores_the_calls_it_made():
    with TestClient(app, raise_server_exceptions=False) as client:
        patient = await _seed_patient()
        response, _ = _extract(
            client, patient_id=patient.id, side_effect=_metered(MOCK_SUMMARY_RESULT, RuntimeError("model down"))
        )

    assert response.status_code == 500
    calls = await _calls_for_patient(patient.id)
    assert len(calls) == 2
    assert {c.run_id for c in calls} == {None}


def test_price_table_costs_known_models_and_leaves_unknown_ones_unpriced():
    prices = PriceTable({"m": ModelPrice(Decimal("1.00"), Decimal("4.00"))})

    assert prices.cost("m", 1_000_000, 500_000) == Decimal("3.00")
    assert prices.cost("m", None, None) == Decimal(0)
    assert prices.cost("unknown", 1000, 1000) is None


def test_price_overrides_layer_over_the_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", '{"qwen3-32b": {"input": 0.2, "output": 0.6}}')
    prices = PriceTable.from_settings()

    assert prices.cost("qwen3-32b", 1_000_000, 0) == Decimal("0.2")
    assert prices.is_priced("mistral-medium-latest")


def test_malformed_price_overrides_fall_back_to_the_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", "not json")

    assert PriceTable.from_settings().is_priced("mistral-small-latest")


@pytest.fixture
async def as_admin_on_a_quiet_day():
    """An admin, and a pinned "today" far from any other test's calls."""
    async with session_scope() as session:
        admin = await UserRepository(session).create(
            email=f"usage-{uuid.uuid4().hex[:8]}@example.test",
            hashed_password="!",
            full_name="Admin Usage",
            role=UserRole.ADMIN,
        )
    app.dependency_overrides[get_current_user] = lambda: admin

    class _Pinned:
        def today(self) -> date:
            return date(2031, 3, 10)

    app.dependency_overrides[get_clock] = lambda: _Pinned()
    yield admin
    app.dependency_overrides.pop(get_clock, None)


async def test_usage_report_totals_days_and_breakdown(as_admin_on_a_quiet_day):
    async with session_scope() as session:
        repo = LLMCallRepository(session)
        await repo.add_many(
            [
                # 2031-03-09 23:30 in Montréal is already the 10th in UTC: counted on the 9th.
                _record("mistral-medium-latest", "billing_codes", input_tokens=1_000_000, output_tokens=0,
                        started_at=datetime(2031, 3, 10, 3, 30, tzinfo=timezone.utc)),
                _record("unpriced-model", "consultation_summary",
                        started_at=datetime(2031, 3, 10, 15, 0, tzinfo=timezone.utc)),
            ],
            LLMCallOwner(user_id=as_admin_on_a_quiet_day.id),
        )

    with TestClient(app) as client:
        response = client.get("/admin/usage", params={"start": "2031-03-08", "group_by": "model"})
        by_user = client.get("/admin/usage", params={"start": "2031-03-08", "group_by": "user"})

    assert response.status_code == 200
    body = response.json()
    assert body["end"] == "2031-03-10"
    assert body["totals"]["calls"] == 2
    assert body["totals"]["unpriced_calls"] == 1
    assert Decimal(body["totals"]["cost_usd"]) == Decimal("0.4")
    assert [(d["key"], d["calls"]) for d in body["by_day"]] == [
        ("2031-03-08", 0), ("2031-03-09", 1), ("2031-03-10", 1)
    ]
    assert [b["key"] for b in body["breakdown"]] == ["mistral-medium-latest", "unpriced-model"]
    assert [b["label"] for b in by_user.json()["breakdown"]] == ["Admin Usage"]


async def test_usage_report_rejects_a_backwards_range(as_admin_on_a_quiet_day):
    with TestClient(app) as client:
        response = client.get("/admin/usage", params={"start": "2031-03-10", "end": "2031-03-01"})

    assert response.status_code == 422

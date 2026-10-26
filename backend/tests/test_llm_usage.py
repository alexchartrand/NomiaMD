"""app/llm/usage.py: scopes collect the calls recorded inside them (and only those),
purposes tag them, and every call is logged as one structured `llm_call` line."""

import asyncio
import logging
from datetime import datetime, timezone

from app.llm import LLMCallRecord, UsageRecorder, call_purpose, usage_scope
from app.llm.usage import current_purpose


def _call(purpose: str | None = None, *, input_tokens: int = 10) -> LLMCallRecord:
    return LLMCallRecord(
        kind="chat",
        provider="test",
        model="m",
        purpose=purpose,
        input_tokens=input_tokens,
        output_tokens=2,
        latency_ms=5.0,
        started_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
    )


def test_a_scope_collects_calls_recorded_while_it_is_open_only():
    recorder = UsageRecorder()
    recorder.record(_call())

    with usage_scope() as scope:
        recorder.record(_call(input_tokens=1))
    recorder.record(_call())

    assert [c.input_tokens for c in scope.records] == [1]


def test_nested_scopes_both_see_the_inner_calls():
    recorder = UsageRecorder()

    with usage_scope() as outer:
        recorder.record(_call(input_tokens=1))
        with usage_scope() as inner:
            recorder.record(_call(input_tokens=2))

    assert [c.input_tokens for c in outer.records] == [1, 2]
    assert [c.input_tokens for c in inner.records] == [2]


async def test_concurrent_scopes_do_not_see_each_other():
    recorder = UsageRecorder()

    async def note(tokens: int) -> list[int]:
        with usage_scope() as scope:
            await asyncio.sleep(0)
            recorder.record(_call(input_tokens=tokens))
            await asyncio.sleep(0)
            recorder.record(_call(input_tokens=tokens))
        return [c.input_tokens for c in scope.records]

    assert await asyncio.gather(note(1), note(2)) == [[1, 1], [2, 2]]


async def test_gather_children_report_into_the_parent_scope():
    recorder = UsageRecorder()

    async def child(tokens: int) -> None:
        recorder.record(_call(input_tokens=tokens))

    with usage_scope() as scope:
        await asyncio.gather(child(1), child(2))

    assert sorted(c.input_tokens for c in scope.records) == [1, 2]


def test_innermost_purpose_wins_and_is_restored():
    assert current_purpose() is None
    with call_purpose("billing_codes"):
        with call_purpose("billing_codes.retrieval"):
            assert current_purpose() == "billing_codes.retrieval"
        assert current_purpose() == "billing_codes"
    assert current_purpose() is None


def test_every_call_is_logged_as_one_structured_line(caplog):
    with caplog.at_level(logging.INFO, logger="app.llm.usage"):
        UsageRecorder().record(_call("consultation_summary"))

    [record] = caplog.records
    assert record.getMessage() == "llm_call"
    assert record.purpose == "consultation_summary"
    assert record.input_tokens == 10 and record.output_tokens == 2
    assert record.started_at == "2026-10-08T00:00:00+00:00"

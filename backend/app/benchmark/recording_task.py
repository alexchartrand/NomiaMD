"""Wraps an extraction task to keep what run_extraction never returns: the prompt it built
and the model's raw JSON before the task's parse() cleaned it up — for billing_codes, the
invented and malformed codes parse() silently drops."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.tasks.base import ExtractionTask, PreparedPrompt

TInput = TypeVar("TInput")


class RecordingTask(ExtractionTask[TInput], Generic[TInput]):
    """One per call: it holds that call's prompt and raw output."""

    def __init__(self, inner: ExtractionTask[TInput]):
        self._inner = inner
        # Read by run_extraction to pick the model and tag the call.
        self.name = inner.name
        self.model = inner.model
        self.prepared: PreparedPrompt | None = None
        self.raw: dict[str, Any] | None = None

    async def build_prompt(self, task_input: TInput) -> PreparedPrompt:
        self.prepared = await self._inner.build_prompt(task_input)
        return self.prepared

    def json_schema(self) -> dict[str, Any]:
        return self._inner.json_schema()

    def parse(self, raw: dict[str, Any], prepared: PreparedPrompt) -> BaseModel:
        self.raw = raw
        return self._inner.parse(raw, prepared)

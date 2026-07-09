"""The pluggable extraction-task interface.

Every output type this system produces (billing codes today; prescriptions, consultation
notes, etc. later) implements this interface. The transcript ingestion and Claude API
plumbing (app/extraction/engine.py) is shared and never needs to change when a new task
is added — only a new class implementing ExtractionTask.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ExtractionTask(ABC):
    name: str

    @abstractmethod
    def build_prompt(self, transcript: str) -> tuple[str, str]:
        """Returns (system_prompt, user_message) for this transcript."""

    @abstractmethod
    def json_schema(self) -> dict[str, Any]:
        """JSON schema passed to output_config.format for structured extraction."""

    @abstractmethod
    def parse(self, raw: dict[str, Any]) -> BaseModel:
        """Validate/parse the model's raw JSON output into a typed result."""

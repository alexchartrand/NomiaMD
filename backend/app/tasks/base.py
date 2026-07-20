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
    def build_prompt(self, input_text: str) -> tuple[str, str]:
        """Returns (system_prompt, user_message) for this task's input text.

        For most tasks this is the raw transcript. billing_codes is the exception: it takes
        the rendered text of an already-generated consultation_summary instead (see
        app/extraction/pipeline.py), not the raw transcript directly.
        """

    @abstractmethod
    def json_schema(self) -> dict[str, Any]:
        """JSON schema passed to output_config.format for structured extraction."""

    @abstractmethod
    def parse(self, raw: dict[str, Any]) -> BaseModel:
        """Validate/parse the model's raw JSON output into a typed result."""

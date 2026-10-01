"""Turn what a source hands us (a demo note, a paste, an uploaded file) into SourceNotes for
IntakeService.receive. Connectors only read structured fields; they never call the LLM."""

from app.intake.connectors.manual import ManualConnector, UnsupportedUploadError
from app.intake.connectors.nam_header import read_header_nam
from app.intake.connectors.sample import SAMPLE_SOURCE_SYSTEM, SampleConnector
from app.intake.connectors.splitter import NoteSplitter

__all__ = [
    "SAMPLE_SOURCE_SYSTEM",
    "ManualConnector",
    "NoteSplitter",
    "SampleConnector",
    "UnsupportedUploadError",
    "read_header_nam",
]

"""Retention: what is removed once it's past its period, and when (app/retention/policy.py).
Note text is scrubbed, never the encounter or its billing (note_scrub.py). Run nightly by the
worker (app/worker.py) or by hand (scripts/purge.py)."""

from app.retention.job import RetentionJob, RetentionReport
from app.retention.note_scrub import NoteScrubber, ScrubOutcome
from app.retention.policy import RetentionPolicy

__all__ = ["NoteScrubber", "RetentionJob", "RetentionPolicy", "RetentionReport", "ScrubOutcome"]

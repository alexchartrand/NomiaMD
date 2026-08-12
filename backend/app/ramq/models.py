"""Shared RAMQ code data shapes — mirrors ramq-ingestion's src/models.py, which is where
this shape originates (Code.fees -> here). This module owns the read-side (RamqCandidate,
built from a retrieved node's metadata); ramq-ingestion owns the write-side (Code, the
extraction/embedding schema)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Fee:
    amount: float | None
    when_to_use: str | None
    majoration: str | None


@dataclass(frozen=True)
class RamqCandidate:
    code: str
    description: str
    when_to_use: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    fees: tuple[Fee, ...] = ()

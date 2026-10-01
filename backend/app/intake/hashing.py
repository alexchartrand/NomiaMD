"""The fingerprint that tells two versions of one external note apart — a changed note
gets a new hash, so it's a new Encounter row rather than a silent overwrite."""

import hashlib


def content_hash(note_text: str) -> str:
    """sha256 hex of the note text, exactly as stored."""
    return hashlib.sha256(note_text.encode("utf-8")).hexdigest()

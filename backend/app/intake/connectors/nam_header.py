"""The NAM a note states in a header line ("**NAM :** DESR81021001", "NAM: DESR 8102 1001").
A structured field match, never inference: a NAM mentioned in the prose doesn't count."""

import re

from app.patients import nam

# Bold markers are optional on either side of the colon.
NAM_HEADER_RE = re.compile(r"^[ \t]*(?:\*\*)?[ \t]*NAM[ \t]*(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?(?P<value>.*)$", re.MULTILINE)
# A header value may carry more than the NAM ("DESR 8102 1001 (exp. 2027-02)").
_NAM_VALUE_RE = re.compile(r"\b[A-Za-z]{4}[\s-]?\d{4}[\s-]?\d{4}\b")


def read_header_nam(text: str) -> str | None:
    """The normalized NAM of the note's header lines, or None when there's none, none is
    valid, or two header lines disagree — an ambiguous NAM is left for the physician."""
    found = {_parse_value(match.group("value")) for match in NAM_HEADER_RE.finditer(text)}
    found.discard(None)
    return found.pop() if len(found) == 1 else None


def _parse_value(value: str) -> str | None:
    match = _NAM_VALUE_RE.search(value)
    return nam.normalize(match.group()) if match else None

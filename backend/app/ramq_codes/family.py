"""Collapses near-duplicate RAMQ code variants using deterministic facts from
BillingContext, instead of letting the model guess a 50/50 axis it was never given (panel
size, registration, vulnerability, age band). Pure text/data logic — no LLM, no DB — so it
unit-tests against the same fixtures the stubbed retriever uses (see tests/conftest.py).

`header_path` (app/ramq_codes/models.py's Code.header_path) groups a family: 315 of the 362
rows in the live `codes` table as of 2026-08 share a header_path with at least one sibling,
differing only on the axes this class resolves. `header_path` is used whole, never trimmed
to a "meaningful" suffix — see Code.header_path's docstring for why the leading section
segment matters once the corpus grows beyond section B."""

import re
from dataclasses import dataclass

from app.ramq_codes.context import (
    AXIS_AGE_BAND,
    AXIS_PANEL_SIZE,
    AXIS_REGISTRATION,
    AXIS_VULNERABILITY,
    BillingContext,
)
from app.ramq_codes.models import Code

_PANEL_SIZE_THRESHOLD = 500
_AGE_THRESHOLDS = (70, 80)

# Each matcher inspects a candidate's description + when_to_use text and returns True/False/
# None (axis not expressed in this candidate's text at all — most codes outside the B
# section's visit families won't mention these axes, and None means "don't touch this
# candidate's family membership check").
_PANEL_UNDER = re.compile(r"moins de 500 patients", re.IGNORECASE)
_PANEL_OVER = re.compile(r"500 patients ou plus", re.IGNORECASE)
_VULNERABLE = re.compile(r"patient vuln[ée]rable", re.IGNORECASE)
_NON_VULNERABLE = re.compile(r"patient non vuln[ée]rable", re.IGNORECASE)
_NON_INSCRIT = re.compile(r"non inscrit", re.IGNORECASE)
_INSCRIT = re.compile(r"(?<!non )\binscrit", re.IGNORECASE)
# "inscrite ou non inscrite" (18 of 362 rows, e.g. 15805's pregnancy-followup family) means
# the code applies regardless of registration — not "for non-registered patients". Checked
# before _NON_INSCRIT/_INSCRIT below, since "inscrit ou non inscrit" would otherwise
# substring-match _NON_INSCRIT and be misread as the opposite of what it says. Same
# construction is checked for vulnerability even though it doesn't occur in the corpus
# today (0 of 362 rows) — cheap insurance against a future ingestion adding it.
_EITHER_REGISTRATION = re.compile(r"inscrite?s? ou non inscrite?s?", re.IGNORECASE)
_EITHER_VULNERABILITY = re.compile(r"vuln[ée]rables? ou non vuln[ée]rables?", re.IGNORECASE)
# Numeric ("70 ans") and spelled-out ("soixante-dix (70) ans") phrasing both appear in the
# manual text — see app/ramq_codes/models.py Code.header_path's docstring for the same
# "match the source text as written, don't assume one convention" stance.
_AGE_UNDER = {
    70: re.compile(r"moins de (?:soixante-dix \(70\)|70) ans", re.IGNORECASE),
    80: re.compile(r"moins de (?:quatre-vingts? \(80\)|80) ans", re.IGNORECASE),
}
_AGE_OVER_OR_EQUAL = {
    70: re.compile(r"(?:soixante-dix \(70\)|70) ans ou plus", re.IGNORECASE),
    80: re.compile(r"(?:quatre-vingts? \(80\)|80) ans ou plus", re.IGNORECASE),
}


def _text(code: Code) -> str:
    return " ".join((code.description, *code.when_to_use))


def _panel_variant(text: str) -> bool | None:
    if _PANEL_UNDER.search(text):
        return True
    if _PANEL_OVER.search(text):
        return False
    return None


def _vulnerability_variant(text: str) -> bool | None:
    # Checked before the specific patterns below: "vulnérable ou non vulnérable" would
    # otherwise substring-match _VULNERABLE (or _NON_VULNERABLE) and be misread as
    # discriminating on an axis the text actually says doesn't apply here.
    if _EITHER_VULNERABILITY.search(text):
        return None
    # Non-vulnerable next: "patient non vulnérable" also matches the plain "vulnérable"
    # pattern as a substring.
    if _NON_VULNERABLE.search(text):
        return False
    if _VULNERABLE.search(text):
        return True
    return None


def _registration_variant(text: str) -> bool | None:
    if _EITHER_REGISTRATION.search(text):
        return None
    if _NON_INSCRIT.search(text):
        return False
    if _INSCRIT.search(text):
        return True
    return None


def _age_threshold_variant(text: str) -> tuple[int, bool] | None:
    """Returns (threshold, is_under) for whichever of the two known thresholds this
    candidate's text expresses, or None if neither pattern matches."""
    for threshold in _AGE_THRESHOLDS:
        if _AGE_UNDER[threshold].search(text):
            return threshold, True
        if _AGE_OVER_OR_EQUAL[threshold].search(text):
            return threshold, False
    return None


@dataclass(frozen=True)
class FamilyCollapseResult:
    candidates: list[Code]
    unresolved_axes: tuple[str, ...]


class CodeFamilySelector:
    """Groups candidates by header_path and drops any variant that contradicts a fact
    BillingContext resolves.

    No "keep at least one" fallback for a family a filter empties out. Each axis is binary
    (e.g. <500/>=500 patients) and `_filter_axis`/`_filter_age_axis` always keep a candidate
    whose text doesn't express the axis at all (variant is None) — so a filter can only drop
    every remaining member when every one of them explicitly and uniformly states the
    *contradicting* value with no ambiguity between them. That is not a matcher glitch to
    guard against; it is the filter doing its job: e.g. a family of "consultation
    mineure/ordinaire/majeure pour les patients de 70 ans ou plus" candidates for a
    50-year-old patient should end up with none surviving, not one kept anyway because it
    happened to share a header_path with siblings. A prior version of this class kept the
    first-ranked member whenever a family went fully empty, meant to protect against a
    parser bug — verified against the real `codes` table, it instead resurrected exactly
    that kind of clearly-wrong, age-inapplicable suggestion. The residual risk this class
    can't fully cover is the mirror case — a matcher misreading a genuinely-matching
    candidate's text as the *contradicting* value (a false flip, not just a missed match) —
    which is an inherent limit of text-pattern axis parsing; the eval harness (Part 6) and
    the unit tests here pin real corpus phrasing specifically to catch that during
    development rather than relying on a runtime safety net that has its own failure mode."""

    def select(self, candidates: list[Code], context: BillingContext) -> FamilyCollapseResult:
        known = context.known_axes()
        unresolved: set[str] = set()

        families: dict[str, list[Code]] = {}
        order: list[str] = []
        for code in candidates:
            key = code.header_path or code.number  # ungrouped codes are their own family
            if key not in families:
                families[key] = []
                order.append(key)
            families[key].append(code)

        kept: list[Code] = []
        for key in order:
            survivors, family_unresolved = self._collapse_family(families[key], known)
            unresolved |= family_unresolved
            kept.extend(survivors)

        return FamilyCollapseResult(candidates=kept, unresolved_axes=tuple(sorted(unresolved)))

    def _collapse_family(
        self, members: list[Code], known: dict[str, bool | int | None]
    ) -> tuple[list[Code], set[str]]:
        survivors = list(members)
        unresolved: set[str] = set()

        survivors, resolved = self._filter_axis(
            survivors, known, AXIS_PANEL_SIZE, lambda text: _panel_variant(text),
            actual=lambda value: value < _PANEL_SIZE_THRESHOLD,
        )
        if not resolved:
            unresolved.add(AXIS_PANEL_SIZE)

        survivors, resolved = self._filter_axis(
            survivors, known, AXIS_VULNERABILITY, _vulnerability_variant, actual=lambda value: bool(value)
        )
        if not resolved:
            unresolved.add(AXIS_VULNERABILITY)

        survivors, resolved = self._filter_axis(
            survivors, known, AXIS_REGISTRATION, _registration_variant, actual=lambda value: bool(value)
        )
        if not resolved:
            unresolved.add(AXIS_REGISTRATION)

        survivors, resolved = self._filter_age_axis(survivors, known)
        if not resolved:
            unresolved.add(AXIS_AGE_BAND)

        return survivors, unresolved

    def _filter_axis(self, members, known, axis, variant_fn, *, actual) -> tuple[list[Code], bool]:
        fact = known.get(axis)
        if fact is None:
            return members, False

        actual_value = actual(fact)
        filtered = []
        for code in members:
            variant = variant_fn(_text(code))
            if variant is None or variant == actual_value:
                filtered.append(code)
        return filtered, True

    def _filter_age_axis(self, members: list[Code], known: dict) -> tuple[list[Code], bool]:
        age = known.get(AXIS_AGE_BAND)
        if age is None:
            return members, False

        filtered = []
        for code in members:
            variant = _age_threshold_variant(_text(code))
            if variant is None:
                filtered.append(code)
                continue
            threshold, is_under = variant
            matches = (age < threshold) == is_under
            if matches:
                filtered.append(code)
        return filtered, True

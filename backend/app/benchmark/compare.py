"""Per-note comparison of two runs: for retrieval, did every expected code rank better or
worse; for selection, which right codes were gained or lost and which wrong ones appeared or
went away. An average can stay flat while one note gains a code and another loses one —
exactly the "a fix on one transcript regresses another" failure — so regressions are listed
note by note, worst first."""

from typing import Literal

from pydantic import BaseModel

from app.benchmark.scoring import CodeStatus, RetrievalScore
from app.benchmark.selection_scoring import SelectionScore

Change = Literal["regressed", "improved", "unchanged"]
Verdict = Literal["regressed", "mixed", "improved", "unchanged"]
_VERDICT_ORDER = {"regressed": 0, "mixed": 1, "improved": 2, "unchanged": 3}


def _verdict(regressed: bool, improved: bool) -> Verdict:
    if regressed and improved:
        return "mixed"
    if regressed:
        return "regressed"
    return "improved" if improved else "unchanged"

# Lower is better: an exact hit is worth its rank; a same-family hit beats nothing at all.
_FAMILY_ONLY_COST = 1_000
_MISSING_COST = 10_000


def _cost(status: str | None, rank: int | None) -> int:
    if status == CodeStatus.EXACT and rank is not None:
        return rank
    if status == CodeStatus.FAMILY_ONLY:
        return _FAMILY_ONLY_COST
    return _MISSING_COST


class CodeChange(BaseModel):
    code: str
    before_status: str | None
    before_rank: int | None
    after_status: str | None
    after_rank: int | None
    change: Change


class NoteComparison(BaseModel):
    patient_id: str
    difficulty: str
    verdict: Verdict
    changes: list[CodeChange]
    before_candidates: int
    after_candidates: int


class RunComparison(BaseModel):
    baseline: str
    candidate: str
    notes: list[NoteComparison]
    counts: dict[str, int]


class RunComparator:
    def compare(
        self, baseline_name: str, baseline: list[RetrievalScore], candidate_name: str, candidate: list[RetrievalScore]
    ) -> RunComparison:
        before_by_id = {s.patient_id: s for s in baseline}
        notes = [
            self._note(before_by_id[after.patient_id], after) for after in candidate if after.patient_id in before_by_id
        ]
        notes.sort(key=lambda n: (_VERDICT_ORDER[n.verdict], -self._severity(n), n.patient_id))
        counts = {verdict: sum(1 for n in notes if n.verdict == verdict) for verdict in _VERDICT_ORDER}
        return RunComparison(baseline=baseline_name, candidate=candidate_name, notes=notes, counts=counts)

    @staticmethod
    def _note(before: RetrievalScore, after: RetrievalScore) -> NoteComparison:
        before_by_code = {o.code: o for o in before.outcomes}
        after_by_code = {o.code: o for o in after.outcomes}
        changes = []
        for code in sorted(before_by_code.keys() | after_by_code.keys()):
            b, a = before_by_code.get(code), after_by_code.get(code)
            change = CodeChange(
                code=code,
                before_status=b.status.value if b else None,
                before_rank=b.rank if b else None,
                after_status=a.status.value if a else None,
                after_rank=a.rank if a else None,
                change="unchanged",
            )
            delta = _cost(change.after_status, change.after_rank) - _cost(change.before_status, change.before_rank)
            change.change = "regressed" if delta > 0 else "improved" if delta < 0 else "unchanged"
            changes.append(change)
        kinds = {c.change for c in changes}
        return NoteComparison(
            patient_id=after.patient_id,
            difficulty=after.difficulty,
            verdict=_verdict("regressed" in kinds, "improved" in kinds),
            changes=changes,
            before_candidates=before.candidate_count,
            after_candidates=after.candidate_count,
        )

    @staticmethod
    def _severity(note: NoteComparison) -> int:
        return sum(
            abs(_cost(c.after_status, c.after_rank) - _cost(c.before_status, c.before_rank)) for c in note.changes
        )


class SelectionNoteComparison(BaseModel):
    patient_id: str
    difficulty: str
    verdict: Verdict
    # Among the codes the model is sure of (retained): expected codes the candidate run
    # retained and the baseline didn't, and the reverse; wrong retained codes only the
    # candidate run has, and the ones it no longer has.
    gained: list[str]
    lost: list[str]
    new_wrong: list[str]
    fixed_wrong: list[str]
    # Expected codes that entered or left the answer altogether (either tier).
    gained_overall: list[str]
    lost_overall: list[str]


class SelectionComparison(BaseModel):
    baseline: str
    candidate: str
    notes: list[SelectionNoteComparison]
    counts: dict[str, int]


class SelectionComparator:
    """Unlabeled notes are skipped: without expected codes, a change is neither better nor
    worse."""

    def compare(
        self, baseline_name: str, baseline: list[SelectionScore], candidate_name: str, candidate: list[SelectionScore]
    ) -> SelectionComparison:
        before_by_id = {s.patient_id: s for s in baseline}
        notes = [
            self._note(before_by_id[after.patient_id], after)
            for after in candidate
            if after.patient_id in before_by_id and after.is_labeled
        ]
        notes.sort(
            key=lambda n: (
                _VERDICT_ORDER[n.verdict],
                -(len(n.lost) + len(n.new_wrong) + len(n.lost_overall)),
                n.patient_id,
            )
        )
        counts = {verdict: sum(1 for n in notes if n.verdict == verdict) for verdict in _VERDICT_ORDER}
        return SelectionComparison(baseline=baseline_name, candidate=candidate_name, notes=notes, counts=counts)

    @staticmethod
    def _note(before: SelectionScore, after: SelectionScore) -> SelectionNoteComparison:
        def right(score: SelectionScore) -> set[str]:
            return {o.code for o in score.retained if o.correct}

        def wrong(score: SelectionScore) -> set[str]:
            return {o.code for o in score.retained if o.correct is False}

        def found(score: SelectionScore) -> set[str]:
            return {o.code for o in score.returned if o.correct}

        gained, lost = sorted(right(after) - right(before)), sorted(right(before) - right(after))
        new_wrong, fixed_wrong = sorted(wrong(after) - wrong(before)), sorted(wrong(before) - wrong(after))
        gained_overall, lost_overall = sorted(found(after) - found(before)), sorted(found(before) - found(after))
        return SelectionNoteComparison(
            patient_id=after.patient_id,
            difficulty=after.difficulty,
            verdict=_verdict(bool(lost or new_wrong or lost_overall), bool(gained or fixed_wrong or gained_overall)),
            gained=gained,
            lost=lost,
            new_wrong=new_wrong,
            fixed_wrong=fixed_wrong,
            gained_overall=gained_overall,
            lost_overall=lost_overall,
        )

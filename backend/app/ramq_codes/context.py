"""Value objects for the administrative facts BillingCodesTask needs but can never derive
from a transcript (see CLAUDE.md): the billing physician's own practice facts, and the
identified patient's roster status. Pure data — no I/O, no dependency on postgresdb or
auth — assembled by BillingContextBuilder (context_builder.py) and consumed by
CodeFamilySelector (family.py) and BillingCodesTask's prompt (task.py).

Every field is nullable. An unresolved axis (no roster match, no profile on file) must
degrade to "unknown", never to a guessed default — a wrong assumption here is worse than an
admitted gap, since it would silently narrow the candidate list instead of asking the
physician to confirm."""

from dataclasses import dataclass, field
from datetime import date

# Names for the axes CodeFamilySelector resolves — shared vocabulary between
# BillingContext.known_axes(), CodeFamilySelector's unresolved-axis reporting, and the
# prompt's "please confirm" instructions, so all three always refer to the same thing.
AXIS_PANEL_SIZE = "panel_size"
AXIS_REGISTRATION = "registration"
AXIS_VULNERABILITY = "vulnerability"
AXIS_AGE_BAND = "age_band"

ALL_AXES = (AXIS_PANEL_SIZE, AXIS_REGISTRATION, AXIS_VULNERABILITY, AXIS_AGE_BAND)


@dataclass(frozen=True)
class PhysicianContext:
    """The billing physician's own practice facts, as of the encounter date — see
    ProfileService.as_of, not .current: a past encounter is interpreted under the panel
    size in effect then, not today's (same reasoning as PhysicianProfile's docstring and
    ClaimCode's fee snapshot). When the encounter predates the physician's earliest profile
    version, BillingContextBuilder falls back to that earliest version instead of leaving
    this all-null — see its docstring and BACKLOG.md for why that's a deliberate, revisit-
    later trade-off rather than the "never guess" default this class otherwise holds to."""

    number_of_patients: int | None = None
    physician_type: str | None = None
    remuneration_type: str | None = None


@dataclass(frozen=True)
class PatientContext:
    """The identified patient's roster status, as of the encounter date. None throughout
    when no roster match was found — see BillingContextBuilder."""

    age_years: float | None = None
    is_registered: bool | None = None
    is_vulnerable: bool | None = None


@dataclass(frozen=True)
class BillingContext:
    """Everything BillingCodesTask's prompt states as authoritative fact rather than lets
    the model infer from the transcript. Both halves are independently optional: a
    physician with no profile on file and/or a patient with no roster match still produce a
    valid (all-null) BillingContext — the pipeline degrades to today's guess-from-transcript
    behavior for whichever axes stay unknown, rather than failing the extraction."""

    physician: PhysicianContext = field(default_factory=PhysicianContext)
    patient: PatientContext = field(default_factory=PatientContext)
    encounter_date: date | None = None

    def known_axes(self) -> dict[str, bool | int | None]:
        """Which of the four family-disambiguating axes this context can resolve, and to
        what value. A key is present only when the fact is actually known — CodeFamilySelector
        treats an absent key exactly like `known_axes().get(axis)` returning None: keep every
        variant and flag the axis unresolved."""
        axes: dict[str, bool | int | None] = {}
        if self.physician.number_of_patients is not None:
            axes[AXIS_PANEL_SIZE] = self.physician.number_of_patients
        if self.patient.is_registered is not None:
            axes[AXIS_REGISTRATION] = self.patient.is_registered
        if self.patient.is_vulnerable is not None:
            axes[AXIS_VULNERABILITY] = self.patient.is_vulnerable
        if self.patient.age_years is not None:
            axes[AXIS_AGE_BAND] = self.patient.age_years
        return axes

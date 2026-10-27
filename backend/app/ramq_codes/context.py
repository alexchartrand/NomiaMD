"""Value objects for the administrative facts the billing_codes step needs but can never derive
from a transcript (see CLAUDE.md): the billing physician's own practice facts, and the
identified patient's roster status. Pure data — no I/O, no dependency on postgresdb or
auth — assembled by BillingContextBuilder (context_builder.py) and consumed by the
eligibility prefilter/UnresolvedAxisDetector (eligibility.py) and the billing_codes prompt
(prompt.py).

Every field is nullable. An unresolved axis (no roster match, no profile on file) must
degrade to "unknown", never to a guessed default — a wrong assumption here is worse than an
admitted gap, since it would silently narrow the candidate list instead of asking the
physician to confirm."""

from dataclasses import dataclass, field
from datetime import date, time

from app.care_setting import CareSetting
from app.shifts import DayType, ShiftPeriod

# Names for the eligibility axes a code variant can be bound on — shared vocabulary between
# BillingContext.known_axes(), UnresolvedAxisDetector's unresolved-axis reporting, and the
# prompt's "please confirm" instructions, so all three always refer to the same thing.
AXIS_PANEL_SIZE = "panel_size"
AXIS_REGISTRATION = "registration"
AXIS_VULNERABILITY = "vulnerability"
AXIS_AGE_BAND = "age_band"

ALL_AXES = (AXIS_PANEL_SIZE, AXIS_REGISTRATION, AXIS_VULNERABILITY, AXIS_AGE_BAND)

# The same axes in the French wording shown to both the billing_codes model (as something it
# must ask the physician to confirm) and the physician (ExtractedCode.needs_confirmation, and
# a hand-searched code's own "à confirmer" — see app/code_catalog/). No thresholds are named
# here: they vary across the manual's sections, and each code's own description states the
# one it's bound by.
AXIS_LABELS_FR = {
    AXIS_PANEL_SIZE: "la taille de la clientèle inscrite du médecin",
    AXIS_REGISTRATION: "le statut d'inscription du patient auprès de ce médecin (inscrit ou non)",
    AXIS_VULNERABILITY: "le statut de vulnérabilité du patient au sens de la RAMQ",
    AXIS_AGE_BAND: "l'âge exact du patient",
}


@dataclass(frozen=True)
class PhysicianContext:
    """The billing physician's own practice facts, as of the encounter date — see
    ProfileService.as_of, not .current: a past encounter is interpreted under the panel
    size in effect then, not today's (same reasoning as PhysicianProfile's docstring and
    ClaimCode's fee snapshot). An encounter older than the physician's first profile
    version reads that first version."""

    panel_size: int | None = None
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
class ShiftContext:
    """The shift the encounter took place in — the physician's pick, else the one its date
    and time fall in (app/shifts/encounter_setting.py) — with its hours in the clinic's local
    time, the end at or before the start being the next day."""

    period: ShiftPeriod
    service_date: date
    start_time: time
    end_time: time


@dataclass(frozen=True)
class BillingContext:
    """Everything the billing_codes prompt states as authoritative fact rather than lets
    the model infer from the transcript. Both halves are independently optional: a
    physician with no profile on file and/or a patient with no roster match still produce a
    valid (all-null) BillingContext — the pipeline degrades to today's guess-from-transcript
    behavior for whichever axes stay unknown, rather than failing the extraction."""

    physician: PhysicianContext = field(default_factory=PhysicianContext)
    patient: PatientContext = field(default_factory=PatientContext)
    encounter_date: date | None = None
    # Where the encounter took place, from its source or the physician (see
    # app/care_setting.py). Not an eligibility axis — no codes column is bound on it — it
    # scopes the visit-code search (visit_query.py) and is stated in the prompt.
    care_setting: CareSetting | None = None
    # When the encounter took place, for the time-based supplements and majorations: its
    # shift, the day type of its date (else its shift's), and its start time from the
    # source. Not eligibility axes either — stated in the prompt only.
    shift: ShiftContext | None = None
    day_type: DayType | None = None
    encounter_time: time | None = None

    def known_axes(self) -> dict[str, bool | int | None]:
        """Which of the four eligibility axes this context can resolve, and to what value. A
        key is present only when the fact is actually known — an absent key means that axis
        filters nothing, and UnresolvedAxisDetector flags it if any candidate is bound on it."""
        axes: dict[str, bool | int | None] = {}
        if self.physician.panel_size is not None:
            axes[AXIS_PANEL_SIZE] = self.physician.panel_size
        if self.patient.is_registered is not None:
            axes[AXIS_REGISTRATION] = self.patient.is_registered
        if self.patient.is_vulnerable is not None:
            axes[AXIS_VULNERABILITY] = self.patient.is_vulnerable
        if self.patient.age_years is not None:
            axes[AXIS_AGE_BAND] = self.patient.age_years
        return axes

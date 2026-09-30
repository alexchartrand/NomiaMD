"""Unit tests for app/ramq_codes/eligibility.py — BillingContext -> eligibility filter, and
which unknown axes the surviving candidates still depend on. Pure data logic, no DB.

Eligibility bounds below are copied from the real `codes_2026-06-05` rows they're named
after."""

from app.ramq_codes.context import (
    AXIS_AGE_BAND,
    AXIS_PANEL_SIZE,
    AXIS_REGISTRATION,
    AXIS_VULNERABILITY,
    BillingContext,
    PatientContext,
    PhysicianContext,
)
from app.ramq_codes.eligibility import EligibilityFilterFactory, UnresolvedAxisDetector
from app.ramq_codes.models import Code, CodeEligibility
from app.lancedb.eligibility import CodeEligibilityFilter

# Visite de prise en charge, patient non vulnérable inscrit de moins de 80 ans, clientèle
# inscrite de moins de 500 patients.
_15801 = Code(
    number="15801",
    description="Visite de prise en charge",
    eligibility=CodeEligibility(
        max_age=79, max_panel_size=499, requires_registered=True, requires_vulnerable=False
    ),
)
# A code with no bound on any axis.
_UNBOUNDED = Code(number="00059", description="Acte sans restriction")


# -- EligibilityFilterFactory ---------------------------------------------------------------


def test_empty_context_filters_nothing():
    assert EligibilityFilterFactory().from_context(BillingContext()) == CodeEligibilityFilter()


def test_known_facts_are_carried_over():
    context = BillingContext(
        physician=PhysicianContext(number_of_patients=320),
        patient=PatientContext(age_years=58.0, is_registered=True, is_vulnerable=False),
    )

    assert EligibilityFilterFactory().from_context(context) == CodeEligibilityFilter(
        age=58, panel_size=320, is_registered=True, is_vulnerable=False
    )


def test_age_is_floored_to_completed_years():
    # 79.6 is still "moins de 80 ans" (max_age=79) — rounding would wrongly exclude it.
    context = BillingContext(patient=PatientContext(age_years=79.6))

    assert EligibilityFilterFactory().from_context(context).age == 79


def test_age_under_one_year_is_zero():
    context = BillingContext(patient=PatientContext(age_years=0.4))

    assert EligibilityFilterFactory().from_context(context).age == 0


# -- UnresolvedAxisDetector -----------------------------------------------------------------


def test_every_axis_a_candidate_is_bounded_on_is_unresolved_when_nothing_is_known():
    unresolved = UnresolvedAxisDetector().detect([_15801], BillingContext())

    assert unresolved == tuple(sorted((AXIS_AGE_BAND, AXIS_PANEL_SIZE, AXIS_REGISTRATION, AXIS_VULNERABILITY)))


def test_a_known_axis_is_never_unresolved():
    context = BillingContext(physician=PhysicianContext(number_of_patients=320))

    unresolved = UnresolvedAxisDetector().detect([_15801], context)

    assert AXIS_PANEL_SIZE not in unresolved


def test_an_unknown_axis_no_candidate_is_bounded_on_is_not_flagged():
    assert UnresolvedAxisDetector().detect([_UNBOUNDED], BillingContext()) == ()


def test_no_candidates_means_nothing_to_confirm():
    assert UnresolvedAxisDetector().detect([], BillingContext()) == ()


def test_one_bounded_candidate_is_enough_to_flag_an_axis():
    registration_only = Code(
        number="X", description="", eligibility=CodeEligibility(requires_registered=False)
    )

    unresolved = UnresolvedAxisDetector().detect([_UNBOUNDED, registration_only], BillingContext())

    assert unresolved == (AXIS_REGISTRATION,)

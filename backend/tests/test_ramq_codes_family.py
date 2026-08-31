"""Unit tests for CodeFamilySelector (app/ramq_codes/family.py) — pure text/data logic, no
LLM and no DB. Candidate text below is copied verbatim from the real `codes` LanceDB table
(as of 2026-08) rather than invented, since the whole point of this class is parsing that
table's actual French phrasing; a made-up phrasing could pass even if the real one doesn't."""

from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext
from app.ramq_codes.family import CodeFamilySelector
from app.ramq_codes.models import Code

# Panel-size family: "Visite de prise en charge", <500 vs >=500 patients.
_15801 = Code(
    number="15801",
    libelle="",
    description=(
        "Visite de prise en charge d'un patient non vulnérable inscrit de moins de 80 ans, "
        "sur rendez-vous, clientèle inscrite de moins de 500 patients"
    ),
    header_path="B > Visites sur rendez-vous (<80 ans) > Patient non vulnérable inscrit > Visite de prise en charge",
)
_15802 = Code(
    number="15802",
    libelle="",
    description=(
        "Visite de prise en charge d'un patient non vulnérable inscrit de moins de 80 ans, "
        "sur rendez-vous, clientèle inscrite de 500 patients ou plus"
    ),
    header_path=_15801.header_path,
)

# Vulnerability family: "Visite périodique", vulnerable, <500 patients.
_15819 = Code(
    number="15819",
    libelle="",
    description=(
        "Visite périodique d'un patient vulnérable inscrit de moins de 80 ans, sur "
        "rendez-vous, clientèle inscrite de moins de 500 patients"
    ),
    header_path="B > Visites sur rendez-vous (<80 ans) > Patient vulnérable inscrit > Visite périodique",
)

# Registration-indifferent family (pregnancy follow-up): text says "inscrite ou non
# inscrite" — applies regardless of registration, not "for non-registered patients".
_15805 = Code(
    number="15805",
    libelle="",
    description=(
        "Visite de prise en charge de grossesse durant le premier trimestre, sans référence "
        "à un autre médecin durant le premier trimestre pour assurer le suivi, pour une "
        "patiente non vulnérable inscrite ou non inscrite de moins de 80 ans, sur "
        "rendez-vous, clientèle inscrite de moins de 500 patients"
    ),
    header_path="B > Visites sur rendez-vous (<80 ans) > Patient non vulnérable inscrit > Prise en charge de grossesse",
)

# Age-band family, spelled-out "70 ans ou plus" phrasing (no <70 sibling in this group —
# these are distinct consultation complexity levels, not axis-variant siblings, but they
# still all carry the same age-band claim).
_09231 = Code(
    number="09231",
    libelle="",
    description=(
        "Consultation mineure pour les patients de soixante-dix (70) ans ou plus, en "
        "clinique externe, au service d'urgence et au CLSC du réseau de garde intégré"
    ),
    header_path="B > Consultation et examen (70 ans ou plus) > Consultation",
)
_09237 = Code(
    number="09237",
    libelle="",
    description=(
        "Consultation majeure pour les patients de soixante-dix (70) ans ou plus, en "
        "clinique externe, au service d'urgence et au CLSC du réseau de garde intégré"
    ),
    header_path=_09231.header_path,
)


def test_unknown_context_keeps_every_variant_and_flags_all_axes_unresolved():
    result = CodeFamilySelector().select([_15801, _15802, _15819], BillingContext())

    assert {c.number for c in result.candidates} == {"15801", "15802", "15819"}
    assert set(result.unresolved_axes) == {"panel_size", "registration", "vulnerability", "age_band"}


def test_known_panel_size_keeps_only_the_matching_variant():
    context = BillingContext(physician=PhysicianContext(number_of_patients=320))

    result = CodeFamilySelector().select([_15801, _15802], context)

    assert {c.number for c in result.candidates} == {"15801"}
    assert "panel_size" not in result.unresolved_axes


def test_known_panel_size_over_threshold_keeps_the_other_variant():
    context = BillingContext(physician=PhysicianContext(number_of_patients=750))

    result = CodeFamilySelector().select([_15801, _15802], context)

    assert {c.number for c in result.candidates} == {"15802"}


def test_known_vulnerability_drops_the_vulnerable_only_code_for_a_non_vulnerable_patient():
    context = BillingContext(patient=PatientContext(is_vulnerable=False))

    result = CodeFamilySelector().select([_15801, _15819], context)

    assert {c.number for c in result.candidates} == {"15801"}


def test_registration_indifferent_phrasing_is_not_misread_as_non_registered_only():
    # "inscrite ou non inscrite" must not substring-match the "non inscrit" pattern and get
    # excluded for a registered patient — the code applies either way.
    context = BillingContext(patient=PatientContext(is_registered=True))

    result = CodeFamilySelector().select([_15805], context)

    assert {c.number for c in result.candidates} == {"15805"}
    assert "registration" not in result.unresolved_axes


def test_uniform_age_contradiction_empties_the_family_rather_than_keeping_one_anyway():
    # Every candidate in this group claims "70 ans ou plus"; for a 50-year-old patient none
    # of them apply. This must return nothing, not fall back to an arbitrary member — a
    # wrong age-band suggestion is actively harmful, not a safe default.
    context = BillingContext(patient=PatientContext(age_years=50))

    result = CodeFamilySelector().select([_09231, _09237], context)

    assert result.candidates == []
    assert "age_band" not in result.unresolved_axes


def test_matching_age_band_keeps_every_candidate_in_the_group():
    context = BillingContext(patient=PatientContext(age_years=75))

    result = CodeFamilySelector().select([_09231, _09237], context)

    assert {c.number for c in result.candidates} == {"09231", "09237"}


def test_a_candidate_silent_on_an_axis_is_never_dropped_by_that_axis():
    # 15805's own text doesn't say anything about vulnerability's sibling axis being
    # indifferent (it's explicitly non-vulnerable) — pick a code whose text simply never
    # mentions vulnerability at all, and confirm a known vulnerability fact doesn't drop it.
    silent = Code(number="99999", libelle="", description="Acte technique sans mention de clientèle", header_path="x")
    context = BillingContext(patient=PatientContext(is_vulnerable=True))

    result = CodeFamilySelector().select([silent], context)

    assert {c.number for c in result.candidates} == {"99999"}

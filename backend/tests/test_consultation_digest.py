"""ConsultationDigestBuilder: the consultation summary as the review shows it above the codes."""

from typing import get_args

from app.summary import ConsultationDigestBuilder, ConsultationSummaryResult
from app.summary.models import RequesterRole
from app.summary.review import _REQUESTER_LABELS
from tests.test_extraction import MOCK_SUMMARY_RESULT


def _summary(**overrides) -> ConsultationSummaryResult:
    return ConsultationSummaryResult.model_validate({**MOCK_SUMMARY_RESULT, **overrides})


def test_the_digest_keeps_what_the_physician_checks_codes_against():
    digest = ConsultationDigestBuilder().build(
        _summary(
            procedures_performed=[
                {
                    "procedure_description": "Suture d'une lacération de 3 cm à l'avant-bras",
                    "anesthesia_used": "local",
                    "diagnostic_or_therapeutic": "thérapeutique",
                }
            ],
            possible_billable_add_ons=["deplacement_urgence", "frais__kilometrage"],
            notes_uncertain_items=["Durée de la visite non précisée"],
        )
    )

    assert digest.short_description == MOCK_SUMMARY_RESULT["short_description"]
    clinical = MOCK_SUMMARY_RESULT["clinical_summary"]
    assert digest.reason_for_visit == clinical["chief_complaint_or_reason_for_visit"]
    assert digest.procedures == ["Suture d'une lacération de 3 cm à l'avant-bras"]
    assert digest.billable_add_ons == ["Deplacement urgence", "Frais kilometrage"]
    assert digest.open_questions == ["Durée de la visite non précisée"]
    assert digest.referral is None


def test_an_incoming_referral_carries_its_requester_and_reason():
    referral = {
        **MOCK_SUMMARY_RESULT["referral_information"],
        "present": True,
        "requester_role": "medecin_specialiste",
        "reason_for_referral": "Prise en charge du diabète",
    }
    digest = ConsultationDigestBuilder().build(_summary(referral_information=referral))

    assert digest.referral is not None
    assert digest.referral.requester == "Médecin spécialiste"
    assert digest.referral.reason == "Prise en charge du diabète"


def test_every_requester_role_has_a_label():
    assert set(_REQUESTER_LABELS) == set(get_args(RequesterRole))


def test_a_summary_stored_under_an_older_schema_has_no_digest():
    builder = ConsultationDigestBuilder()
    assert builder.from_stored({"short_description": 3}) is None
    assert builder.from_stored(MOCK_SUMMARY_RESULT).short_description == MOCK_SUMMARY_RESULT["short_description"]

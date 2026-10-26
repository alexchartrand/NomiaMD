"""The consultation summary as the review UI shows it above the proposed codes: the few facts
a physician checks codes against (what happened, acts performed, other billable items, a
referral, open questions), not the whole structured summary the billing step reads."""

from typing import Any

from pydantic import BaseModel, ValidationError

from app.summary.models import ConsultationSummaryResult

_REQUESTER_LABELS: dict[str, str] = {
    "medecin_omnipraticien": "Médecin omnipraticien",
    "medecin_specialiste": "Médecin spécialiste",
    "dentiste": "Dentiste",
    "optometriste": "Optométriste",
    "sage_femme": "Sage-femme",
    "autre_professionnel": "Autre professionnel",
}


class ReferralDigest(BaseModel):
    requester: str | None
    reason: str | None


class ConsultationDigest(BaseModel):
    short_description: str
    reason_for_visit: str | None
    procedures: list[str]
    billable_add_ons: list[str]
    # Only an incoming referral: another professional asked this physician to see the patient.
    referral: ReferralDigest | None
    # What the summary couldn't settle, phrased as questions for the physician.
    open_questions: list[str]


class ConsultationDigestBuilder:
    def build(self, summary: ConsultationSummaryResult) -> ConsultationDigest:
        clinical = summary.clinical_summary
        referral = summary.referral_information
        return ConsultationDigest(
            short_description=summary.short_description,
            reason_for_visit=clinical.chief_complaint_or_reason_for_visit or None,
            procedures=[procedure.procedure_description for procedure in summary.procedures_performed],
            billable_add_ons=[_humanize(add_on) for add_on in summary.possible_billable_add_ons],
            referral=(
                ReferralDigest(
                    requester=_REQUESTER_LABELS.get(referral.requester_role) if referral.requester_role else None,
                    reason=referral.reason_for_referral,
                )
                if referral.present
                else None
            ),
            open_questions=list(summary.notes_uncertain_items),
        )

    def from_stored(self, result_json: dict[str, Any]) -> ConsultationDigest | None:
        """A stored summary's digest; None for one stored under an older summary schema."""
        try:
            summary = ConsultationSummaryResult.model_validate(result_json)
        except ValidationError:
            return None
        return self.build(summary)


def _humanize(token: str) -> str:
    """The model's snake_case add-on (`deplacement_urgence`) as a label ("Deplacement urgence")."""
    text = " ".join(token.replace("_", " ").split())
    return text[:1].upper() + text[1:]

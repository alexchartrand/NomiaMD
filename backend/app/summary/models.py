"""Result model for the consultation_summary task.

Field types plus each field's `description=` (extraction guidance for the LLM) and
`json_schema_extra={"fr_label": ...}` (French label for rendering) are the single source
of truth this task's schema/prompt/renderer are all derived from — see app/tasks/schema.py
(generic, shared across tasks) and app/summary/task.py."""

from typing import Literal

from pydantic import BaseModel, Field

RequesterRole = Literal[
    "medecin_omnipraticien",
    "medecin_specialiste",
    "dentiste",
    "optometriste",
    "sage_femme",
    "autre_professionnel",
]

SingleVsMultiSystem = Literal["single", "multi", "incertain"]

AnesthesiaUsed = Literal["local", "régional", "général", "aucun", "pas_mentionné"]

DiagnosticOrTherapeutic = Literal["diagnostique", "thérapeutique", "les_deux", "incertain"]

Trimester = Literal["premier", "deuxième", "troisième", "incertain"]


class PregnancyContext(BaseModel):
    present: bool = Field(json_schema_extra={"fr_label": "Grossesse"})
    trimester: Trimester | None = Field(default=None, json_schema_extra={"fr_label": "Trimestre de grossesse"})


class EncounterSetting(BaseModel):
    location_detail: str | None = Field(
        default=None,
        description="Free text if stated, e.g. clinic name, ward, 'patient's home' — else null",
        json_schema_extra={"fr_label": "Lieu (détail)"},
    )
    date: str | None = Field(
        default=None,
        description=(
            "ISO 8601 date (YYYY-MM-DD) if the note states one — convert French dates such as "
            "'10 février 2026' to 2026-02-10; else null"
        ),
        json_schema_extra={"fr_label": "Date"},
    )
    time_start: str | None = Field(
        default=None, description="HH:MM if stated, else null", json_schema_extra={"fr_label": "Heure de début"}
    )
    time_end: str | None = Field(
        default=None, description="HH:MM if stated, else null", json_schema_extra={"fr_label": "Heure de fin"}
    )
    duration_minutes: float | None = Field(
        default=None,
        description=(
            "May be estimated from context if not explicitly stated — see "
            "duration_explicitly_stated, or null if there's no basis to estimate it"
        ),
        json_schema_extra={"fr_label": "Durée (minutes)"},
    )
    duration_explicitly_stated: bool = Field(
        description="Whether duration_minutes was explicitly stated by the transcript vs. estimated from context",
        json_schema_extra={"fr_label": "Durée déclarée explicitement"},
    )
    appointment_type: str | None = Field(       
        description=(
            "Type of appointment if stated. e.g.: sans rendez-vous, avec rendez-vous, urgence "
        ),
        json_schema_extra={"fr_label": "Rendez-vous"})


class ReferralInformation(BaseModel):
    present: bool = Field(json_schema_extra={"fr_label": "Référence"})
    requester_role: RequesterRole | None = Field(
        default=None, json_schema_extra={"fr_label": "Demandeur (rôle)"}
    )
    requester_identifier_mentioned: str | None = Field(
        default=None,
        description="Verbatim name/number if stated, else null",
        json_schema_extra={"fr_label": "Demandeur (identifiant)"},
    )
    reason_for_referral: str | None = Field(
        default=None,
        description="Short paraphrase, else null",
        json_schema_extra={"fr_label": "Motif de la référence"},
    )
    written_report_back_required_or_produced: bool | None = Field(
        default=None, json_schema_extra={"fr_label": "Rapport écrit requis/produit"}
    )


class ClinicalSummary(BaseModel):
    chief_complaint_or_reason_for_visit: str = Field(
        description="Short paraphrase", json_schema_extra={"fr_label": "Motif de consultation"}
    )
    systems_or_body_regions_involved: list[str] = Field(
        default_factory=list,
        description="e.g. respiratoire, genou_droit, peau",
        json_schema_extra={"fr_label": "Systèmes/régions concernés"},
    )
    single_vs_multi_system: SingleVsMultiSystem = Field(
        json_schema_extra={"fr_label": "Système unique ou multiple"}
    )
    history_taken: bool | None = Field(default=None, json_schema_extra={"fr_label": "Anamnèse effectuée"})
    new_treatment_initiated: bool | None = Field(
        default=None, json_schema_extra={"fr_label": "Nouveau traitement amorcé"}
    )
    existing_treatment_reviewed_or_adjusted: bool | None = Field(
        default=None, json_schema_extra={"fr_label": "Traitement existant révisé"}
    )
    diagnosis_or_impression_stated: str | None = Field(
        default=None,
        description="Short paraphrase, else null",
        json_schema_extra={"fr_label": "Diagnostic/impression"},
    )
    recommendations_given_to_patient: bool | None = Field(
        default=None, json_schema_extra={"fr_label": "Recommandations données au patient"}
    )
    orders_or_prescriptions_mentioned: bool | None = Field(
        default=None, json_schema_extra={"fr_label": "Ordonnances/tests mentionnés"}
    )


class PhysicalExamination(BaseModel):
    performed: bool | None = Field(default=None, json_schema_extra={"fr_label": "Examen physique effectué"})
    regions_or_systems_examined: list[str] = Field(
        default_factory=list,
        description="e.g. cou, thorax, abdomen, fond_oeil, gynécologique, psychiatrique",
        json_schema_extra={"fr_label": "Régions examinées"},
    )
    notable_findings: str | None = Field(
        default=None,
        description="Short paraphrase if stated, else null",
        json_schema_extra={"fr_label": "Constatations"},
    )


class ProcedurePerformed(BaseModel):
    procedure_description: str = Field(
        description="Plain language, e.g. 'suture of 3cm laceration', 'joint injection', 'ECG performed and interpreted'",
        json_schema_extra={"fr_label": "Description"},
    )
    body_site: str | None = Field(
        default=None, description="Free text or null", json_schema_extra={"fr_label": "Site"}
    )
    technique_or_approach_mentioned: str | None = Field(
        default=None, description="Free text or null", json_schema_extra={"fr_label": "Technique/approche"}
    )
    anesthesia_used: AnesthesiaUsed = Field(json_schema_extra={"fr_label": "Anesthésie"})
    diagnostic_or_therapeutic: DiagnosticOrTherapeutic = Field(
        json_schema_extra={"fr_label": "Diagnostique ou thérapeutique"}
    )


class ConsultationSummaryResult(BaseModel):
    """A structured summary of a clinical encounter's RAMQ-relevant facts (setting,
    pregnancy context, referral, clinical/exam content) for physician review — never a
    billing code itself;
    that's resolved downstream by the rules engine against administrative facts not present
    in the transcript. Carries no patient-identity fields: the physician picks the patient
    before extraction runs (see app/extraction/pipeline.py), and that patient's
    administrative facts (registration/vulnerability/age) reach billing_codes separately via
    BillingContext, never re-extracted from the transcript here."""

    short_description: str = Field(
        description=(
            "1-3 sentence plain-language summary of what happened in this encounter, "
            "written for a biller who has not read the transcript"
        ),
        json_schema_extra={"fr_label": "Résumé"},
    )
    encounter_setting: EncounterSetting
    pregnancy_context: PregnancyContext
    referral_information: ReferralInformation
    clinical_summary: ClinicalSummary
    physical_examination: PhysicalExamination
    procedures_performed: list[ProcedurePerformed] = Field(
        default_factory=list, json_schema_extra={"fr_label": "Acte réalisé"}
    )
    possible_billable_add_ons: list[str] = Field(
        default_factory=list,
        description=(
            "e.g. deplacement_urgence, frais_kilometrage, communication_specialiste, "
            "plateau_chirurgie — only if clearly evidenced in transcript, not inferred"
        ),
        json_schema_extra={"fr_label": "Ajouts possiblement facturables"},
    )
    notes_uncertain_items: list[str] = Field(
        default_factory=list,
        description=(
            "Anything the model could not determine confidently, phrased as a specific "
            "question for the physician to resolve"
        ),
        json_schema_extra={"fr_label": "Élément incertain"},
    )

from typing import Any

from app.models import ConsultationSummaryResult
from app.tasks.base import ExtractionTask

SYSTEM_PROMPT = """\
You are a clinical documentation parser for RAMQ billing preparation in Quebec.
Your ONLY job is to extract structured facts from a medical consultation
transcript or note. You do NOT decide or output a billing code. RAMQ codes
depend on administrative facts (patient registration status, panel size,
exact billing context, prior billing history) that are not present in the
transcript, and are resolved separately by a rules engine against the RAMQ
tariff manual (Manuel des médecins omnipraticiens — Rémunération à l'acte).

Output strict JSON matching the schema below. No prose, no markdown, no
commentary outside the JSON object. If a field cannot be determined from the
transcript, use null (or false/empty list as appropriate) — never guess.

All free-text values in the output (short_description, rationale, notable_findings,
chief_complaint_or_reason_for_visit, notes_uncertain_items, and any other
free-text paraphrase or description field) must be written in French. JSON
keys and enum values (e.g. "high"/"medium"/"low", "single"/"multi",
"cabinet"/"domicile"/etc.) remain exactly as specified in the schema — do not
translate keys or enum values, only free-text content.

============================================================
OUTPUT SCHEMA
============================================================

{
  "short_description": "<1-3 sentence plain-language summary of what happened in this encounter, written for a biller who has not read the transcript>",

  "encounter_setting": {
    "location_type": "cabinet | domicile | urgence | clsc | chsld | centre_readaptation | hopital_soins_courte_duree | hopital_soins_longue_duree | telemedecine | inconnu",
    "location_detail": "<free text if stated, e.g. clinic name, ward, 'patient's home' — else null>",
    "date": "<ISO date if stated, else null>",
    "time_start": "<HH:MM if stated, else null>",
    "time_end": "<HH:MM if stated, else null>",
    "duration_minutes": <number or null>,
    "duration_explicitly_stated": true | false,
    "appointment_type": "sur_rendez_vous | sans_rendez_vous_acces_adapte | inconnu"
  },

  "patient_information": {
    "age_years": <number or null>,
    "age_months_if_infant": <number or null>,
    "sex_if_stated": "<free text or null>",
    "pregnancy_context": {
      "present": true | false,
      "trimester": "first | beyond_first | unclear | null"
    },
    "relevant_vulnerability_or_context_mentioned": ["<free text, e.g. perte_severe_autonomie, soins_palliatifs, sante_mentale, toxicomanie — only if explicitly evidenced, not inferred>"],
    "new_or_established_patient_language": "<verbatim or paraphrase of anything transcript says about whether patient is new/registered/followed by this physician — else null>"
  },

  "referral_information": {
    "present": true | false,
    "referral_type": "consultation_ecrite | reference_traitement | demande_opinion_verbale | aucune | inconnu",
    "requester_role": "medecin_omnipraticien | medecin_specialiste | dentiste | optometriste | sage_femme | autre_professionnel | null",
    "requester_identifier_mentioned": "<verbatim name/number if stated, else null>",
    "reason_for_referral": "<short paraphrase, else null>",
    "written_report_back_required_or_produced": true | false | null
  },

  "clinical_summary": {
    "chief_complaint_or_reason_for_visit": "<short paraphrase>",
    "systems_or_body_regions_involved": ["<free text, e.g. respiratoire, genou_droit, peau>"],
    "single_vs_multi_system": "single | multi | unclear",
    "history_taken": true | false | null,
    "new_treatment_initiated": true | false | null,
    "existing_treatment_reviewed_or_adjusted": true | false | null,
    "diagnosis_or_impression_stated": "<short paraphrase, else null>",
    "recommendations_given_to_patient": true | false | null,
    "orders_or_prescriptions_mentioned": true | false | null
  },

  "physical_examination": {
    "performed": true | false | null,
    "regions_or_systems_examined": ["<free text, e.g. cou, thorax, abdomen, fond_oeil>"],
    "special_exam_type": ["gynecologique | ophtalmologique | articulaire_avec_evaluation_fonction | psychiatrique_semiologique | evaluation_fonctions_mentales_superieures | autre_or_null — list all that apply, empty list if none"],
    "notable_findings": "<short paraphrase if stated, else null>"
  },

  "procedures_performed": [
    {
      "procedure_description": "<plain language, e.g. 'suture of 3cm laceration', 'joint injection', 'ECG performed and interpreted'>",
      "body_site": "<free text or null>",
      "technique_or_approach_mentioned": "<free text or null>",
      "anesthesia_used": "<local | regional | general | none | not_stated>",
      "diagnostic_or_therapeutic": "diagnostic | therapeutique | both | unclear"
    }
  ],

  "encounter_category_hint": {
    "best_guess_category": "visite_suivi_ou_prise_en_charge | visite_ponctuelle | consultation_formelle | examen_complet_ou_majeur | intervention_clinique_longue | acte_diagnostique_ou_therapeutique | chirurgie | psychotherapie | constatation_deces | communication_professionnelle_seule | autre_ou_indetermine",
      "confidence": "high | medium | low",
      "rationale": "<one sentence explaining why, referencing what's in the transcript>"
  },

  "possible_billable_add_ons": ["<e.g. deplacement_urgence, frais_kilometrage, communication_specialiste, plateau_chirurgie — only if clearly evidenced in transcript, not inferred>"],

  "notes_uncertain_items": ["<anything the model could not determine confidently, phrased as a specific question for the physician to resolve>"]
}

============================================================
RULES
============================================================
1. Never guess administrative facts not derivable from clinical content:
   patient registration/"inscrit" status with a specific physician,
   vulnerability designation (this is a formal RAMQ status, not a clinical
   impression), physician panel size, prior billing history this calendar
   year. Extract only what the transcript actually documents or states, and
   leave everything else null/false for the downstream rules engine.
2. "encounter_category_hint" is a hint only, to help route the note to the
   right section of the tariff manual. It is explicitly NOT a billing code
   and must never be treated as one downstream.
3. Distinguish clearly between things the transcript explicitly states
   (set the field) and things you would need to infer or assume (leave null
   and add a note instead).
4. If duration is not explicitly stated, you may estimate it from context
   in duration_minutes, but duration_explicitly_stated must be false, and add
   a note.
5. procedures_performed should be an empty list if no procedure beyond
   history-taking/examination occurred.
6. Output valid JSON only, matching the schema exactly. No text before or
   after the JSON object.
7. Write all free-text field values in French (Québécois medical French is
   fine). Do not translate JSON field names or the fixed enum values defined
   in the schema."""


def _bool_fr(value: bool | None) -> str | None:
    if value is None:
        return None
    return "oui" if value else "non"


def _joined(items: list[str]) -> str | None:
    return ", ".join(items) if items else None


def render_for_billing_codes(result: ConsultationSummaryResult) -> str:
    """Renders a ConsultationSummaryResult back into a single French text blob — this,
    not the raw transcript, is what billing_codes.py sends to the model (both for RAMQ
    candidate retrieval and as the text its supporting_quote must be grounded in). Using
    the already-extracted, denser summary instead of a long freeform dictation is the
    point of the two-stage pipeline (app/extraction/pipeline.py): it retrieves RAMQ
    candidates more reliably and grounds the billing model's reasoning in facts already
    pulled out once, rather than re-reading the whole transcript. Every line here mirrors
    a field from the schema in this file's SYSTEM_PROMPT, so a quote sourced from this text
    is traceable straight back to a specific extracted fact. Empty/null fields are omitted
    rather than printed as "null" — a missing line reads as "not established" the same way
    a null does in the JSON.
    """
    lines: list[str] = [f"Résumé: {result.short_description}"]

    setting = result.encounter_setting
    setting_bits = [f"lieu: {setting.location_type}", f"rendez-vous: {setting.appointment_type}"]
    if setting.location_detail:
        setting_bits.append(setting.location_detail)
    if setting.duration_minutes is not None:
        stated = "déclarée" if setting.duration_explicitly_stated else "estimée"
        setting_bits.append(f"durée {stated}: {setting.duration_minutes} min")
    lines.append(f"Contexte de la visite: {'; '.join(setting_bits)}")

    patient = result.patient_information
    patient_bits = []
    if patient.age_years is not None:
        patient_bits.append(f"{patient.age_years} ans")
    if patient.age_months_if_infant is not None:
        patient_bits.append(f"{patient.age_months_if_infant} mois")
    if patient.sex_if_stated:
        patient_bits.append(patient.sex_if_stated)
    if patient.new_or_established_patient_language:
        patient_bits.append(patient.new_or_established_patient_language)
    if patient_bits:
        lines.append(f"Patient: {'; '.join(patient_bits)}")
    if patient.pregnancy_context.present:
        trimester = patient.pregnancy_context.trimester or "inconnu"
        lines.append(f"Grossesse: en cours, trimestre {trimester}")
    vulnerability = _joined(patient.relevant_vulnerability_or_context_mentioned)
    if vulnerability:
        lines.append(f"Contexte/vulnérabilité mentionnée: {vulnerability}")

    referral = result.referral_information
    if referral.present:
        referral_bits = [f"type: {referral.referral_type}"]
        if referral.requester_role:
            referral_bits.append(f"demandeur: {referral.requester_role}")
        if referral.requester_identifier_mentioned:
            referral_bits.append(referral.requester_identifier_mentioned)
        if referral.reason_for_referral:
            referral_bits.append(f"motif: {referral.reason_for_referral}")
        lines.append(f"Référence: {'; '.join(referral_bits)}")

    clinical = result.clinical_summary
    lines.append(f"Motif de consultation: {clinical.chief_complaint_or_reason_for_visit}")
    systems = _joined(clinical.systems_or_body_regions_involved)
    if systems:
        lines.append(f"Systèmes/régions concernés ({clinical.single_vs_multi_system}): {systems}")
    if clinical.diagnosis_or_impression_stated:
        lines.append(f"Diagnostic/impression: {clinical.diagnosis_or_impression_stated}")
    treatment_bits = []
    if clinical.new_treatment_initiated is not None:
        treatment_bits.append(f"nouveau traitement: {_bool_fr(clinical.new_treatment_initiated)}")
    if clinical.existing_treatment_reviewed_or_adjusted is not None:
        treatment_bits.append(
            f"traitement existant révisé: {_bool_fr(clinical.existing_treatment_reviewed_or_adjusted)}"
        )
    if clinical.orders_or_prescriptions_mentioned is not None:
        treatment_bits.append(
            f"ordonnances/tests mentionnés: {_bool_fr(clinical.orders_or_prescriptions_mentioned)}"
        )
    if treatment_bits:
        lines.append(f"Suivi thérapeutique: {'; '.join(treatment_bits)}")

    exam = result.physical_examination
    if exam.performed:
        exam_bits = []
        regions = _joined(exam.regions_or_systems_examined)
        if regions:
            exam_bits.append(f"régions examinées: {regions}")
        special = _joined(exam.special_exam_type)
        if special:
            exam_bits.append(f"type d'examen spécial: {special}")
        lines.append(f"Examen physique: {'; '.join(exam_bits) if exam_bits else 'effectué'}")
        if exam.notable_findings:
            lines.append(f"Constatations: {exam.notable_findings}")

    for procedure in result.procedures_performed:
        proc_bits = [procedure.procedure_description]
        if procedure.body_site:
            proc_bits.append(procedure.body_site)
        if procedure.technique_or_approach_mentioned:
            proc_bits.append(procedure.technique_or_approach_mentioned)
        proc_bits.append(f"anesthésie: {procedure.anesthesia_used}")
        proc_bits.append(procedure.diagnostic_or_therapeutic)
        lines.append(f"Acte réalisé: {' — '.join(proc_bits)}")

    hint = result.encounter_category_hint
    lines.append(
        f"Catégorie probable (indicatif seulement, ne pas traiter comme un code de "
        f"facturation): {hint.best_guess_category} (confiance {hint.confidence}) — {hint.rationale}"
    )

    add_ons = _joined(result.possible_billable_add_ons)
    if add_ons:
        lines.append(f"Ajouts possiblement facturables: {add_ons}")

    for note in result.notes_uncertain_items:
        lines.append(f"Élément incertain: {note}")

    return "\n".join(lines)


class ConsultationSummaryTask(ExtractionTask):
    name = "consultation_summary"

    def build_prompt(self, transcript: str) -> tuple[str, str]:
        return SYSTEM_PROMPT, f"Transcript:\n{transcript}\n\nExtract the structured facts per your instructions."

    def json_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "short_description": {"type": "string"},
                "encounter_setting": {
                    "type": "object",
                    "properties": {
                        "location_type": {
                            "type": "string",
                            "enum": [
                                "cabinet",
                                "domicile",
                                "urgence",
                                "clsc",
                                "chsld",
                                "centre_readaptation",
                                "hopital_soins_courte_duree",
                                "hopital_soins_longue_duree",
                                "telemedecine",
                                "inconnu",
                            ],
                        },
                        "location_detail": {"type": ["string", "null"]},
                        "date": {"type": ["string", "null"]},
                        "time_start": {"type": ["string", "null"]},
                        "time_end": {"type": ["string", "null"]},
                        "duration_minutes": {"type": ["number", "null"]},
                        "duration_explicitly_stated": {"type": "boolean"},
                        "appointment_type": {
                            "type": "string",
                            "enum": ["sur_rendez_vous", "sans_rendez_vous_acces_adapte", "inconnu"],
                        },
                    },
                    "required": [
                        "location_type",
                        "location_detail",
                        "date",
                        "time_start",
                        "time_end",
                        "duration_minutes",
                        "duration_explicitly_stated",
                        "appointment_type",
                    ],
                    "additionalProperties": False,
                },
                "patient_information": {
                    "type": "object",
                    "properties": {
                        "age_years": {"type": ["number", "null"]},
                        "age_months_if_infant": {"type": ["number", "null"]},
                        "sex_if_stated": {"type": ["string", "null"]},
                        "pregnancy_context": {
                            "type": "object",
                            "properties": {
                                "present": {"type": "boolean"},
                                "trimester": {
                                    "type": ["string", "null"],
                                    "enum": ["first", "beyond_first", "unclear", None],
                                },
                            },
                            "required": ["present", "trimester"],
                            "additionalProperties": False,
                        },
                        "relevant_vulnerability_or_context_mentioned": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "new_or_established_patient_language": {"type": ["string", "null"]},
                    },
                    "required": [
                        "age_years",
                        "age_months_if_infant",
                        "sex_if_stated",
                        "pregnancy_context",
                        "relevant_vulnerability_or_context_mentioned",
                        "new_or_established_patient_language",
                    ],
                    "additionalProperties": False,
                },
                "referral_information": {
                    "type": "object",
                    "properties": {
                        "present": {"type": "boolean"},
                        "referral_type": {
                            "type": "string",
                            "enum": [
                                "consultation_ecrite",
                                "reference_traitement",
                                "demande_opinion_verbale",
                                "aucune",
                                "inconnu",
                            ],
                        },
                        "requester_role": {
                            "type": ["string", "null"],
                            "enum": [
                                "medecin_omnipraticien",
                                "medecin_specialiste",
                                "dentiste",
                                "optometriste",
                                "sage_femme",
                                "autre_professionnel",
                                None,
                            ],
                        },
                        "requester_identifier_mentioned": {"type": ["string", "null"]},
                        "reason_for_referral": {"type": ["string", "null"]},
                        "written_report_back_required_or_produced": {"type": ["boolean", "null"]},
                    },
                    "required": [
                        "present",
                        "referral_type",
                        "requester_role",
                        "requester_identifier_mentioned",
                        "reason_for_referral",
                        "written_report_back_required_or_produced",
                    ],
                    "additionalProperties": False,
                },
                "clinical_summary": {
                    "type": "object",
                    "properties": {
                        "chief_complaint_or_reason_for_visit": {"type": "string"},
                        "systems_or_body_regions_involved": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "single_vs_multi_system": {
                            "type": "string",
                            "enum": ["single", "multi", "unclear"],
                        },
                        "history_taken": {"type": ["boolean", "null"]},
                        "new_treatment_initiated": {"type": ["boolean", "null"]},
                        "existing_treatment_reviewed_or_adjusted": {"type": ["boolean", "null"]},
                        "diagnosis_or_impression_stated": {"type": ["string", "null"]},
                        "recommendations_given_to_patient": {"type": ["boolean", "null"]},
                        "orders_or_prescriptions_mentioned": {"type": ["boolean", "null"]},
                    },
                    "required": [
                        "chief_complaint_or_reason_for_visit",
                        "systems_or_body_regions_involved",
                        "single_vs_multi_system",
                        "history_taken",
                        "new_treatment_initiated",
                        "existing_treatment_reviewed_or_adjusted",
                        "diagnosis_or_impression_stated",
                        "recommendations_given_to_patient",
                        "orders_or_prescriptions_mentioned",
                    ],
                    "additionalProperties": False,
                },
                "physical_examination": {
                    "type": "object",
                    "properties": {
                        "performed": {"type": ["boolean", "null"]},
                        "regions_or_systems_examined": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "special_exam_type": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "gynecologique",
                                    "ophtalmologique",
                                    "articulaire_avec_evaluation_fonction",
                                    "psychiatrique_semiologique",
                                    "evaluation_fonctions_mentales_superieures",
                                    "autre",
                                ],
                            },
                        },
                        "notable_findings": {"type": ["string", "null"]},
                    },
                    "required": [
                        "performed",
                        "regions_or_systems_examined",
                        "special_exam_type",
                        "notable_findings",
                    ],
                    "additionalProperties": False,
                },
                "procedures_performed": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "procedure_description": {"type": "string"},
                            "body_site": {"type": ["string", "null"]},
                            "technique_or_approach_mentioned": {"type": ["string", "null"]},
                            "anesthesia_used": {
                                "type": "string",
                                "enum": ["local", "regional", "general", "none", "not_stated"],
                            },
                            "diagnostic_or_therapeutic": {
                                "type": "string",
                                "enum": ["diagnostic", "therapeutique", "both", "unclear"],
                            },
                        },
                        "required": [
                            "procedure_description",
                            "body_site",
                            "technique_or_approach_mentioned",
                            "anesthesia_used",
                            "diagnostic_or_therapeutic",
                        ],
                        "additionalProperties": False,
                    },
                },
                "encounter_category_hint": {
                    "type": "object",
                    "properties": {
                        "best_guess_category": {
                            "type": "string",
                            "enum": [
                                "visite_suivi_ou_prise_en_charge",
                                "visite_ponctuelle",
                                "consultation_formelle",
                                "examen_complet_ou_majeur",
                                "intervention_clinique_longue",
                                "acte_diagnostique_ou_therapeutique",
                                "chirurgie",
                                "psychotherapie",
                                "constatation_deces",
                                "communication_professionnelle_seule",
                                "autre_ou_indetermine",
                            ],
                        },
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "rationale": {"type": "string"},
                    },
                    "required": ["best_guess_category", "confidence", "rationale"],
                    "additionalProperties": False,
                },
                "possible_billable_add_ons": {"type": "array", "items": {"type": "string"}},
                "notes_uncertain_items": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "short_description",
                "encounter_setting",
                "patient_information",
                "referral_information",
                "clinical_summary",
                "physical_examination",
                "procedures_performed",
                "encounter_category_hint",
                "possible_billable_add_ons",
                "notes_uncertain_items",
            ],
            "additionalProperties": False,
        }

    def parse(self, raw: dict[str, Any]) -> ConsultationSummaryResult:
        return ConsultationSummaryResult.model_validate(raw)

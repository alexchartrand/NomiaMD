"""The visit query: what kind of encounter this was, never what it was about.

A visit code (section B of the manual) is chosen by the encounter's form — where it took
place, with or without an appointment, a consultation requested by another physician, a
pregnancy visit — and by the administrative facts the eligibility prefilter already applies.
The clinical content (complaint, diagnosis, findings, body regions) is what the procedure
and overview queries search with; in the visit query it only pulls the search toward
same-topic procedures (a depression follow-up retrieving psychiatric exams, a knee problem
retrieving knee surgery) and away from the visit codes, whose text never mentions it.

So the query is rendered from the encounter's form alone, and searched within section B
only (VISIT_SECTION_PREFIX)."""

from app.summary.models import ConsultationSummaryResult

# The visit section's `header_path` root, as ramq-ingestion writes it for the omnipraticien
# manual. Coupled to that format by design (the repos share no code): if a regenerated
# codes table renames the section, the visit query finds nothing and the benchmark shows it.
VISIT_SECTION_PREFIX = "B — Consultation, examen et visite"

# How the omnipraticien manual words a visit made at another physician's request: an
# "évaluation … pour donner une opinion" (08777, 15790, …), not a "consultation" — whose
# codes the word pulls in instead. Who asked isn't rendered: the requester's role words
# ("médecin omnipraticien") only match the consultation codes again.
_REFERRED_VISIT_FR = "Visite d'évaluation pour donner une opinion"

_SYSTEMS_FR = {"single": "Un seul système", "multi": "Plusieurs systèmes"}


class VisitQueryRenderer:
    def render(self, summary: ConsultationSummaryResult) -> str:
        setting = summary.encounter_setting
        parts = [self._kind(summary)]
        parts += [value for value in (setting.appointment_type, setting.location_detail) if value]

        pregnancy = summary.pregnancy_context
        if pregnancy.present:
            known_trimester = pregnancy.trimester and pregnancy.trimester != "incertain"
            parts.append(f"Grossesse, {pregnancy.trimester} trimestre" if known_trimester else "Grossesse")

        systems = _SYSTEMS_FR.get(summary.clinical_summary.single_vs_multi_system)
        if systems:
            parts.append(systems)

        if setting.duration_explicitly_stated and setting.duration_minutes is not None:
            parts.append(f"Durée {round(setting.duration_minutes)} minutes")

        return ". ".join(parts)

    @staticmethod
    def _kind(summary: ConsultationSummaryResult) -> str:
        return _REFERRED_VISIT_FR if summary.referral_information.present else "Visite"

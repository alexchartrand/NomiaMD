# consultations/

20 synthetic French-language family-medicine (médecine familiale) consultation notes,
written in the same freeform clinical-note style as the root-level
`notes_consultation_simulees.md`. Generated as a candidate eval set for RAMQ
billing-code extraction — see the "Wiring this in" section below before assuming
anything here is already connected to the app.

All patients, physicians, clinics, and clinical details are entirely fictional.

## Contents

- `01_hta_prise_en_charge.md` … `20_cessation_tabagique_suivi.md` — one consultation
  note per file, for browsing/reading individually.
- `all_notes.md` — the same 20 notes concatenated into a single file, in the
  `## NOTE <n>` section format that `backend/app/sample_patients.py` parses
  (identical format to `notes_consultation_simulees.md`).
- `eval_labels.jsonl` — one entry per note with a best-effort candidate RAMQ code
  guess, in the same schema as `backend/tests/fixtures/eval_billing_codes.jsonl`.

## Scope and diversity

Family-doctor (omnipraticien) encounters only, matching this repo's current RAMQ
scope (see root `README.md`). Two fictional clinics (Clinique médicale Les Tilleuls,
a cabinet privé; GMF Boisé-des-Cèdres, a groupe de médecine de famille) and one
telemedicine encounter, across six fictional physicians. Ages span 18 months to 88
years and include: chronic disease management (HTA, dyslipidemia, diabetes),
pregnancy (first-trimester intake and third-trimester follow-up), pediatrics (well-child
visit, acute otitis), musculoskeletal (acute low back pain, shoulder tendinopathy
follow-up, second-opinion knee osteoarthritis), a suspicious-lesion opinion visit, a
complex multi-system opinion visit, mental health (new GAD intake, depression
follow-up), geriatrics/home care (a home visit for severe loss of autonomy, a periodic
visit for a vulnerable inscribed patient), a periodic exam for a 70-79-year-old, an
interpreter-assisted visit, an inter-professional specialist-communication note, and a
telederm video consultation.

## RAMQ code labels — read before trusting them

`eval_labels.jsonl`'s `expected_codes` are **not verified by a physician or RAMQ
billing expert**. This session cross-referenced each note against the descriptions in
the persisted 101-code vector corpus (`backend/app/ramq/vector/`) and picked the
most plausible-sounding code, but picking correct RAMQ codes requires billing
expertise this session doesn't have — see `label_notes` on each entry for the specific
reasoning and open ambiguities (panel-size splits, vulnerability-status judgment calls,
near-duplicate code families whose actual distinction isn't recoverable from the
corpus's parsed text). One entry (`CLI-2026-01230`) is marked `needs_physician_label`
outright rather than guessed, because the three candidate codes were textually
indistinguishable in the corpus. Treat every `draft-unverified` entry as a starting
point for a physician/billing-literate reviewer, not as ground truth — same caveat
that already applies to the existing entries in
`backend/tests/fixtures/eval_billing_codes.jsonl`.

## Wiring this in (not done automatically)

Nothing in this folder is referenced by the running app yet — creating it here (as
requested) rather than editing tracked app files was a deliberate choice, since that
touches existing pipeline configuration and fixtures. To actually use these:

- **As selectable sample patients / pipeline input:** set
  `SAMPLE_PATIENTS_PATH=consultations/all_notes.md` (see root `README.md`'s note on
  `notes_consultation_simulees.md`) — or merge `all_notes.md`'s sections into the root
  file if you want both sets available together under the default path.
- **As eval fixtures:** merge `eval_labels.jsonl`'s lines into
  `backend/tests/fixtures/eval_billing_codes.jsonl`. Note `scripts/eval_extraction.py`
  looks up each `patient_id` via `get_sample_patient()`, which only sees whatever file
  `SAMPLE_PATIENTS_PATH` currently points at — so the sample-patients wiring above has
  to happen too, or these patient IDs won't resolve.

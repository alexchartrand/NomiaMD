# consultations/

25 synthetic French-language consultation notes, one per file — 20 family-medicine
(médecine familiale) notes plus 5 urgence/médecine-familiale notes originally at the
repo root as `notes_consultation_simulees.md`. All patients, physicians, clinics, and
clinical details are entirely fictional.

This is the default source for `backend/app/sample_patients.py` — every `.md` file here
except `README.md` is loaded as a selectable "simulated patient" (`GET /patients`,
`GET /patients/{id}`), one note per file. See root `README.md`.

## Contents

- `01_hta_prise_en_charge.md` … `25_fatigue_depression_suivi.md` — one consultation
  note per file.
- `eval_labels.jsonl` — one entry per note (notes 1-20 only) with a best-effort
  candidate RAMQ code guess, in the same schema as
  `backend/tests/fixtures/eval_billing_codes.jsonl`. Not yet merged into that fixture —
  see "RAMQ code labels" below before doing so.

## Scope and diversity

Family-doctor (omnipraticien) encounters only, matching this repo's current RAMQ
scope (see root `README.md`). Two fictional clinics (Clinique médicale Les Tilleuls,
a cabinet privé; GMF Boisé-des-Cèdres, a groupe de médecine de famille), a CHU
urgence, and one telemedicine encounter, across physicians. Ages span 18 months to 88
years and include: chronic disease management (HTA, dyslipidemia, diabetes),
pregnancy (first-trimester intake and third-trimester follow-up), pediatrics (well-child
visit, acute otitis, pediatric appendicitis), musculoskeletal (acute low back pain,
shoulder tendinopathy follow-up, second-opinion knee osteoarthritis), a
suspicious-lesion opinion visit, a complex multi-system opinion visit, mental health
(new GAD intake, depression follow-up), geriatrics/home care (a home visit for severe
loss of autonomy, a periodic visit for a vulnerable inscribed patient), a periodic exam
for a 70-79-year-old, an interpreter-assisted visit, an inter-professional
specialist-communication note, a telederm video consultation, and urgence cases (STEMI,
hand laceration/suture, pediatric appendicitis).

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

To use these as eval fixtures, merge `eval_labels.jsonl`'s lines into
`backend/tests/fixtures/eval_billing_codes.jsonl` (patient IDs already resolve via
`get_sample_patient()` since this directory is the default sample-patients source).

# consultations/

58 synthetic French-language consultation notes, one per file. All patients, physicians,
clinics and clinical details are entirely fictional.

This is the default source for `backend/app/sample_patients/`: every `.md` file here
except `README.md` is loaded as a selectable "simulated patient", one note per file, and
`backend/scripts/seed_db.py` seeds one patient + encounter per note. See root `README.md`.

## Note format

A fixed header that the loaders parse (`**Label :** value` lines), then a free-form body:

- `**Clinique :**`, `**Service :**` or `**Établissement :**` — where the encounter happened
- `**Médecin :**`, `**Patient :**` (`Nom, Prénom — NN ans (H/F)`, optionally
  `, inscrit(e)` / `, non inscrit(e)` / `vulnérable`), `**NAM :**`, `**Dossier :**`
  (the sample's id), `**Date/heure :**` (`13 juillet 2026, 14h15`)
- `### Motif de consultation` (used for the inbox label)

`seed_db.py` seeds a patient as **not registered** with the demo physician when the
`**Patient :**` line says `non inscrit(e)`, and as **vulnérable** when the note contains
"vulnérable" (not preceded by "non "). Keep those words out of notes where they don't apply.

The body deliberately varies like real notes do: full templates (HMA / ATCD / Rx / E/P /
Impression / Plan) only for intakes and admissions, terse S/O/A/P follow-ups without
ATCD or Rx, ward-round and CHSLD notes full of abbreviations, ER notes with triage and
disposition, dictated prose.

## Coverage

| Notes | Content |
|---|---|
| 01-25 | Original set: cabinet (Clinique médicale Les Tilleuls), GMF Boisé-des-Cèdres, a CHU urgence, one video teleconsultation — mostly single-code visits |
| 26-35 | *Easy* (1 code): GMF/cabinet follow-ups (incl. vulnérable, 80+), walk-in non-registered, new-patient intake, CHSLD round, hospital ward round, ER exam, home visit (severe loss of autonomy), CLSC/GMF-U pregnancy follow-up (mixte) |
| 36-47 | *Medium* (2 codes or a look-alike trap): visit + office ECG / laceration repair / I&D / joint injection, psychotherapy (no visit), CHSLD admission + NIM, CHSLD evening call-out, ward admission and discharge, ER exam + repair, home visit + ECG, shared mental-health follow-up |
| 48-55 | *Hard* (3+ codes or rule traps): follow-up + mental status exam (one code), several cabinet procedures, night ER with an admitted patient, CHSLD phone order + death certification, vulnérable intake + interpreter, IUD insertion (includes the visit), ward hand-over + family meeting (mixte), ER complex-situation forfait |
| 56-58 | *Negatives* (no code): insurer form only, prescription renewal without a visit, no-show |

## RAMQ code labels — read before trusting them

Labels live in `backend/tests/fixtures/eval_billing_codes.jsonl` (the file
`backend/scripts/eval_extraction.py` reads by default), one entry per note, keyed by the
note's dossier number. Each carries the `physician_context` / `patient_context` facts the
eval feeds the eligibility filter (panel size, remuneration, age, registration,
vulnerability) — they're part of the label: the same note can have a different right
answer for a different physician.

**None of the draft labels is verified by a physician or billing expert** (only the
`reviewed` ones went through a review). They were picked on
2026-10-07 from the omnipraticien manual (rev. 2026-09-17, préambule général rules cited
in each `label_notes`) and the `codes_2026-09-17` table; notes 01-25 were re-audited the
same day (several original guesses were wrong — e.g. an under-80 code for an 88-year-old).

- `label_status: "draft-unverified"` — the manual text supports the label.
- `label_status: "to_review"` — a judgment call; `review_reason` says exactly what a
  physician needs to decide (walk-in vs scheduled, hospital unit level A/B, a designation…).
- `label_status: "reviewed"` — a `to_review` judgment call settled in a human review
  (2026-10-07); the decision and its reason close `label_notes`.
- `expected_codes: []` outside `needs_physician_label` is a real answer: nothing billable.

Known gaps in the codes table that affect these labels (ER codes wrongly requiring
registration, mislabelled vulnérable variants, missing surgical-tray supplements) are
logged in ramq-ingestion's `BACKLOG.md`; the app-side ones (no care-setting axis…) in
the root `BACKLOG.md`.

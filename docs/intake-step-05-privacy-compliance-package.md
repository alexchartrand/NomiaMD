# Step 05 — Privacy and compliance package

**Phase:** 1 → 3 (start week 1, must be done before the first real note) · **Depends on:** 06 for the purge job
**Plan section:** §1d, §3

## Goal
Have what Law 25 and every vendor or clinic will ask for before any real patient data arrives.

## Non-code tasks
- [ ] Name the person in charge of protecting personal information, and publish the
  governance policy.
- [ ] Engage privacy counsel. Questions to ask:
  - Does the *Loi sur les renseignements de santé et de services sociaux* apply to private GMFs?
  - Is NomiaMD a *mandataire* of the clinic?
  - What patient consent is needed (if any) for using a note to bill?
- [ ] An ÉFVP (privacy impact assessment) template for NomiaMD, reusable for each clinic and partner.
- [ ] A service agreement (*mandataire*) template for clinics.
- [ ] An incident register and a breach-response procedure.
- [ ] A security questionnaire answer pack: hosting (Canada), encryption, access control,
  logging. Note where SOC 2 is on the roadmap.
- [x] Decide the **retention period** for note text (10/30): 180 days after the visit, and at least a
  year after the last change to its claim. Confirm it with counsel and the clinics.

## Code tasks (land after step 06)
- [x] Retention periods defined once in config (`RETENTION_*`, `app/retention/policy.py`). The
  due date is derived, not stored (`purge_after` was dropped): it moves whenever a claim is billed again.
- [x] Retention job (worker cron from step 10, `app/retention/`): instead of deleting encounters,
  it scrubs their clinical text (the note, the summary, the quotes and analysis of the code
  selection) and keeps the encounter, its codes, claims and bills, so RAMQ follow-ups and the
  year-end report still work. Re-importing the note restores it. The same job deletes audit
  events after a year and rolls `llm_calls` up into daily totals after 90 days.
- [ ] Decide on NAM encryption at rest (BACKLOG 🟢 item). Implement it if counsel or the clinics
  require it.

## Done when
- Counsel's answers are recorded in this file.
- Templates exist (they can live outside the repo; link them here).
- [x] The retention job is tested (`backend/tests/test_retention.py`): an expired note's text is
  gone, its codes and claim survive with their audit fields.
- [x] The BACKLOG retention item is checked off.

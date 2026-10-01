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
- [ ] Decide the **retention period** for note text, and record it in BACKLOG.md's 🔴 retention item.

## Code tasks (land after step 06)
- [ ] Set `encounters.purge_after` at creation (`service_date` + retention period, with the
  period defined once in config).
- [ ] Purge job (worker cron from step 10): delete encounters past `purge_after`. This cascades
  to runs and results; claims keep their snapshot and the audit fields (`source_note_hash`,
  `external_note_id`).
- [ ] Decide on NAM encryption at rest (BACKLOG 🟢 item). Implement it if counsel or the clinics
  require it.

## Done when
- Counsel's answers are recorded in this file.
- Templates exist (they can live outside the repo; link them here).
- The purge job is tested: an expired encounter is gone, its claim survives with its audit fields.
- The BACKLOG retention item is checked off.

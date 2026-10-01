# Step 04 — Partnerships kickoff (non-code)

**Phase:** 1, runs in the background from week 1 · **Depends on:** — · **Unblocks:** 13, 15, 19, 20, 21
**Plan section:** §1a–1d

## Goal
Start every slow-moving external process now, so approvals arrive when the code is ready.

## Tasks
- [ ] **Pilot clinic.** Recruit 1–2 GMFs, ideally on Omnimed or Medesync. Record: DMÉ and
  version, scribe used (if any), number of physicians, who signs agreements. Their DMÉ
  decides the first extension adapter (step 13).
- [ ] **Omnimed.** Contact Omnimed about joining the pre-billing partner integrations (the slot
  Xacte, FACNET and MultiD use). Ask for: the launch contract (parameters, signing),
  partner terms, any API for signed notes.
- [ ] **TELUS Health.** Apply to the EMR add-on/partner program. Ask whether the CHR
  Enterprise API (GraphQL) exposes **Medesync** clinics' signed notes, or only CHR; the access
  model (per clinic or global); and the fees.
- [ ] **Plume IA.** Propose a "Send to NomiaMD" export or webhook on note finalization. Ask for the
  payload format and how physicians are identified.
- [ ] **Epic / Santé Québec.** Identify who at Santé Québec (DSN program) approves third-party
  SMART apps, and what their process is. The fhir.epic.com registration and sandbox work are
  in step 11b and don't wait on this.
- [ ] **Verify the plan's open items** and write the answers into `encounter-intake-plan.md`:
  - TELUS API scope for Medesync
  - Omnimed partner terms and launch-hook mechanics
  - Santé Québec's process for SMART apps; whether GMF-U/CLSC family doctors chart in the DSN
  - market share per DMÉ among omnipraticiens

## Done when
Every contact has a dated status line in a tracking table (append it to this file):
contacted / in discussion / agreement / blocked + reason.

## Tracking
| Party | Contact | Status | Date | Next action |
|---|---|---|---|---|
| Pilot GMF | | | | |
| Omnimed | | | | |
| TELUS Health | | | | |
| Plume IA | | | | |
| Epic / Santé Québec | | | | |

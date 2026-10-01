# Step 20 — TELUS (Medesync) API connector

**Phase:** 5 · **Depends on:** 07, 10 (polling), 16; the TELUS partner agreement (04)
**Blocked on:** confirming the CHR Enterprise API covers Medesync clinics (plan open item)
**Plan section:** §1a Medesync

## Goal
Pull Medesync physicians' signed notes automatically, replacing the extension adapter for
Medesync.

## Tasks
- [ ] Confirm with TELUS what applies to Medesync specifically: the CHR Enterprise API (GraphQL), the
  TELUS Patient Chart FHIR R4 IG, or something else. **Rewrite this step if the answer differs.**
- [ ] Auth: RS512-signed JWT bearer (15-min expiry), signing key provisioned by TELUS and stored
  as a secret (never in the repo). `TelusTokenSigner` renews the token before expiry.
- [ ] `app/intake/connectors/telus_chr.py`: `TelusChrConnector(PullConnector)`:
  - query signed clinical documents and encounters per clinic since a cursor
  - map them to `SourceNote` (`source_system="medesync"`, `channel=partner_api`); NAM from
    the patient identifiers
- [ ] Clinic onboarding: a `ConnectorAccount` (clinic id, credentials ref, cursor, user mapping
  from the TELUS practitioner id to `User`).
- [ ] Polling: an arq cron job every N minutes per active `ConnectorAccount` (step 10's hook).
  Back off on errors, and alert when a clinic fails repeatedly.
- [ ] Unit tests against recorded synthetic GraphQL responses. A sandbox contract test is marked and excluded by default.
- [ ] Retire the Medesync extension adapter for clinics on the API (step 13's retirement rule).

## Done when
- Fixtures → `SourceNote` mapping tests pass. The cursor advances and re-polling creates no duplicates.
- The pilot clinic's notes appear in the inbox without the extension.

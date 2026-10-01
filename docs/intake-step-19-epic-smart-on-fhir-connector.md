# Step 19 — Epic (DSN) production integration (SMART on FHIR)

**Phase:** 5 (18+) · **Depends on:** 11b (client + mapper), 16; Santé Québec contact (04)
**Production blocked on:** Santé Québec activating the client id (security review, ÉFVP, possibly MSSS homologation)
**Plan section:** §1b

## Goal
Real ER and hospital notes reach NomiaMD from the DSN without copy/paste: in context (SMART
launch from the chart) and in bulk (the physician's signed notes for a shift). The sandbox
connector from step 11b already provides `EpicFhirClient` and `EpicNoteMapper`. This step adds what
production needs.

## Tasks
- [ ] SMART **EHR launch** (from inside Epic) and **standalone launch** (bulk shift fetch), PKCE,
  confidential client.
  - Scopes: `launch`, `openid`, `fhirUser`, `patient/Patient.read`, `patient/Encounter.read`,
    `patient/DocumentReference.read`, `patient/Binary.read`, `user/Practitioner.read`
  - Check Epic's scope syntax (v1 vs v2) for the DSN environment.
- [ ] Route `/launch/epic`: finish OAuth, fetch the launch context's notes with
  `EpicFhirClient`/`EpicNoteMapper`, run `IntakeService.receive` (`source_system="epic"`), then
  redirect to the inbox item.
- [ ] `DsnIdentifierStrategy` (replaces 11b's `SandboxIdentifierStrategy`): read the NAM from
  `Patient.identifier`. **Verify the identifier system URI** Santé Québec uses for the NAM.
- [ ] Practitioner mapping: Epic `fhirUser` → NomiaMD `User` (by practice number, or a linking step).
- [ ] Per-user token storage: refresh tokens encrypted at rest, revoked on logout or unlink.
- [ ] Amended notes: rely on `meta.versionId` → step 16's `new_version` handling. Test that an
  addendum supersedes the earlier version.
- [ ] Confirm the DSN's date format and note templates (French or English). Adjust the
  normalizer's `date_order` per environment rather than hard-coding `mdy`.
- [ ] Production checklist for Santé Québec (security, ÉFVP, hosting, logging), tracked in
  step 04's table.

## Done when
- Unit tests: the EHR launch callback creates an encounter for the launch patient; the
  DSN identifier strategy reads the NAM; an addendum → new version.
- Launch → note → inbox works against the sandbox with the production code path (EHR launch
  simulated with Epic's launch tooling, if available).
- The production client id is activated by Santé Québec (external milestone).

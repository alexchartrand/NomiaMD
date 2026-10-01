# Step 21 — Omnimed pre-billing hook

**Phase:** 5 · **Depends on:** 07, 09, 16; the Omnimed partner agreement (04)
**Blocked on:** Omnimed's launch contract (parameters, signing, whether the note text is included)
**Plan section:** §1a Omnimed, §2 flow 2

## Goal
NomiaMD becomes one of Omnimed's pre-billing systems (alongside Xacte, FACNET and MultiD). The
physician clicks bill in Omnimed and lands in NomiaMD with the encounter ready.

## Tasks
- [ ] Get Omnimed's integration spec. Record in this file:
  - the transport (signed URL launch? server-to-server push?)
  - the fields (physician, billing location, NAM, name, date are known from the Xacte case)
  - whether the signed note text comes along or must be fetched separately
- [ ] Route `/launch/omnimed`:
  - validate the signature or token according to the spec
  - map the physician to `User` (practice number), and the location to `encounter_meta.location_label`/`etablissement_number`
  - `IntakeService.receive` with `channel=partner_api`, `source_system="omnimed"`
  - redirect to the inbox item, or to the login page and then back
- [ ] If the note text isn't in the launch payload, the encounter is created as "en attente de la
  note". The extension (step 13) or an Omnimed API call fills it in. The dedup fallback merges them.
- [ ] Billing location and date from Omnimed are **structured metadata**. They take precedence
  over the summary (step 17's rule).
- [ ] Retire the Omnimed extension adapter for clinics on the hook (step 13's retirement rule).

## Done when
- Tests cover: valid launch → encounter created with patient resolved by NAM; bad signature →
  rejected with nothing stored; a repeated launch for the same visit → same encounter.
- End-to-end test in Omnimed's partner test environment.

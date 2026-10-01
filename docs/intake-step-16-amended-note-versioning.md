# Step 16 — Amended notes (versioning and claim re-review)

**Phase:** 4 · **Depends on:** 06, 07 · **Unblocks:** API connectors (20, 21) that re-send notes
**Plan section:** §3 Amended notes

## Goal
When a signed note gets an addendum, extract it again. **Never** silently change a claim
that was made from the old version: flag it for the physician instead.

## Tasks
- [ ] `IntakeService.receive`, for the `new_version` outcome (same `external_note_id`, new hash):
  - create a new encounter with the same external id and set `superseded_by_id` on the previous one
  - copy over the patient if it was resolved
  - enqueue extraction
- [ ] Derived states:
  - old encounter → `modifié`
  - a claim whose encounter is superseded **and** not voided → "à revoir"
  - computed in queries, not stored, like `claims` status in `app/claims/status.py`
- [ ] Inbox: a `modifié` row links to its new version. The new version's review shows a diff
  hint ("codes ajoutés / retirés par rapport à la réclamation existante").
- [ ] Facturation (`FacturationPage/RecordsTab.tsx`): an "à revoir" badge. Actions: keep the
  existing claim (record `claims.reviewed_after_amendment_at`) or void it and bill from the new version.
- [ ] Confirmed duplicates (step 11): when the physician marks an encounter as the same visit
  as another and **both** already have a live claim, the hidden one's claim becomes "à revoir"
  too, so one visit can't go out billed twice.
- [ ] Inbox and the bill generator must not let a claim go out that is "à revoir" and not yet
  re-confirmed (it's excluded from bills until resolved).

## Done when
Tests cover:
- v2 supersedes v1
- a claim on v1 becomes "à revoir"
- the keep action clears it
- the void + new claim path works
- re-sending v1's hash after v2 is a `duplicate`, not a revert
- a bill excludes "à revoir" claims
- confirming a duplicate when both encounters have a live claim flags the hidden one's claim

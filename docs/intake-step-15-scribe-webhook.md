# Step 15 — Scribe webhook channel

**Phase:** 4 (weeks 14–18) · **Depends on:** 07, 09; the partner agreement from 04 (Plume IA first)
**Plan section:** §1c, §2 flow 4

## Goal
A scribe sends the **physician-finalized** note to NomiaMD, and it lands in the inbox like any
other source.

## Tasks
- [ ] `IntegrationPartner` model, table `integration_partners`: `slug` (`plume_ia`), `name`,
  `webhook_secret_hash`, `active`.
- [ ] `PartnerAccountLink` model: `(partner_id, partner_user_ref) → user_id`. Created when
  the physician links their account (an OAuth-style "Connecter Plume IA" flow, or a one-time
  code shown in NomiaMD and entered in the scribe; pick whichever the partner supports).
- [ ] Route `POST /intake/scribe/{partner_slug}`:
  - verify the HMAC-SHA256 signature over the raw body plus a timestamp header (reject if >5 min
    old, to stop replays)
  - resolve the physician through `PartnerAccountLink`
  - **reject anything not marked finalized** by the partner
- [ ] A payload adapter per partner (`app/intake/connectors/scribes/plume_ia.py`), mapping to
  `SourceNote` with `channel=scribe_webhook`. Build a `generic.py` with a documented
  payload first, so the work isn't blocked on the partner's format.
- [ ] Attestation: an encounter from a scribe shows "Note issue de <scribe> — confirmez qu'elle
  correspond au dossier signé" in the review. Saving the claim records the attestation (a new
  `claims.source_attested_at`, nullable).
- [ ] Dedup across channels: the step 07 fallback `(patient, service_date, author_ref)` must
  merge the same visit sent by both the extension and the scribe. Show one row with both sources listed.

## Done when
Tests cover:
- a valid signature is accepted, while a wrong signature, an old timestamp and a replay are rejected
- an unknown `partner_user_ref` gets 404 with no data stored
- a non-finalized note is rejected
- the extension + scribe pair for the same visit gives one encounter
- the claim records the attestation

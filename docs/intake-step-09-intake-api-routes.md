# Step 09 — Intake and encounter API routes

**Phase:** 2 · **Depends on:** 07, 08 · **Unblocks:** 10, 11, 13
**Plan section:** §4 `router.py`

## Goal
HTTP endpoints for pushing notes in and for working the inbox.

## Routes (`app/intake/router.py`, mounted in `app/main.py`)
| Method | Path | Body / query | Notes |
|---|---|---|---|
| POST | `/intake/notes` | `{text, source_system, batch_label?}` or a list of `SourceNote` | Session auth for now. Step 12 adds device tokens, step 15 adds scribe HMAC. Rate-limited. Returns one `ReceiveOutcome` per note |
| POST | `/intake/upload` | multipart `.txt`/`.md` | → `ManualConnector` |
| GET | `/encounters` | `?date=YYYY-MM-DD` (default: today from `Clock`) | Inbox rows: id, patient (name/NAM masked), source, batch_label, derived status, code count, `all_clean` flag |
| GET | `/encounters/{id}` | — | Note text, meta, latest run's result (same shape as `BillingExtractionResponse`) |
| POST | `/encounters/{id}/patient` | `{patient_id}` | Manual pick for "à associer". Enqueues extraction |
| POST | `/encounters/{id}/extract` | — | On-demand, synchronous (same short-session pattern as `/extract`). Returns the extraction |

- [ ] Ownership: every route scopes by `current_user.id`. Someone else's encounter returns 404.
- [ ] `all_clean` = every code has `confidence == "high"` and an empty `needs_confirmation`.
  Computed server-side, used by step 11's approve-all.
- [ ] `POST /claims` is unchanged (it still takes `extraction_run_id`).
- [ ] Decide whether `/extract` is deprecated in favour of `/intake/notes` +
  `/encounters/{id}/extract`. Leave it in place until step 11 ships.

## Done when
API tests (seeded through `session_scope()` per CLAUDE.md) cover:
- push one note with a known NAM: status `prêt` with the inline queue
- push with an unknown NAM: `à associer`; manual pick: `prêt`
- duplicate push: no new row
- another physician's encounter: 404
- `all_clean` true and false cases

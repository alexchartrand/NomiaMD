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

- [x] Ownership: every route scopes by `current_user.id`. Someone else's encounter returns 404.
- [x] `all_clean` = every code has `confidence == "high"` and an empty `needs_confirmation`.
  Computed server-side, used by step 11's approve-all.
- [x] `POST /claims` is unchanged (it still takes `extraction_run_id`).
- [x] Decide whether `/extract` is deprecated in favour of `/intake/notes` +
  `/encounters/{id}/extract`. Leave it in place until step 11 ships.

## Done when
API tests (seeded through `session_scope()` per CLAUDE.md) cover:
- push one note with a known NAM: status `prêt` with the inline queue
- push with an unknown NAM: `à associer`; manual pick: `prêt`
- duplicate push: no new row
- another physician's encounter: 404
- `all_clean` true and false cases

## Notes (done 10/1)
- **Two routers, not one.** `/intake/*` is `app/intake/router.py`. The `/encounters` routes
  are a new `app/encounters/` package: they return billing results (`BillingCodesResult`,
  `all_clean`), and `app/intake` never imports `ramq_codes`. `app/encounters/` is where
  intake and extraction meet, and `build_intake_service()` (in its `factory.py`) wires
  `IntakeService` + `InlineExtractionQueue(PipelineEncounterExtractor())`. `main.py`'s
  lifespan builds it once and stores it on `app.state.intake_service`. Step 10 picks its
  queue there.
- **`POST /intake/notes`** takes either `{text, source_system="manual", batch_label?}`
  (cut by `ManualConnector.from_paste`, so an ER shift works) or a list of `SourceNote`.
  An empty paste → 422. A note that's empty once normalized (`EmptyNoteError`) fails the
  whole request with a 422. The notes before it are already stored, but resending the
  batch is safe: they come back as duplicates. `source_system` defaults to `"manual"`.
- **`POST /intake/upload`**: multipart `file` + form `source_system`/`batch_label`, 2 MB
  max (413). Anything but `.txt`/`.md` UTF-8 → 422. Added `python-multipart`.
- Rate limits: 10/minute on both intake routes and on the two `/encounters` POSTs. They
  run the extraction inline until step 10.
- **The inbox shows undated encounters.** `list_for_day` used to match only
  `service_date == day`. An encounter with no date yet (a paste with no date, waiting for
  a patient or for the summary to find one) would never have shown, so "à associer"
  pastes were invisible. It now also matches an undated encounter received on that day,
  in clinic time (`clinic_day_bounds` in `app/clock.py`, a `ReceivedWindow` for the
  repository). Once extraction finds a date, the encounter moves to that day.
- **`all_clean`** (`app/encounters/readiness.py`): status `prêt`, at least one code, every
  code `high` with an empty `needs_confirmation`. `revu` rows are never clean, so
  approve-all can't bill twice. An empty extraction is never clean, since there'd be
  nothing to approve.
- **Masking in the list**: `"Roch D."` and `"DESR ******01"` (the six birth-date digits
  hidden). `GET /encounters/{id}` gives the full name and NAM.
- `GET /encounters/{id}` → `EncounterDetailOut`: note text, meta, `extraction_error`, and
  `extraction` in `BillingExtractionResponse`'s shape, read back from the latest run by
  `StoredExtractionLoader` (`app/extraction/stored.py`). Its `encounter_date` is the
  encounter's `service_date`, the date a claim from it is dated with.
- `POST /encounters/{id}/patient` → `IntakeService.assign_patient`: 404 for someone
  else's encounter or an unknown patient, 409 if it already has a patient (its runs were
  eligibility-filtered for that one). Then it enqueues, and returns the encounter's detail.
- `POST /encounters/{id}/extract` (`OnDemandExtraction`): 409 while "à associer". A
  pipeline failure is recorded ("échec") and propagates as a 500, same as `/extract`.
- **`/extract` stays** until step 11 moves the paste page onto `/intake/notes` +
  `/encounters/{id}/extract`.
- `GET /encounters?date=` defaults to `get_clock().today()` (new `get_clock` dependency in
  `app/clock.py`, overridable in tests).
- Frontend types (`encounters.ts`, `intake.ts`) are step 11's.

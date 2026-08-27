# Backlog

## How to use this
- Add new items under the right section, newest on top.
- Check off `[x]` when done, but leave the line — don't delete (keeps history).
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🟡 Three different strategies for the same enum problem — *added 8/27, from schema review*
  - `UserRole`/`Gender` are native `Enum(...)`; `PhysicianProfile.physician_type`/`remuneration_type` are `String(255)` shadowing a Python enum; `Claim.status` is `String(16)` validated by a Pydantic `Literal`. All three defensible in isolation, incoherent together.
  - Fix once Alembic lands: native `Enum` for vocabularies this codebase owns (role, gender), `String` + boundary validation for anything RAMQ's vocabulary controls (status, physician/remuneration type).

- [ ] 🟢 NAM stored in plaintext — *added 8/27, from schema review*
  - `patients.ramq_number` and the NAM inside `extraction_records.result_json` are a direct government identifier at rest with no column-level protection. Worth a pgcrypto/application-level encryption decision before real patient data, alongside the retention item above.

- [ ] 🟡 NAM matching scans the whole roster instead of an indexed lookup — *added 8/24, from billing-workflow code review*
  - `PatientSuggestionService._match` (`app/patients/suggestion.py`) calls `list_for_physician` and filters for a NAM match in Python, on every `/extract` call. `PatientRepository` has no `find_by_ramq(physician_id, nam)`. Fine at demo scale; a physician with hundreds of roster patients pays for the full roster transfer/deserialization just to find at most one match, on a rate-limited hot path.

- [ ] 🟢 Slash-date parsing assumes `DD/MM/YYYY`, would misparse an Epic-style `MM/DD/YYYY` note — *added 8/24, from billing-workflow code review*
  - `app/extraction/encounter_date.py`'s `_SLASH_DATE_RE` always reads `d/m/y`. Harmless today (Epic/Plume AI sources are still disabled buttons in the UI, and Quebec notes use `DD/MM/YYYY`), but once a US-market EHR source is wired up, a date like "03/04/2026" would silently parse as March 4 instead of April 3 for any day/month both ≤ 12 — no error, just a silently wrong `encounter_date`. Revisit once a real `source.system` other than `simule` sends dates.

- [ ] 🟢 Facturation's patient filter can't select a soft-deleted patient — *added 8/24, from billing-workflow code review*
  - `ClaimRepository.list_for_physician` deliberately doesn't filter `is_deleted` (a deleted patient's past claims must keep showing their name), but `FacturationPage.tsx`'s patient filter dropdown is populated from `listPatients()`, which does filter it out — so there's no way to filter the list down to just that patient's claims once they've left the roster. Minor; the "all patients" view still shows them.

- [ ] 🔴 No purge/retention policy on `extraction_records` — *added 8/21, moved from DEPLOY.md, escalated 8/24*
  - Stores each transcript + result indefinitely. Acceptable while demoing with the synthetic notes in `consultations/`; must revisit before this ever touches real patient data (Law 25).
  - Escalated: `extraction_records.result_json` now holds the patient's name **and NAM** as discrete, greppable fields (`patient_information.name_as_stated`/`ramq_number_as_stated`, billing-workflow plan Part 1) — a NAM is a direct government identifier, which makes this materially more pressing than before.

- [ ] 🔴 No Alembic — schema changes require a DB wipe or a hand-run `ALTER TABLE` — *added 8/24, escalated 8/27*
  - `init_db()` only runs `Base.metadata.create_all`, which creates missing tables but never alters an existing one. `patients.is_deleted` (billing-workflow plan Part 4) is the first column added to an existing table since this app went live; the next one needs the same manual `ALTER TABLE` step on prod, or a wipe locally. Adopt Alembic before billing data is real.
  - Escalated 8/27: this is the blocker for every other schema item in this section — none of them are applicable to a live DB without migrations. It's also the stated cause of two existing workarounds (`Claim.status` as a bare `String` instead of an enum; `BillClaim` existing as a table because "a new column on an existing table isn't free"), so adopting Alembic removes the constraint those were designed around. Not urgent while there's no production DB — the local SQLite file is disposable — but it gates going live.

- [ ] 🟡 Hard-deleting a `facturé` billing record destroys audit trail — *added 8/24*
  - `DELETE /claims/{id}` (`app/claims/router.py`) hard-deletes regardless of `status` — there's no soft-delete equivalent to `patients.is_deleted` for claims. Fine for a `brouillon` mistake; loses the audit trail for anything already marked `facturé`.

- [ ] 🟢 No backup of the `postgres_data` volume — *added 8/21, moved from DEPLOY.md*
  - Fine for a short-lived demo seeded with synthetic data; take a manual `pg_dump` first if that stops being true.

- [x] 🟢 Docker's default `json-file` log driver has no rotation — *added 8/21, moved from DEPLOY.md, done 8/24*
  - Not a concern at demo traffic/duration. Add `logging: driver: json-file, options: {max-size: 10m, max-file: "3"}` per service in `docker-compose.yml` if this runs long enough to matter.
  - Fixed: all five services in `docker-compose.yml` now set `logging: driver: json-file, options: {max-size: "10m", max-file: "3"}`.

- [ ] 🔴 Vector search blocks the event loop — *added 8/19, from codebase audit*
  - `LanceDBVectorStore` has no `aquery` override, so both retrievers' `_aretrieve` (`ramq_codes/retriever.py`, `ramq_chatbot/retriever.py`) fall back to the sync `.retrieve()` call under the hood. Every concurrent physician's request stalls the single event loop for the duration of the native call.
  - Fix: wrap the sync query in `run_in_threadpool`, or move to an async-native vector store call path.

- [ ] 🟡 No server-side check that returned billing codes are from the candidate set — *added 8/19, from codebase audit, note added 8/24*
  - `ramq_codes/task.py`'s `parse()` only validates JSON shape, never cross-checks returned `number`s against the candidates built in `build_prompt`. The "only choose from candidates" constraint lives in the prompt only. Mandatory physician review is the only backstop today — no defense in depth.
  - Note: `POST /claims` (`app/claims/service.py`) *does* validate its `selected_codes` against the referenced extraction's own stored candidates (422 on an unknown code) — but that's checking the physician's selection against what the model already returned, not checking what the model returned against what it was offered. This item is still open.

- [ ] 🟡 Login timing side-channel enables user enumeration — *added 8/19, from codebase audit*
  - `auth/service.py` `login()` returns immediately on `user is None`, but runs the deliberately slow Argon2 `verify()` when the email exists — response time distinguishes valid from invalid emails.
  - Fix: always run a dummy hash verify on the unknown-user path. Low real-world impact given the small, manually-provisioned user base.

- [ ] 🟡 Argon2 verify blocks the event loop on every login — *added 8/19, from codebase audit*
  - `AuthService.login` (async) calls the sync, CPU-slow `PasswordHasher.verify` directly (`auth/security.py`), no `run_in_threadpool`. Stalls the whole process for tens–hundreds of ms, including other physicians' in-flight `/extract`/`/query` requests.

- [ ] 🟢 Backend has no network-level allowlist of its own — *added 8/19, from codebase audit*
  - `docker-compose.yml`: header-spoofing protection depends entirely on nginx being the only path to `backend:8000`. Partially mitigated since S1's fix moved backend to an `internal` network, but backend still has no self-defense if another container joins that network later.

- [ ] 🟢 Non-backend containers run with image-default privileges — *added 8/19, from codebase audit*
  - Postgres/redis/caddy/frontend don't set an explicit non-root `user:` in `docker-compose.yml`. Backend (the real attack surface) already drops to `appuser`.

- [ ] 🟢 DEPLOY.md and nginx's allowlist behavior disagree — *added 8/19, from codebase audit*
  - `DEPLOY.md:65-67` says leaving `ALLOWED_CIDRS` unset makes the demo fully public; `frontend/docker-entrypoint.sh` actually `deny all`s everything but `127.0.0.1` in that case. Fails safe, but will send an operator chasing a bogus CIDR issue.

- [ ] 🟢 Prompt injection surface is unhardened — *added 8/19, from codebase audit*
  - Transcript and chat text are interpolated directly into prompts (`summary/task.py`, `ramq_codes/task.py`, `ramq_chatbot/engine.py`) with only section headers, no delimiter/escaping scheme. Low impact today given JSON-schema output + mandatory physician review downstream.

## ✨ Features

- [ ] 🟢 LLM usage/timing logging (token counts, execution time) — *added 8/27*
  - Every extraction LLM call already funnels through one chokepoint, `app/extraction/engine.py`'s `run_extraction` (`client.achat(...)`), and `ramq_chatbot/factory.py` builds its own `MistralAI` client the same way — so either option below is a single integration point, not scattered instrumentation.
  - Decide between: (a) self-hosted Langfuse, using its `llama_index` instrumentor (`LlamaIndexInstrumentor` from `langfuse.llama_index`, started once in `bootstrap.py`) for full traces/dashboards/cost aggregation, vs (b) lightweight DB logging — wrap the `achat` call with `time.perf_counter()`, read `response.raw["usage"]` (Mistral's API is OpenAI-compatible), and persist onto the existing `ExtractionRecord` row (`app/postgresdb/models.py`).
  - Self-hosted Langfuse means another service to run/maintain but gets a UI, prompt diffing, and cost views; DB logging is zero new infra and keeps prompt/response content off any third-party system (relevant here since transcripts carry patient name + NAM), but you build your own queries/views to look at it.

- [x] 🟡 Add a data logger for production — *added 8/21, done 8/24*
  - Fixed: `app/logging_config.py` configures stdlib `logging` to emit one JSON line per event to stdout (same shape as `app/request_logging.py`'s existing per-request access log), wired at startup in `app/main.py`. Added `logger` calls at the silent-failure spots worth surfacing: `CodeTable.get_all` (`app/lancedb/db.py`) now warns on candidate numbers with no matching `codes` row (stale index), `AuthService.login` (`app/auth/service.py`) now logs failed/successful login attempts, and `RequestLoggingMiddleware` now logs unhandled exceptions with the same `request_id` as its access-log line before re-raising.

## 🧹 Cleanup / Dead code

- [ ] 🟢 Ownership/soft-delete guard copy-pasted across repository methods — *added 8/24, from billing-workflow code review*
  - `if patient is None or patient.physician_id != physician_id or patient.is_deleted: return None/False` is typed out identically in `PatientRepository.get_for_physician`/`update_for_physician`/`delete_for_physician`, and the analogous `record is None or record.physician_id != physician_id` check appears three more times in `ClaimRepository` (`app/postgresdb/repository.py`). A future rule change (e.g. "also block if the physician account is deactivated") means finding and updating all six copies by hand.

- [ ] 🟢 `patients/router.py` and `PatientSuggestionService`'s construction skip the factory/`Depends` DI pattern — *added 8/24, from billing-workflow code review*
  - `billing/factory.py` and `auth/factory.py` both expose a `get_*_service()` wired via FastAPI `Depends`, but `patients/router.py` instantiates `PatientRepository()` inline in every handler (no `patients/factory.py`), and `extraction/router.py` does the same for `PatientSuggestionService()`. Not a bug, just an inconsistent seam — swapping or mocking either at the dependency layer (the way tests already do for `BillingService`) isn't possible without editing the router directly.

- [ ] 🟢 A few independent DB round trips are awaited sequentially instead of concurrently — *added 8/24, from billing-workflow code review*
  - `ClaimService.create` (`app/claims/service.py`) awaits the patient/extraction/duplicate-check lookups one at a time even though none depends on another's result; `extraction/router.py`'s `create_many(...)` and `_build_patient_suggestion(...)` are similarly independent. `asyncio.gather` would roughly halve the added latency on both the extraction and claim-save hot paths. Not measured against real Postgres latency — worth profiling before spending effort here.
  - Related: `BillingService.update_status` re-fetches the record it just updated via a second full query (`update_status_for_physician` + `get_for_physician`) instead of having the update return the same detail shape directly.

- [ ] 🟢 Remove `MISTRAL_EMBEDDING_MODEL` from `.env` — *added 8/21*
  - `config.py`'s `mistral_embedding_model` reads it from env and `embedings.py` passes it straight to `MistralAIEmbedding`, but it must always match whatever model ramq-ingestion used to embed the `code-embeddings`/`documents-embeddings` LanceDB tables (`mistral-embed`) — changing it doesn't degrade gracefully, it silently breaks retrieval (embedding-space mismatch). Extraction's model name is already hardcoded as `MODEL` in `app/extraction/engine.py`; this should be too, rather than exposed as an operator-configurable env var.

- [ ] 🟢 Unused dependency: pandas — *added 8/19, from codebase audit*
  - Declared in `backend/pyproject.toml`; zero imports anywhere in `app/`, `scripts/`, or `tests/`.

- [ ] 🟢 Unused "ghost" button variant — *added 8/19, from codebase audit*
  - `components/Button.tsx` + `styles.css:135-140` — defined with matching CSS, no call site anywhere passes `variant="ghost"`.

- [ ] 🟢 Unused `tagline` prop — *added 8/19, from codebase audit*
  - `components/PageHeader.tsx` renders it, but its only call site `SiteHeader.tsx` never supplies it.

- [ ] 🟢 `encounter_id` accepted, validated, then discarded — *added 8/19, from codebase audit, needs confirmation*
  - `extraction/models.py` / `extraction/router.py` — router only reads `source.system`; `encounter_id` is parsed and never persisted. Frontend doesn't send a `source` object today. CLAUDE.md frames multi-source ingestion (Epic/Plume) as part of the design, so may be intentional scaffolding rather than a mistake.

## ✅ Done

- [x] 🟢 No unique constraint on `(physician_id, ramq_number)` on `patients` — *added 8/24, done 8/27, from billing-workflow code review*
  - Soft-deleting a patient and re-adding the same NAM (or a data-entry duplicate) created two roster rows sharing a NAM. `PatientSuggestionService._match` already degraded gracefully (logs a warning, treats it as no match) rather than crashing or guessing, but the duplicate itself was never surfaced to the physician as a data-integrity problem.
  - Fixed: `ix_patients_physician_ramq_number_active` (`app/postgresdb/models.py`) — a **partial** unique index on `(physician_id, ramq_number)`, scoped to `deleted_at IS NULL` (`postgresql_where`/`sqlite_where`) so a soft-deleted patient never blocks re-adding the same NAM. Unlike the FK `ondelete`/composite-FK schema-review items, this is live on both dialects: SQLite enforces unique indexes unconditionally (no `PRAGMA foreign_keys` gate involved), confirmed with a standalone in-memory-SQLite repro. `PatientRepository.create`/`update_for_physician` (`app/postgresdb/repository.py`) also pre-check for an active NAM collision and raise `DuplicatePatientRamqNumberError` (excluding the patient's own row on update) — same "clean error over a raw IntegrityError, DB constraint as the backstop" shape as `ClaimService`'s duplicate-extraction check — which `patients/router.py` maps to a 409. Doesn't cover a NAM that's merely `nam.normalize()`-equivalent under different literal formatting (e.g. `"DESR81021001"` vs `"desr 8102-1001"`) — that gap is real and intentionally left to `PatientSuggestionService._match`'s existing multi-match fallback, now the only remaining code path that can still see two active rows sharing a NAM; `test_patient_suggestion.py`'s `test_duplicate_nam_across_roster_rows_is_no_match_not_a_coin_flip` was rewritten around exactly that case (its old exact-literal-duplicate setup no longer round-trips through `PatientRepository.create`). Added `test_patients.py` coverage: re-adding the same NAM after a soft delete succeeds, a second active create/update onto the same NAM is 409, and two patients with no NAM at all don't collide. Several fixture helpers across `test_patients.py`/`test_claims.py`/`test_bills.py`/`test_bill_repository.py` previously reused one hardcoded NAM per physician across many tests against the same never-reset session-scoped test DB (see conftest.py) — harmless before this constraint, a 409 after — so each now mints a fresh NAM per seeded patient.

- [x] 🟡 `extraction_records.result_json` is `Text`, not JSONB — *added 8/27, done 8/27, from schema review*
  - It holds the patient name and NAM as discrete fields. As `Text`, both the retention purge (see the Law 25 item above) and any "which extractions mention this NAM" query are a full table scan with a `LIKE`.
  - Fixed: `result_json` is now `JSON().with_variant(JSONB, "postgresql")` (`app/postgresdb/models.py`), typed as `dict` instead of `str`. `ExtractionRepository.create_many` now stores the dict directly instead of `json.dumps`-ing it, and `ClaimService.create` reads `extraction_record.result_json` directly instead of `json.loads`-ing it — the now-unused `json` imports were dropped from both `postgresdb/repository.py` and `claims/service.py`. Keeps the SQLite dev path working, makes the Postgres path indexable.

- [x] 🟢 Timestamp defaults are Python-side only — *added 8/27, done 8/27, from schema review*
  - Every `created_at`/`updated_at` uses `default=lambda: datetime.now(timezone.utc)`, which never fires for a migration backfill, a raw `INSERT`, or a `psql` fix-up.
  - Fixed: every such column across `User`, `PhysicianProfile`, `Patient`, `ExtractionRecord`, `Claim`, and `Bill` (`app/postgresdb/models.py`) now also sets `server_default=func.now()` alongside the existing Python-side default.

- [x] 🟢 Index gaps on the per-physician list queries — *added 8/27, done 8/27, from schema review*
  - `extraction_records` has no index on `(user_id, created_at)` despite being listed per user; `bills` has none on `(physician_id, start_date)` despite being listed per physician per date range. `claims` already got this right (`ix_claims_physician_service_date`).
  - Fixed: added `ix_extraction_records_user_created` on `ExtractionRecord.__table_args__` and `ix_bills_physician_start_date` on `Bill.__table_args__` (`app/postgresdb/models.py`), mirroring `claims`' existing composite index.

- [x] 🟢 `is_deleted` bool loses *when* a record was removed — *added 8/27, done 8/27, from schema review*
  - `patients.is_deleted` filters identically as a nullable `deleted_at` timestamp (`IS NULL`), but under Law 25 the deletion date is the thing an audit asks for.
  - Fixed: `Patient.is_deleted` (`Boolean`) replaced with `Patient.deleted_at` (`DateTime | None`, indexed) in `app/postgresdb/models.py`. `PatientRepository` (`app/postgresdb/repository.py`) updated throughout: `is_deleted.is_(False)` → `deleted_at.is_(None)`, the ownership/soft-delete guards in `get_for_physician`/`update_for_physician`/`delete_for_physician` check `deleted_at is not None`, and `delete_for_physician` now sets `deleted_at = datetime.now(timezone.utc)` instead of `is_deleted = True`. No API/frontend exposure existed to update — the flag never left the repository layer.

- [x] 🟢 No `pool_pre_ping` on the Postgres engine — *added 8/27, done 8/27, from schema review*
  - `database.py`'s `create_async_engine` took no pool config. A long-lived container against a Postgres that recycles connections would be handed a stale one.
  - Fixed: on the non-SQLite path, `create_async_engine` (`app/postgresdb/database.py`) now also passes `pool_pre_ping=True` and an explicit `pool_size=10`; the SQLite dev path is untouched (meaningless there, and unsupported by aiosqlite's `NullPool`).

- [x] 🟡 No `ondelete` on any foreign key — *added 8/27, done 8/27, from schema review*
  - `ClaimRepository.delete_for_physician` deletes `ClaimCode` rows by hand (`repository.py:387`) and `BillRepository.delete_for_physician` does the same for `BillClaim`. Correct today, but nothing at the DB level stopped a future path — or a psql session — from orphaning them.
  - Fixed: `ondelete="CASCADE"` on `claim_codes.claim_id` and `bill_claims.bill_id`/`claim_id`, `ondelete="RESTRICT"` on the `claims` composite `ForeignKeyConstraint(["patient_id", "physician_id"], ...)` (`app/postgresdb/models.py`). Same SQLite-is-a-no-op caveat as the composite-FK item below: live on Postgres only, so the repository methods' manual explicit deletes stay as the real guarantee in tests/dev — this closes the gap only for a future path or a raw psql session against prod. All 208 tests still pass unchanged.

- [x] Split `users` into credentials + dated physician profile — *added and done 8/27, from schema review*
  - `physician_type`/`number_of_patients`/`remuneration_type` moved off `users` into a new append-only `physician_profiles` table keyed by `(user_id, effective_from)`. They aren't preferences — they decide which RAMQ codes a physician may legally bill, and editing them used to silently rewrite the basis of every past claim (the failure `ClaimCode`'s fee snapshot already exists to prevent). Reads go through `PhysicianProfileRepository.get_effective_on(user_id, date)`; `get_current` is the same call with today's date. Same-day edits overwrite in place rather than appending.
  - `AuthService` kept authentication only; the new `ProfileService` (`app/auth/profile.py`) owns the profile read/write and returns a `PhysicianAccount` (user + applicable profile) that `UserOut` flattens — the API shape is unchanged, so no frontend change. `BillService.render_pdf` now prints the profile in effect at `bill.end_date` instead of today's.

- [x] Rate-limit bypass via X-Forwarded-For spoofing — *added 8/19, done 8/18, from codebase audit*
  - Fixed by commit 5c231b5 ("Pin backend's trusted proxy IP to nginx's static compose address") — `--forwarded-allow-ips` now pinned to nginx's static IP on an internal compose network, instead of trusting `*`.

- [x] Chat history grows unbounded, no truncation — *added 8/19, done 8/19, from codebase audit*
  - `ramq_chatbot/engine.py` now caps `chat_history` to the most recent `MAX_HISTORY_MESSAGES` (20) entries before threading it into the LLM prompt — backend-authoritative regardless of client behavior. `ChatbotPage.tsx` mirrors the same cap on what it sends (full scrollback still displays) and gained a "Effacer la conversation" clear button.

- [x] Chatbot's BM25 index builds synchronously on first request — *added 8/19, done 8/19, from codebase audit*
  - `ramq_chatbot/__init__.py` now calls `get_ramq_query_engine()` at import time (same trigger chain as `app/tasks/registry.py`'s eager `BillingCodesTask`), so the BM25 build runs once before uvicorn serves any request instead of blocking the first `/query` coroutine. `scripts/make_ci_fixture_db.py` extended with a throwaway `manuel-omnipraticiens` table so test collection still works without a real ramq-ingestion DB.

- [x] Chat bubbles re-parse markdown on every new message — *added 8/19, done 8/19, from codebase audit*
  - `ChatBubble.tsx` now wraps its component with `React.memo`. Since props are already primitive (`role`, `content`) rather than an object, and `ChatbotPage.tsx` only ever appends to `messages` (never mutates/reorders), older bubbles bail out of re-render/re-parse when a new message is appended instead of re-running `ReactMarkdown` on unchanged content.

- [x] Two sequential Postgres writes tail every extraction — *added 8/19, done 8/19, from codebase audit*
  - `ExtractionRepository.create` replaced with `create_many`, which opens a single session and does one `commit()` for both the `consultation_summary` and `billing_codes` rows. `extraction/router.py` now makes one `create_many([...])` call instead of two sequential `create(...)` calls — also closes a small atomicity gap where a mid-request failure could leave a summary row persisted with no matching billing_codes row.

- [x]  Money is a Python float end to end — *added 8/27, done 8/27, from schema review*
  - `ClaimCode.fee_amount` and `Bill.total_amount` are `Numeric(10, 2, asdecimal=False)`, so SQLAlchemy hands back `float`, and `bills/service.py:88` sums those floats into the invoice total. Postgres storage is exact; the arithmetic isn't, and the SQLite dev default has no exact numeric type at all. The output of this system is a dollar figure sent to RAMQ.
  - Fixed: dropped `asdecimal=False` on both `Numeric(10, 2)` columns (`app/postgresdb/models.py`) and threaded `Decimal` through `ClaimCodeInput`/`BillInput` (`postgresdb/repository.py`), `ClaimCodeOut`/`ClaimOut`/`BillOut` (`claims/models.py`, `bills/models.py`), `_total_amount`'s `sum()` (`claims/service.py`), the `total = 0.0` accumulator in `BillService.create` (`bills/service.py`), and `BillLineItem`/`BillDocument`/`_fmt_amount` in the PDF renderer (`bills/pdf.py`). The one float→Decimal conversion point is `claims/service.py`'s `_to_decimal`, right where a fee amount comes out of an extraction's stored JSON (`Decimal(str(amount))`, not `Decimal(amount)`, to avoid inheriting the binary float's imprecision). API responses still serialize `Decimal` as a JSON number via a `PlainSerializer` (`claims/models.py`'s `Money` type alias) — the frontend's `number` types and `.toFixed(2)` calls are unaffected; only backend storage and arithmetic changed. `CodeFee`/`ExtractedFee`/`CodeRowFee` (the LanceDB/LLM-schema boundary upstream of that conversion point) intentionally stay `float` — that data is float at the source and changing the LLM tool-call schema type is a separate concern. Added `test_bills.py::test_create_bill_total_is_exact_not_binary_float_drift` (two claims fee 0.10 + 0.20, asserts the bill total is exactly 0.30, not `0.30000000000000004`).

- [x] No DB-level guarantee that a claim's patient belongs to its physician — *added 8/27, done 8/27, from schema review*
  - `claims.physician_id` and `claims.patient_id` were independent FKs; only `ClaimService` enforced that the patient is on that physician's roster. One bad code path bills the wrong doctor's patient — a Law 25 incident, not a bug report.
  - Fixed: `patients` gained `UniqueConstraint("id", "physician_id")`; `claims.patient_id` lost its own `ForeignKey("patients.id")` in favor of a `ForeignKeyConstraint(["patient_id", "physician_id"], ["patients.id", "patients.physician_id"])` on `Claim.__table_args__` (`app/postgresdb/models.py`), so a mismatched pairing is rejected at the DB level on Postgres — a real guarantee, not just `ClaimService.create`'s existing `get_for_physician` check. Same accepted SQLite-is-a-no-op caveat as the sibling `ondelete` backlog item: SQLite doesn't enforce FKs without `PRAGMA foreign_keys=ON` (not set here), so this constraint is live on Postgres only; all 208 existing tests still pass unchanged since every test already pairs the right patient with the right physician.

---

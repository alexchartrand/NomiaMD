# Backlog

## How to use this
- Add new items under the right section, newest on top.
- Check off `[x]` when done, but leave the line — don't delete (keeps history).
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🟡 NAM matching scans the whole roster instead of an indexed lookup — *added 8/24, from billing-workflow code review*
  - `PatientSuggestionService._match` (`app/patients/suggestion.py`) calls `list_for_physician` and filters for a NAM match in Python, on every `/extract` call. `PatientRepository` has no `find_by_ramq(physician_id, nam)`. Fine at demo scale; a physician with hundreds of roster patients pays for the full roster transfer/deserialization just to find at most one match, on a rate-limited hot path.

- [ ] 🟢 No unique constraint on `(physician_id, ramq_number)` on `patients` — *added 8/24, from billing-workflow code review*
  - Soft-deleting a patient and re-adding the same NAM (or a data-entry duplicate) creates two roster rows sharing a NAM. `PatientSuggestionService._match` already degrades gracefully (logs a warning, treats it as no match) rather than crashing or guessing, but the duplicate itself is never surfaced to the physician as a data-integrity problem.

- [ ] 🟢 Slash-date parsing assumes `DD/MM/YYYY`, would misparse an Epic-style `MM/DD/YYYY` note — *added 8/24, from billing-workflow code review*
  - `app/extraction/encounter_date.py`'s `_SLASH_DATE_RE` always reads `d/m/y`. Harmless today (Epic/Plume AI sources are still disabled buttons in the UI, and Quebec notes use `DD/MM/YYYY`), but once a US-market EHR source is wired up, a date like "03/04/2026" would silently parse as March 4 instead of April 3 for any day/month both ≤ 12 — no error, just a silently wrong `encounter_date`. Revisit once a real `source.system` other than `simule` sends dates.

- [ ] 🟢 Facturation's patient filter can't select a soft-deleted patient — *added 8/24, from billing-workflow code review*
  - `ClaimRepository.list_for_physician` deliberately doesn't filter `is_deleted` (a deleted patient's past claims must keep showing their name), but `FacturationPage.tsx`'s patient filter dropdown is populated from `listPatients()`, which does filter it out — so there's no way to filter the list down to just that patient's claims once they've left the roster. Minor; the "all patients" view still shows them.

- [ ] 🔴 No purge/retention policy on `extraction_records` — *added 8/21, moved from DEPLOY.md, escalated 8/24*
  - Stores each transcript + result indefinitely. Acceptable while demoing with the synthetic notes in `consultations/`; must revisit before this ever touches real patient data (Law 25).
  - Escalated: `extraction_records.result_json` now holds the patient's name **and NAM** as discrete, greppable fields (`patient_information.name_as_stated`/`ramq_number_as_stated`, billing-workflow plan Part 1) — a NAM is a direct government identifier, which makes this materially more pressing than before.

- [ ] 🟡 No Alembic — schema changes require a DB wipe or a hand-run `ALTER TABLE` — *added 8/24*
  - `init_db()` only runs `Base.metadata.create_all`, which creates missing tables but never alters an existing one. `patients.is_deleted` (billing-workflow plan Part 4) is the first column added to an existing table since this app went live; the next one needs the same manual `ALTER TABLE` step on prod, or a wipe locally. Adopt Alembic before billing data is real.

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

---

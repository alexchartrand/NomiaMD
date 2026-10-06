# Backlog

## How to use this
- Add new items under the right section.
- When done (or obsolete), check it off `[x]` and move it to the top of ✅ Done with its title line only — drop the description (git history keeps it).
- Keep each open section ordered by priority (🔴, then 🟡, then 🟢); newest on top within a priority.
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🔴 No purge/retention policy on `encounters` — *added 8/21, moved from DEPLOY.md, escalated 8/24, escalated 8/29, reworded 9/30, retargeted 10/1*
  - The note text lives in `encounters.note_text` (with the patient's name and NAM verbatim), so the encounter is the purge target. Deleting one cascades to its runs and their results and sets `claims.extraction_run_id` to NULL; claims keep `source_note_hash`/`external_note_id`. `encounters.purge_after` (indexed) exists but nothing sets or acts on it — pick the retention period, set it where encounters are created, and add the job (intake step 05).
  - Acceptable while demoing with the synthetic notes in `consultations/`; must be done before this ever touches real patient data (Law 25). The NAM is scrubbed from the *prompt* (`app/patients/nam.py`'s `redact`), not from what's stored.

- [ ] 🔴 No Alembic — schema changes require a DB wipe or a hand-run `ALTER TABLE` — *added 8/24, escalated 8/27, deferred 9/30*
  - `init_db()` only runs `Base.metadata.create_all`, which creates missing tables but never alters an existing one.
  - Decided 9/30: not needed until the next release — every existing DB (local SQLite and the demo Postgres) is deleted and recreated on a schema change until then. Adopt Alembic (with the current schema as its baseline revision) before the first release that holds data worth keeping; it gates going live.

- [ ] 🟡 One extraction can mix two manual revisions — *added 9/30, from database review*
  - `CurrentCodeTableProvider.current()` is re-resolved on every `CodeRepository` call: once per planned query in `RAMQCodesRetriever`, then again in `BillingCodesTask.resolve_fees` after the LLM call. A promote landing mid-extraction gives candidates from one `codes_<rev>` and fees from another (or an empty fee list for a code dropped from the new manual). Fix: resolve the table once per extraction and pass it through — also the natural carrier for the `manual_rev` item in Features.

- [ ] 🟡 `Patient.is_vulnerable` can't say "unknown" — *added 10/1, from the profile-fallback review*
  - The column is a non-null bool defaulting to `False` (`app/postgresdb/models.py`), so a patient created without anyone checking vulnerability is treated as established non-vulnerable: `EligibilityFilterFactory` filters the vulnerable variants out and the axis is never flagged for confirmation. Same "never guess" rule `BillingContext` holds to everywhere else. Fix: make it nullable (null = not entered yet), default new patients to null, and have the patient form ask explicitly.

- [ ] 🟢 The test suite can't run against Postgres as-is — *added 9/30, from the schema batch*
  - `tests/db_helpers.py`'s `ensure_user_row` inserts users with explicit ids (1, 99, 2000…), which on Postgres doesn't advance `users_id_seq`, so the next autoincremented user (`test_auth.py`'s `_create_user`) collides on `users_pkey`. Only failure when conftest's `postgres_db` is pointed at Postgres. Fix: `setval` the sequence after seeding, or stop using fixed ids. Worth a `TEST_DATABASE_URL` switch in conftest once it passes — SQLite doesn't enforce `String(n)` lengths, which hid a too-short `claim_codes.code`.

- [ ] 🟢 A voided bill forgets which claims it held — *added 9/30, from the schema batch*
  - `claims.bill_id` is a single FK, so `BillService.delete` has to clear it to release the claims for re-billing. The voided `bills` row keeps its number, period, `total_amount` and `claim_count`, but not the claim list. If an audit needs that, add a `bill_claim_history` (append-only) or snapshot the claim ids onto the bill when it's voided.

- [ ] 🟢 NAM stored in plaintext — *added 8/27, from schema review*
  - `patients.ramq_number` and the NAM inside `encounters.note_text` are a direct government identifier at rest with no column-level protection. Worth a pgcrypto/application-level encryption decision before real patient data, alongside the retention item above.

- [ ] 🟢 Facturation's patient filter only lists the physician's own roster — *added 8/24, from billing-workflow code review, reworded 9/30*
  - `ClaimRepository.list_for_physician` deliberately doesn't filter `deleted_at` (a deleted patient's past claims keep showing their name), but `FacturationPage/RecordsTab.tsx`'s patient filter dropdown is filled from the physician's roster (`GET /patients`). Since the 8/31 global-patient refactor, claims aren't roster-gated, so any patient billed but never added to (or removed from) "my patients" can't be picked in the filter. Minor; the "all patients" view still shows their claims. Could be filled from the distinct patients on the physician's own claims instead.

- [ ] 🟢 No backup of the `postgres_data` volume — *added 8/21, moved from DEPLOY.md*
  - Fine for a short-lived demo seeded with synthetic data; take a manual `pg_dump` first if that stops being true.

- [ ] 🟢 Backend has no network-level allowlist of its own — *added 8/19, from codebase audit*
  - `docker-compose.yml`: header-spoofing protection depends entirely on nginx being the only path to `backend:8000`. Partially mitigated since S1's fix moved backend to an `internal` network, but backend still has no self-defense if another container joins that network later.

- [ ] 🟢 Non-backend containers run with image-default privileges — *added 8/19, from codebase audit*
  - Postgres/redis/caddy/frontend don't set an explicit non-root `user:` in `docker-compose.yml`. Backend (the real attack surface) already drops to `appuser`.

- [ ] 🟢 Prompt injection surface is unhardened — *added 8/19, from codebase audit*
  - Transcript and chat text are interpolated directly into prompts (`summary/task.py`, `ramq_codes/task.py`, `ramq_chatbot/engine.py`) with only section headers, no delimiter/escaping scheme. Low impact today given JSON-schema output + mandatory physician review downstream.

## ✨ Features

- [ ] 🟡 Let the physician settle a panel-size question once, from the review page — *added 10/6, from the review-page rework*
  - A `needs_confirmation` like « Confirmer la taille exacte de la clientèle inscrite… » comes back on every encounter dated before the physician's first profile version: `BillingContextBuilder` falls back to the earliest version as an *assumed* panel size, which never filters (`PhysicianContext.is_assumed`). The profile page can't fix it today: `ProfileService.record_practice_facts` is only called with `effective_from = today`.
  - Wanted: (1) put the run's `unresolved_axes` (computed by `UnresolvedAxisDetector`, today only logged in `retriever.py`) on `BillingCodesResult` as a server-only field, so the review page knows deterministically that panel size is the open question instead of matching the model's free text; (2) a "En vigueur depuis" date on the profile form; (3) on the review page, one banner per run linking to the profile, then « Relancer l'extraction » once it's set.

- [ ] 🟡 Group a code's variants into one choice on the review page — *added 10/6, from the review-page rework*
  - Variants of one act that differ only on an unresolved axis (e.g. 15841/15842/15843, panel size) are proposed as separate cards in `frontend/src/pages/app/review/CodesReview.tsx`, each with its own checkbox, so the physician can tick two and bill both. Wanted: one card per act with a radio choice of variant, and the `needs_confirmation` text shown once. Needs a family key on `ExtractedCode` (server-only, like `fees`), derived from the code table (the shared `header_path`/family `ramq_codes` already uses for eligibility), not guessed by the frontend from descriptions. Also guard `ClaimService` against two variants of one family on the same claim.

- [ ] 🟡 Enforce the free plan's 1 extraction per day — *added 10/2, from the public-site work*
  - The pricing page (`frontend/src/site/pricing.ts`) advertises a Gratuit plan limited to 1 extraction per day, but nothing enforces it. Needs a plan on `User` (or a dated plan history, like practice facts) and a daily quota check on `POST /extract` and in the extraction worker, counted per physician over the Montreal day (`Clock`), with a clear message in the app when the limit is reached.

- [ ] 🟡 Retune `similarity_top_k`/`fused_top_k` for the full-manual codes table — *added 9/30, from the versioned-codes-table migration*
  - `RAMQCodesRetriever` still uses `similarity_top_k=20`, `fused_top_k=40`, sized for the old 362-row, section-B-only table; `codes_2026-06-05` is 4,070 rows across B–V. The eligibility prefilter frees slots that ineligible variants used to take, but that's no substitute for measuring. Run `scripts/eval_extraction.py --retrieval-only` on 2+ cases (per the "a fix validated on one transcript can regress another" rule) before changing either number — `URG-2026-04512`'s `01320…` procedure codes can now appear at all.

- [ ] 🟡 Carry `manual_rev` on code results and claims — *added 9/30, deferred from the versioned-codes-table migration*
  - The `code_versions` registry names each table's `manual_rev`. Not carried anywhere yet: `CodeVersionRow` is read, but `Code`/`ExtractedCode`/`claim_codes` don't record which manual edition a suggestion came from.
  - Wanted: `manual_rev` on `Code`/`ExtractedCode` (extraction result JSON, no migration), `get_by_number(number, manual_rev=None)` opening that revision's `table_name` from the registry (explaining a claim billed under an older manual). 9/30: `claim_codes.manual_rev` now exists and `ClaimService` already copies `StoredCandidate.manual_rev` into it — it's NULL only because nothing upstream sets it yet.

- [ ] 🟢 Replace the remaining `window.confirm` calls with `useConfirm` — *added 10/6, from the review-page rework*
  - The encounter page now asks through `components/ConfirmDialog.tsx`'s `useConfirm`. Still on the browser's dialog: `PatientsPage.tsx` (remove from roster), `FacturationPage/BillsTab.tsx` (delete a bill), `FacturationPage/RecordsTab.tsx` (delete a claim), `InboxPage/EncounterRowItem.tsx` (delete an encounter). Their tests spy on `window.confirm` and need to click the dialog instead.

- [ ] 🟢 Frontend E2E: more journeys, and a nightly run — *added 10/4, from the frontend test plan*
  - Playwright in `frontend/e2e/` covers 3 journeys (extract → pick codes → save the claim; paste a note → associate the patient; bill the saved claims → PDF). `npm run e2e` needs `backend/.env`'s `MISTRAL_API_KEY` and `DB_PATH`, since retrieval embeddings still hit the real Mistral API.
  - Not done: it isn't in CI (needs a nightly/manual workflow with secrets, or a fake embedding server); the e2e files aren't covered by `tsc -b` (`tsconfig.json` only includes `src`); no journeys for the chat, patients page or duplicate handling.
  - Known limits of the unit suite: jsdom's `FormData` doesn't stream into Node's fetch, so the upload test only checks the multipart content type; there are no visual/layout tests.

- [ ] 🟢 Contact requests have no admin screen — *added 10/2, from the public-site work*
  - `POST /contact` saves to `contact_requests` and emails `CONTACT_NOTIFY_EMAIL` when SMTP is configured; otherwise requests are only in the DB. A small admin-only list (and a retention purge, per the privacy policy) would follow.

- [ ] 🟢 Paginate the inbox for long periods — *added 10/1, from the step 11 period filter*
  - `GET /encounters` with no bounds ("Tout") loads every encounter, its latest run's results and its patient in one response, and the duplicate flagging is O(n²) over them. Fine for weeks of notes; for a year of them, add a limit/cursor (and keep "Tout" paged) or cap the preset.

- [ ] 🟢 Let the physician backdate their profile ("En vigueur depuis") — *added 10/1*
  - The first profile version is dated the day it's entered, so encounters before onboarding only get an assumed panel size (see the cold-start item in Done). `ProfileService.record_practice_facts` already takes `effective_from`; expose it on the profile form/API (default today) so the physician can say when the facts started and `as_of` finds a real version.

- [ ] 🟢 Show ingestion's `needs_review`/`review_reason` to the physician — *added 9/30, deferred from the versioned-codes-table migration*
  - 135 rows of `codes_2026-06-05` are flagged by ingestion as ambiguous/incomplete. Not selected by `CodeRepository` today. Could flow through `Code` into `ExtractedCode` as a server-only field and show as a small "fiche RAMQ à vérifier" warning in `CodesReview.tsx` (not sent to the LLM).

- [ ] 🟢 Measure per-candidate prompt cost with the deeper `header_path` and procedure `rules` — *added 9/30*
  - `_format_candidate` (`app/ramq_codes/task.py`) prints `header_path` verbatim (now up to ~7 segments) and every rule; procedure-section codes can carry long `rules`. Check the token cost of a 40-candidate prompt on the real table before deciding whether to trim either.

- [ ] 🟢 LLM usage logging (token counts, execution time) — *added 8/27*
  - Today `app/extraction/engine.py`'s `run_extraction` only debug-logs the call's duration (`llm_duration_ms`); token usage isn't read and nothing is persisted.
  - Every extraction LLM call already funnels through one chokepoint, `app/extraction/engine.py`'s `run_extraction` (`client.achat(...)`), and `ramq_chatbot/factory.py` builds its own `MistralAI` client the same way — so either option below is a single integration point, not scattered instrumentation.
  - Decide between: (a) self-hosted Langfuse, using its `llama_index` instrumentor (`LlamaIndexInstrumentor` from `langfuse.llama_index`, started once in `bootstrap.py`) for full traces/dashboards/cost aggregation, vs (b) lightweight DB logging — wrap the `achat` call with `time.perf_counter()`, read `response.raw["usage"]` (Mistral's API is OpenAI-compatible), and persist onto the stage's `extraction_results` row (`ExtractionRunResult`, `app/postgresdb/models.py`).
  - Self-hosted Langfuse means another service to run/maintain but gets a UI, prompt diffing, and cost views; DB logging is zero new infra and keeps prompt/response content off any third-party system (relevant here since transcripts carry patient name + NAM), but you build your own queries/views to look at it.

## 🧹 Cleanup / Dead code

- [ ] 🟢 `FacturationPage`'s `reloadSignal` is redundant — *added 10/4, from the frontend tests*
  - Only one tab is mounted at a time, so the tab the physician switches to remounts and fetches fresh anyway; bumping `reloadSignal` after a bill is created or deleted changes nothing observable (removing `onChanged` in `BillsTab` leaves every test green). Drop the signal, or keep both tabs mounted if the intent was to avoid refetching on every switch.

- [ ] 🟢 `formatClinicTime`'s comment says "HH:MM" but it renders "09 h 05" — *added 10/4, from the frontend tests*
  - `frontend/src/utils/date.ts` uses the `fr-CA` locale, so the output is `09 h 05` (and the separator whitespace varies by ICU version). Probably intended for a French UI; fix the comment, or switch to `hour12: false` with `en-CA` if a strict HH:MM is wanted. `date.test.ts` asserts the current output.

## ✅ Done

- [x] 🟢 A failed bill deletion hides the bills list — *added 10/4, from the frontend tests*
- [x] 🔴 The public site is behind the IP allowlist — *added 10/2, from the public-site work, done 10/6*
- [x] 🟡 Rate limits see every visitor as Caddy — *added 10/2, from the public-site work, done 10/6*
- [x] 🟡 Login timing side-channel enables user enumeration — *added 8/19, from codebase audit, fixed 10/6*
- [x] 🟡 Argon2 verify blocks the event loop on every login — *added 8/19, from codebase audit, fixed 10/6*
- [x] 🟡 `GET /dashboard` reads the physician's whole encounter history on every load — *added 10/5, from the dashboard work, done 10/6*
- [x] 🟢 Ownership guard copy-pasted across repository methods — *added 8/24, from billing-workflow code review, reworded 9/30, obsolete 10/6*
- [x] 🟢 `patients/router.py` and `extraction/router.py` skip the factory/`Depends` DI pattern — *added 8/24, from billing-workflow code review, reworded 9/30, partly fixed 9/30, obsolete 10/6*
- [x] 🟢 `encounter_id` accepted, validated, then discarded — *added 8/19, from codebase audit, obsolete 10/6*
- [x] 🟢 A few independent DB round trips are awaited sequentially instead of concurrently — *added 8/24, from billing-workflow code review, won't fix 10/6*
- [x] 🟢 Unused dependency: pandas — *added 8/19, from codebase audit, fixed 10/6*
- [x] 🟢 Unused "ghost" button variant — *added 8/19, from codebase audit, reworded 9/30, obsolete 10/6*
- [x] 🟢 Unused `tagline` prop — *added 8/19, from codebase audit, fixed 10/6*
- [x] 🟡 Serve Epic's JWK Set from the backend instead of a gist — *added 10/3, from the Epic sandbox connector (intake step 11b), fixed 10/6*
- [x] 🟡 A failed `/auth/me` logs the physician out of the UI — *added 10/4, from the frontend test plan, fixed 10/4*
- [x] 🟡 API errors with a non-JSON body and no status text had an empty message — *added 10/4, from the first frontend test, fixed 10/4*
- [x] 🟢 Slash-date parsing assumes `DD/MM/YYYY`, would misparse an Epic-style `MM/DD/YYYY` note — *added 8/24, from billing-workflow code review, fixed 10/1*
- [x] 🟢 Remove `MISTRAL_EMBEDDING_MODEL` from `.env` — *added 8/21, superseded 10/1*
- [x] 🟢 `test_retrieve_includes_section_referenced_by_a_top_hit_even_when_it_ranks_last` fails with `KeyError: 'is_expansion'` — *added 9/30, fixed 10/1*
- [x] 🟡 Physician-profile cold-start fallback treated a guess as a fact — *added 8/31, from billing_codes context propagation bug report, fixed 10/1*
- [x] 🟡 Schema upgrade batch, once Alembic lands — *added 9/30, from database review, done 9/30*
- [x] 🔴 A claim can be saved against a different patient than its extraction was built for — *added 9/30, from database review, fixed 9/30*
- [x] 🟡 Three different strategies for the same enum problem — *added 8/27, from schema review, fixed 9/30*
- [x] 🟡 Deleting a bill, then its claims, destroys the audit trail — *added 8/24, reworded 9/30, fixed 9/30*
- [x] 🔴 NAM stored un-normalized — breaks global uniqueness — *added 9/30, from database review, fixed 9/30*
- [x] 🟡 SQLite never enforces foreign keys — *added 9/30, from database review, fixed 9/30*
- [x] 🟡 `claims → extraction_records` FKs will block the retention purge — *added 9/30, from database review, fixed 9/30*
- [x] 🟡 `ProfileService.update` writes its two halves in separate transactions — *added 9/30, from database review, fixed 9/30*
- [x] 🟢 "Today" is the container's UTC date — *added 9/30, from database review, fixed 9/30*
- [x] 🟢 `DELETE /claims/{id}` 404s with "Facture introuvable" — *added 9/30, from database review, fixed 9/30*
- [x] 🟡 Database layer refactor — *added 9/30, done 9/30, from database review*
- [x] 🟡 `codes.header_path` is now per code and deeper; family grouping and prompts read it — *added 9/28, done 9/30, reworked 9/29 from ramq-ingestion's model-written sub-paths*
- [x] 🟡 Read the new `role`/`unit` fee fields from the `codes` table — *added 9/28, done 9/30, from ramq-ingestion's role-column change*
- [x] 🟡 Read the current codes table from ramq-ingestion's `code_versions` registry — *added 9/29, done 9/30, from ramq-ingestion's versioned codes tables*
- [x] 🔴 `codes` LanceDB table covers only manual section B — *added 8/29, done 9/30, from billing_codes retrieval/prompt optimization*
- [x] 🟡 Code-family disambiguating axes are free text, not typed columns — *added 8/29, done 9/30, from billing_codes retrieval/prompt optimization*
- [x] 🟡 NAM matching scans the whole roster instead of an indexed lookup — *added 8/24, from billing-workflow code review, obsolete 8/31*
- [x] 🟡 No server-side check that returned billing codes are from the candidate set — *added 8/19, from codebase audit, note added 8/24, done 8/29*
- [x] 🟢 No unique constraint on `(physician_id, ramq_number)` on `patients` — *added 8/24, done 8/27, from billing-workflow code review*
- [x] 🟡 `extraction_records.result_json` is `Text`, not JSONB — *added 8/27, done 8/27, from schema review*
- [x] 🟢 Timestamp defaults are Python-side only — *added 8/27, done 8/27, from schema review*
- [x] 🟢 Index gaps on the per-physician list queries — *added 8/27, done 8/27, from schema review*
- [x] 🟢 `is_deleted` bool loses *when* a record was removed — *added 8/27, done 8/27, from schema review*
- [x] 🟢 No `pool_pre_ping` on the Postgres engine — *added 8/27, done 8/27, from schema review*
- [x] 🟡 No `ondelete` on any foreign key — *added 8/27, done 8/27, from schema review*
- [x] Split `users` into credentials + dated physician profile — *added and done 8/27, from schema review*
- [x] 🔴 Vector search blocks the event loop — *added 8/19, from codebase audit, done 8/25*
- [x] 🟢 Docker's default `json-file` log driver has no rotation — *added 8/21, moved from DEPLOY.md, done 8/24*
- [x] 🟡 Add a data logger for production — *added 8/21, done 8/24*
- [x] 🟢 DEPLOY.md and nginx's allowlist behavior disagree — *added 8/19, from codebase audit, done 8/21*
- [x] Rate-limit bypass via X-Forwarded-For spoofing — *added 8/19, done 8/18, from codebase audit*
- [x] Chat history grows unbounded, no truncation — *added 8/19, done 8/19, from codebase audit*
- [x] Chatbot's BM25 index builds synchronously on first request — *added 8/19, done 8/19, from codebase audit*
- [x] Chat bubbles re-parse markdown on every new message — *added 8/19, done 8/19, from codebase audit*
- [x] Two sequential Postgres writes tail every extraction — *added 8/19, done 8/19, from codebase audit*
- [x] Money is a Python float end to end — *added 8/27, done 8/27, from schema review*
- [x] No DB-level guarantee that a claim's patient belongs to its physician — *added 8/27, done 8/27, from schema review*

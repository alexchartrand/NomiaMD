# Backlog

## How to use this
- Add new items under the right section.
- When done (or obsolete), check it off `[x]` and move it to the top of ✅ Done with its title line only — drop the description (git history keeps it).
- Keep each open section ordered by priority (🔴, then 🟡, then 🟢); newest on top within a priority.
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🔴 No two-factor login — *added 10/7, from opening `ALLOWED_CIDRS` to everyone*
  - Physicians use the app from hospitals, clinics, home and cellular, so `ALLOWED_CIDRS` has to be `0.0.0.0/0,::/0` and the IP allowlist no longer protects anything. Email + password (`app/auth/`) is now the only barrier in front of patient data. Add TOTP (authenticator app) at login, with recovery codes and an admin reset in `scripts/reset_password.py`'s style.
  - Acceptable while the app holds only synthetic data; must be done before real patient data (Law 25's "reasonable security measures" for remote access to health data).

- [ ] 🔴 No purge/retention policy on `encounters` — *added 8/21, moved from DEPLOY.md, escalated 8/24, escalated 8/29, reworded 9/30, retargeted 10/1*
  - The note text lives in `encounters.note_text` (with the patient's name and NAM verbatim), so the encounter is the purge target. Deleting one cascades to its runs and their results and sets `claims.extraction_run_id` to NULL; claims keep `source_note_hash`/`external_note_id`. `encounters.purge_after` (indexed) exists but nothing sets or acts on it — pick the retention period, set it where encounters are created, and add the job (intake step 05).
  - Acceptable while demoing with the synthetic notes in `consultations/`; must be done before this ever touches real patient data (Law 25). The NAM is scrubbed from the *prompt* (`app/patients/nam.py`'s `redact`), not from what's stored.

- [ ] 🔴 No Alembic — schema changes require a DB wipe or a hand-run `ALTER TABLE` — *added 8/24, escalated 8/27, deferred 9/30*
  - `init_db()` only runs `Base.metadata.create_all`, which creates missing tables but never alters an existing one.
  - Decided 9/30: not needed until the next release — every existing DB (local SQLite and the demo Postgres) is deleted and recreated on a schema change until then. Adopt Alembic (with the current schema as its baseline revision) before the first release that holds data worth keeping; it gates going live.

- [ ] 🟡 Login brute force is only limited per IP — *added 10/7, from opening `ALLOWED_CIDRS` to everyone*
  - `POST /auth/login` is `@limiter.limit("10/minute")` keyed on `get_remote_address` (`app/rate_limit.py`), so an attacker rotating IPs gets 10 guesses/minute per address against one account, with nothing tracking failures per account. Add a per-account counter (exponential delay or temporary lockout after N failures, reset on success), and log failed attempts.

- [ ] 🟡 No password policy, and 30-day sessions can't be revoked — *added 10/7, from opening `ALLOWED_CIDRS` to everyone*
  - `scripts/create_user.py` and `reset_password.py` accept any password, even one character. Enforce a minimum length (≥ 12) and reject common/breached passwords.
  - Sessions are stateless JWTs: 12 h by default, 30 days with "Rester connecté" (`JWT_REMEMBER_ME_EXPIRY_SECONDS`, `app/auth/security.py`). Nothing invalidates one before it expires — not a password reset, a logout on another device, or a lost phone. Shorten the remember-me lifetime and add a revocation hook (e.g. a per-user `token_version` claim bumped on password reset).

- [ ] 🟡 ER notes retain the wrong ER visit variant — *added 10/9, from the `er-b-pinned-clarified` benchmark*
  - The ER subsection's visit codes are now pinned at the top of the candidates, and the prompt says that an ER code's « patient inscrit » means registered at the ER, not with this physician (without it the model ruled every ER code out). On the 7 URG notes overall recall went 36% → 64%, but retained recall stays 2/11: the model picks « ordinaire » where the label says « principal » (04471, 04538) and « avec déplacement » where it says « sans » (04512, 04621, 04622). `backend/benchmarks/README.md`, *ER notes: pinning and « patient inscrit »*.
  - First check the labels with a physician (the ER entries are drafts or `to_review`; see "Physician review of the selection judgment calls"). Then, if the labels hold: « sans déplacement » is presumably the default for a physician on shift at the ER (to confirm in that review), so it could be stated with the care setting; principal vs ordinaire needs the manual's definition in front of the model (the candidates' `rules`).
  - The « patient inscrit » wording is upstream data: ramq-ingestion could say what it means in the ER rows' `when_to_use`/`rules`, and the prompt line could then go.

- [ ] 🟡 Eligibility can't see several RAMQ conditions the new eval notes hit — *added 10/7, from labeling `consultations/` 26-58*
  - **Care setting isn't an eligibility axis.** Since 10/9 `BillingContext.care_setting` exists (from the note's source or the physician, `app/care_setting.py`), but it only adds an ER-scoped visit query and a prompt line; nothing filters on it. CHSLD (`15615`-`15625`) and ward (`15638`-`15655`) codes still compete with cabinet visits, and the model alone decides. They could get their own subsection in `CARE_SETTING_VISIT_SECTIONS` (`visit_query.py`) like the ER; a real filter needs a codes column for it (`fees[].lieux` partially encodes it), so a ramq-ingestion change first.
  - **Vulnérable tariff is reserved to the treating physician or their group** (P.G. 2.2.6 A a). Eligibility treats `is_vulnerable` as a plain patient attribute, so a clinically vulnerable patient seen by another physician (home-care doctor, walk-in) gets only the vulnérable variants — the right non-vulnérable code is filtered out (eval entry `DOM-2026-00022` sets `is_vulnerable=false` to get around it).
  - **Physician designations aren't practice facts.** `08775`-`08777` (MSK) need a comité-paritaire designation; ward visits split by the unit's level A/B (annexe XXII 2.01). Neither is in `PracticeFacts`, so both variants are always offered (several `to_review` entries hinge on these).
  - The ER-code `requires_registered` data bug is fixed upstream (ramq-ingestion, 10/8). `codes_2026-09-17` now has `requires_registered=True` only on the 27 « patient (non) vulnérable inscrit » visits (`15801`-`15840`); the ER, clinique externe/CH, « patient admis » and `15188`/`15841`-`15846` rows are null. Re-score the eval entries labeled around it.

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

- [ ] 🟡 Read the care setting from Epic encounters — *added 10/9, from the care-setting work*
  - `EncounterMeta.care_setting` is only set by paste/upload today. Epic doesn't expose a standard code for it: the sandbox's `Encounter.class` is Epic-local ("Support OP Encounter") and its location a department name ("EMC Family Medicine"). Add a per-site mapping (department or class → `CareSetting`) to `EpicNoteMapper`; unmapped = unknown. A schedule-entry connector would fill the same field.

- [ ] 🟡 Let the physician pick the care setting — *added 10/9, from the care-setting work*
  - `POST /intake/notes` (`PastedNotes.care_setting`) and `/intake/upload` (`care_setting` form field) take it, applied to every note of the batch, but the frontend doesn't send it yet. Add the picker to `/app/ajouter`'s paste/upload form, and a way to set or correct it on the encounter page (then re-extract). `POST /extract` has no field for it yet either.

- [ ] 🟡 Benchmark ramq-ingestion's Bedrock candidate tables — *added 10/8, from ramq-ingestion's model comparison*
  - ramq-ingestion now builds candidate tables beside the current one, `codes_<rev>__<variant>`: another model's extraction (Claude/Nova on Bedrock) and/or another embedding model (Cohere Embed v4). Each is registered in `code_versions` with `is_current=false`, so `scripts/benchmark.py run --codes-table codes_<rev>__<variant>` can pin it. Compare it with a control run on the current table made with the same code (`benchmarks/runs/current-table-sel`), not with `mistral-sel-2026-10-v3`: that baseline predates the ER data fix and `HybridSearch`.
  - `codes_2026-09-17__claude-sonnet-4-6` done 10/9 (`sonnet-sel`): no better. Selection is within noise (43 vs 46 correct retained codes), retrieval MRR falls from 0.32 to 0.27 because visit codes rank lower, and it costs 10% more input tokens. Details in `benchmarks/README.md`, "Codes tables".
  - Registry rows are now keyed by `table_name` (several per `manual_rev`), and there is a new nullable `embedding_model` column (e.g. `mistral:mistral-embed`, `bedrock:cohere.embed-v4:0`). Each codes table's schema metadata carries `embedding_model` too. `CodeVersionRow` ignores the extra field (pydantic default), so nothing breaks today.
  - Extraction-only variants (Mistral embeddings) run as-is. An embedding variant (`codes_<rev>__…` built with `bedrock:cohere.embed-v4:0`) runs with `EMBEDDING_PROVIDER=bedrock EMBEDDING_MODEL=cohere.embed-v4:0` (done 10/9: `app/llm/bedrock.py`, and `EmbeddingModelGuard` now refuses a table recording another model). None is built yet; only the run is left.

- [ ] 🟡 Measure the selection benchmark's noise floor — *added 10/8, from the `mistral-sel` analysis*
  - `mistral-medium` isn't deterministic at temperature 0 (the summary already moved a code's rank between two identical runs). Before reading small per-note deltas between two selection prompts as real, re-run one unchanged configuration (`run --name <x>-rerun --stages selection --candidates-from mistral-2026-10-v2`) and compare it with `report --baseline`: whatever changes there is noise. A `--repeat N` on `run` would make this routine.

- [ ] 🟡 Show each candidate's eligibility bounds in the billing_codes prompt — *added 10/8, from the `mistral-sel` analysis*
  - `_format_candidate` (`app/ramq_codes/task.py`) shows the taxonomy path, description, usage and conditions, so what tells sibling variants apart (age band, panel size, registered/vulnerable) is buried in French prose. `mistral-sel` retained 18 wrong variants of an expected code. Render `Code.eligibility`'s typed bounds as one line per candidate (e.g. « Admissibilité : 80 ans ou plus ; patient inscrit ; clientèle ≥ 500 »), then measure with `run --stages selection --candidates-from mistral-2026-10-v2 --baseline <previous>` (wrong variants, retained precision).

- [ ] 🟡 Physician review of the selection judgment calls — *added 10/8, from the `mistral-sel` analysis*
  - Five expected codes the model saw and didn't pick look like label questions as much as model errors: `GMF-2026-00303` 15813 vs 15833 (periodic vs pediatric intake), `GMF-2026-00313` 15803 vs 08819 (follow-up vs psychiatric evaluation), `HOP-2026-00733` 15639 vs 15638 (follow-up vs intake on the ward), `CHSLD-2026-00054` 15622 (phone response), `CLI-2026-01229` 15803 (the model picked hospital code 08882). Also the negatives that came back with codes, `CLI-2026-01246`'s insurer form above all (09826 at high confidence). Settle them in `tests/fixtures/eval_billing_codes.jsonl` before tuning the prompt against them.

- [ ] 🟢 Check server-side that a code's supporting quote is in the note — *added 10/8, from the `mistral-sel` analysis*
  - The prompt asks for a verbatim `supporting_quote` from the summary or transcript, but nothing checks it. A deterministic check in `BillingCodesTask.parse` (whitespace/case-normalized substring of the rendered summary or the transcript) would flag a made-up quote on the review card rather than drop the code. Count the flagged quotes in the selection benchmark first, to see whether it happens at all.

- [ ] 🟡 Seed demo encounters relative to today — *added 10/6, from the app demo polish*
  - `scripts/seed_db.py` seeds the `consultations/` notes at the dates written in them (spring–summer 2026), so on a demo day the dashboard shows 0 encounters this week, an empty 8-week activity chart, and every unbilled note at "5 j restants" before the 90-day limit; the inbox's default "Cette semaine" period is empty too. Wanted: an opt-in seed mode (e.g. `--relative-to-today`) that spreads the encounters over the last ~3 weeks, several per day, so the dashboard, the day cards and the bulk-approve callout all have something to show.

- [ ] 🟡 Let the physician settle a panel-size question once, from the review page — *added 10/6, from the review-page rework*
  - A `needs_confirmation` like « Confirmer la taille exacte de la clientèle inscrite… » comes back on every encounter dated before the physician's first profile version: `BillingContextBuilder` falls back to the earliest version as an *assumed* panel size, which never filters (`PhysicianContext.is_assumed`). The profile page can't fix it today: `ProfileService.record_practice_facts` is only called with `effective_from = today`.
  - Wanted: (1) put the run's `unresolved_axes` (computed by `UnresolvedAxisDetector`, today only logged in `retriever.py`) on `BillingCodesResult` as a server-only field, so the review page knows deterministically that panel size is the open question instead of matching the model's free text; (2) a "En vigueur depuis" date on the profile form; (3) on the review page, one banner per run linking to the profile, then « Relancer l'extraction » once it's set.

- [ ] 🟡 Group a code's variants into one choice on the review page — *added 10/6, from the review-page rework*
  - Variants of one act that differ only on an unresolved axis (e.g. 15841/15842/15843, panel size) are proposed as separate cards in `frontend/src/pages/app/review/CodesReview.tsx`, each with its own checkbox, so the physician can tick two and bill both. Wanted: one card per act with a radio choice of variant, and the `needs_confirmation` text shown once. Needs a family key on `ExtractedCode` (server-only, like `fees`), derived from the code table (the shared `header_path`/family `ramq_codes` already uses for eligibility), not guessed by the frontend from descriptions. Also guard `ClaimService` against two variants of one family on the same claim.

- [ ] 🟡 Enforce the free plan's 1 extraction per day — *added 10/2, from the public-site work*
  - The pricing page (`frontend/src/site/pricing.ts`) advertises a Gratuit plan limited to 1 extraction per day, but nothing enforces it. Needs a plan on `User` (or a dated plan history, like practice facts) and a daily quota check on `POST /extract` and in the extraction worker, counted per physician over the Montreal day (`Clock`), with a clear message in the app when the limit is reached.

- [ ] 🟡 Retune `similarity_top_k`/`fused_top_k` for the full-manual codes table — *added 9/30, from the versioned-codes-table migration*
  - `RAMQCodesRetriever` still uses `similarity_top_k=20`, `fused_top_k=40`, sized for the old 362-row, section-B-only table; `codes_2026-06-05` is 4,070 rows across B–V. The eligibility prefilter frees slots that ineligible variants used to take, but that's no substitute for measuring. Measure with `scripts/benchmark.py sweep --summaries-from <run> --similarity-top-k … --fused-top-k …` over all labeled notes, and check `report --baseline` for per-note regressions (the "a fix validated on one transcript can regress another" rule) before changing either number — `URG-2026-04512`'s `01320…` procedure codes can now appear at all.

- [ ] 🟡 Carry `manual_rev` on code results and claims — *added 9/30, deferred from the versioned-codes-table migration*
  - The `code_versions` registry names each table's `manual_rev`. Not carried anywhere yet: `CodeVersionRow` is read, but `Code`/`ExtractedCode`/`claim_codes` don't record which manual edition a suggestion came from.
  - Wanted: `manual_rev` on `Code`/`ExtractedCode` (extraction result JSON, no migration), `get_by_number(number, manual_rev=None)` opening that revision's `table_name` from the registry (explaining a claim billed under an older manual). 9/30: `claim_codes.manual_rev` now exists and `ClaimService` already copies `StoredCandidate.manual_rev` into it — it's NULL only because nothing upstream sets it yet.

- [ ] 🟢 Open an encounter's review from its claim in Facturation — *added 10/6, from the app demo polish*
  - A claim saved from an encounter can only be edited from its review, but `ClaimOut` carries no `encounter_id`, so the claims table can't link to it (only "Sans rencontre" drafts get a « Modifier »). Add a read-only `encounter_id` (claim → extraction run → encounter, `None` once the run is purged) and a « Ouvrir la rencontre » row action.

- [ ] 🟢 An « Insérer une note d'exemple » button on Ajouter — *added 10/6, from the app demo polish*
  - Would let a demo show the paste flow without hunting for a note, but every `consultations/` note is already seeded, so pasting one is ignored as a duplicate. Needs demo-only notes kept out of the seed (or a fresh synthetic one generated per click).

- [ ] 🟢 Small screens in the app — *added 10/6, from the app demo polish*
  - The app targets 1280px+ laptops: the sidebar is a fixed 240px column with no collapse, and the review's note docks beside the codes only from 1200px (below that it folds under them). A collapsible sidebar (sheet under ~1024px) and a scroll-safe table layout would cover tablets.

- [ ] 🟢 Frontend E2E: more journeys, and a nightly run — *added 10/4, from the frontend test plan*
  - Playwright in `frontend/e2e/` covers 3 journeys (extract → pick codes → save the claim; paste a note → associate the patient; bill the saved claims → PDF). `npm run e2e` needs the root `.env`'s `EMBEDDING_API_KEY` and `DB_PATH`, since retrieval embeddings still hit the real Mistral API.
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

- [ ] 🟢 Persist LLM usage (token counts, execution time) — *added 8/27, reworded 10/8*
  - Since 10/8 every chat and embedding call is metered by `app/llm/openai_client.py` (`LLMCallRecord`: tokens in/out, latency, purpose, `finish_reason`) and logged as one structured `llm_call` line (`app/llm/usage.py`); the benchmark collects them per note with `usage_scope()`. Nothing is persisted yet.
  - Remaining: a `UsageRecorder` sink that stores the records of an extraction on its run (a `llm_calls` table keyed to `ExtractionRun`, or a JSON column on `ExtractionRunResult`), so cost per encounter/physician can be queried. Langfuse stays an option, but would need its OpenAI-SDK integration now that llama-index is gone.

## 🧹 Cleanup / Dead code

- [ ] 🟢 Flaky frontend tests under full-suite load — *added 10/7, from the `reloadSignal` cleanup*
  - `FacturationPage.test.tsx`'s first test ("marks a claim billed without an encounter…") takes ~0.7s alone but often hits vitest's 5s timeout in a full `npm test` run, with or without the 10/7 change. `EncounterPage.test.tsx`'s "saves and opens the next encounter, saying whose claim was saved" failed once the same way. Find what the first test is waiting on (cold module/portal import under 37 parallel jsdom workers?) before reaching for a bigger `testTimeout`.

- [ ] 🟢 `formatClinicTime`'s comment says "HH:MM" but it renders "09 h 05" — *added 10/4, from the frontend tests*
  - `frontend/src/utils/date.ts` uses the `fr-CA` locale, so the output is `09 h 05` (and the separator whitespace varies by ICU version). Probably intended for a French UI; fix the comment, or switch to `hour12: false` with `en-CA` if a strict HH:MM is wanted. `date.test.ts` asserts the current output.

## ✅ Done

- [x] 🟡 ER visit codes are eligible but never retrieved — *added 10/9, from the `sonnet-sel` benchmark, done 10/9*
- [x] 🟢 Lance prints a deprecation warning on every hybrid code search — *added 10/8, from the benchmark work, done 10/9*
- [x] 🟢 `FacturationPage`'s `reloadSignal` is redundant — *added 10/4, from the frontend tests, done 10/7*
- [x] 🟢 Replace the remaining `window.confirm` calls with `useConfirm` — *added 10/6, from the review-page rework, done 10/6*
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

# Backlog

## How to use this
- Add new items under the right section, newest on top.
- Check off `[x]` when done, but leave the line — don't delete (keeps history).
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🟡 Noisy `unit`/`role` tagging on some `codes_2026-06-05` fees — report to ramq-ingestion — *added 9/30, from the versioned-codes-table migration*
  - `15837` (a B-section visit, no anesthesia) carries a stray `94 unités` fee with `role=2`; `08118` (radiology) has `role=1, unit="unités"` on `4.55`, which has decimals and so reads like a dollar amount. Of the 6,948 fees, 101 are `role=1` in units and 11 are `role=2` in dollars — worth a spot check upstream.
  - The failure mode on this side is safe (a unit fee is never billed as dollars, the physician sees the label), but a mis-tagged dollar fee shows as units and drops out of the total.

- [ ] 🟢 `test_retrieve_includes_section_referenced_by_a_top_hit_even_when_it_ranks_last` fails with `KeyError: 'is_expansion'` — *added 9/30*
  - `tests/test_ramq_chatbot_retriever.py`. Still failing on 9/30 (the other 8 tests in that file pass). Fails identically on `dev` before the versioned-codes-table change, so it's unrelated to it. Looks like the test still expects expansion metadata the chatbot retriever no longer sets.

- [ ] 🟡 Physician-profile cold-start fallback needs revalidation once real profile history exists — *added 8/31, from billing_codes context propagation bug report*
  - Root cause, confirmed against a real local run (`extraction_records` #9/#10): the physician's only `physician_profiles` row has `effective_from=2026-08-27`; the tested encounter is dated `2026-05-26`. `ProfileService.as_of` correctly (by its own "interpret a past encounter under the facts in effect then" contract) returns no profile for a date before any version existed, so `PhysicianContext` came back all-null and the model couldn't pick between codes 15839/15840 on panel size — exactly the "physician info should have been sent but wasn't" symptom reported.
  - Fixed with a scoped fallback, not a change to the shared historical-accuracy contract: `BillingContextBuilder.build` (`app/ramq_codes/context_builder.py`) now calls the new `ProfileService.earliest`/`PhysicianProfileRepository.get_earliest` (`app/auth/profile.py`, `app/postgresdb/repository.py`) only when `as_of` finds nothing. `get_effective_on`/`as_of` themselves are untouched, so `app/bills/service.py`'s fee-snapshot lookup keeps strict as-of-date accuracy.
  - **This is a real assumption, not just a bug fix — needs revalidation**: treating a physician's current-and-only profile as applicable to an arbitrarily old encounter is fine while every physician has at most one profile version, but once physicians accumulate multiple versions over a career (panel size/remuneration type do change), falling back to the *earliest* version for a pre-history encounter could become a materially wrong estimate rather than a reasonable one. User explicitly chose this trade-off (fall back rather than stay unresolved) when asked — revisit the choice once real multi-version profile data exists.
  - Related, fixed alongside: when the *vulnerability* axis is genuinely unresolved (no roster match — same #9/#10 run, patient "Lefebvre, Madeleine" isn't on this physician's roster), the model was treating the transcript's own descriptive language ("patiente vulnérable inscrite") as if it resolved the axis, returning only the vulnerable-patient code variants (15839/15840) with `needs_confirmation` naming panel size but never vulnerability. `BillingCodesTask.SYSTEM_PROMPT` (`app/ramq_codes/task.py`) now states explicitly that the unresolved-axes list is authoritative and a transcript/summary mention never resolves it on its own — unverified by a further real-API run since this needs a live Mistral call to confirm the model actually complies with the strengthened wording.

- [ ] 🟡 Three different strategies for the same enum problem — *added 8/27, from schema review*
  - `UserRole`/`Gender` are native `Enum(...)`; `PhysicianProfile.physician_type`/`remuneration_type` are `String(255)` shadowing a Python enum; `Claim.status` is `String(16)` validated by a Pydantic `Literal`. All three defensible in isolation, incoherent together.
  - Fix once Alembic lands: native `Enum` for vocabularies this codebase owns (role, gender), `String` + boundary validation for anything RAMQ's vocabulary controls (status, physician/remuneration type).

- [ ] 🟢 NAM stored in plaintext — *added 8/27, from schema review*
  - `patients.ramq_number` and the NAM inside `extraction_records.transcript` are a direct government identifier at rest with no column-level protection. Worth a pgcrypto/application-level encryption decision before real patient data, alongside the retention item above.

- [ ] 🟢 Slash-date parsing assumes `DD/MM/YYYY`, would misparse an Epic-style `MM/DD/YYYY` note — *added 8/24, from billing-workflow code review*
  - `app/extraction/encounter_date.py`'s `_SLASH_DATE_RE` always reads `d/m/y`. Harmless today (Epic/Plume AI sources are still disabled buttons in the UI, and Quebec notes use `DD/MM/YYYY`), but once a US-market EHR source is wired up, a date like "03/04/2026" would silently parse as March 4 instead of April 3 for any day/month both ≤ 12 — no error, just a silently wrong `encounter_date`. Revisit once a real `source.system` other than `simule` sends dates.

- [ ] 🟢 Facturation's patient filter only lists the physician's own roster — *added 8/24, from billing-workflow code review, reworded 9/30*
  - `ClaimRepository.list_for_physician` deliberately doesn't filter `deleted_at` (a deleted patient's past claims keep showing their name), but `FacturationPage/RecordsTab.tsx`'s patient filter dropdown is filled from the physician's roster (`GET /patients`). Since the 8/31 global-patient refactor, claims aren't roster-gated, so any patient billed but never added to (or removed from) "my patients" can't be picked in the filter. Minor; the "all patients" view still shows their claims. Could be filled from the distinct patients on the physician's own claims instead.

- [ ] 🔴 No purge/retention policy on `extraction_records` — *added 8/21, moved from DEPLOY.md, escalated 8/24, escalated 8/29*
  - Stores each transcript + result indefinitely. Acceptable while demoing with the synthetic notes in `consultations/`; must revisit before this ever touches real patient data (Law 25).
  - Escalated: `extraction_records.result_json` used to hold the patient's name **and NAM** as discrete, greppable fields (`patient_information.name_as_stated`/`ramq_number_as_stated`). Those fields were removed on 9/01 with the patient-verification step, but the stored `transcript` column still carries the name and NAM verbatim for both the `consultation_summary` and `billing_codes` rows, so this stays 🔴.
  - Escalated 8/29: `billing_codes` now also grounds its selection in the raw transcript (`app/ramq_codes/task.py`'s `BillingCodesInput`), not just the NAM-stripped rendered summary — the `billing_codes` extraction record's stored result no longer excludes identity the way the summary-only prompt did. A NAM embedded in the transcript is scrubbed before it reaches the *prompt* (`app/patients/nam.py`'s `redact`), but the stored `extraction_records` row still carries the untouched original transcript, same as it always has for the `consultation_summary` stage.

- [ ] 🔴 No Alembic — schema changes require a DB wipe or a hand-run `ALTER TABLE` — *added 8/24, escalated 8/27*
  - `init_db()` only runs `Base.metadata.create_all`, which creates missing tables but never alters an existing one. `patients.is_deleted` (billing-workflow plan Part 4) is the first column added to an existing table since this app went live; the next one needs the same manual `ALTER TABLE` step on prod, or a wipe locally. Adopt Alembic before billing data is real.
  - Escalated 8/27: this is the blocker for every other schema item in this section — none of them are applicable to a live DB without migrations. It's also the stated cause of two existing workarounds (`Claim.status` as a bare `String` instead of an enum; `BillClaim` existing as a table because "a new column on an existing table isn't free"), so adopting Alembic removes the constraint those were designed around. Not urgent while there's no production DB — the local SQLite file is disposable — but it gates going live.

- [ ] 🟡 Deleting a bill, then its claims, destroys the audit trail — *added 8/24, reworded 9/30*
  - Partly fixed: `ClaimService.delete` (`app/claims/service.py`) now refuses any claim that isn't `brouillon` (`ClaimOnBillError`). But `DELETE /bills/{id}` (`BillRepository.delete_for_physician`) hard-deletes the bill and resets its claims to `brouillon`, after which they can be hard-deleted too. Two clicks still erase a claim that was `soumis`. No soft delete exists for either `bills` or `claims` (`patients` has `deleted_at`).

- [ ] 🟢 No backup of the `postgres_data` volume — *added 8/21, moved from DEPLOY.md*
  - Fine for a short-lived demo seeded with synthetic data; take a manual `pg_dump` first if that stops being true.

- [ ] 🟡 Login timing side-channel enables user enumeration — *added 8/19, from codebase audit*
  - `auth/service.py` `login()` returns immediately on `user is None`, but runs the deliberately slow Argon2 `verify()` when the email exists — response time distinguishes valid from invalid emails.
  - Fix: always run a dummy hash verify on the unknown-user path. Low real-world impact given the small, manually-provisioned user base.

- [ ] 🟡 Argon2 verify blocks the event loop on every login — *added 8/19, from codebase audit*
  - `AuthService.login` (async) calls the sync, CPU-slow `PasswordHasher.verify` directly (`auth/security.py`), no `run_in_threadpool`. Stalls the whole process for tens–hundreds of ms, including other physicians' in-flight `/extract`/`/query` requests.

- [ ] 🟢 Backend has no network-level allowlist of its own — *added 8/19, from codebase audit*
  - `docker-compose.yml`: header-spoofing protection depends entirely on nginx being the only path to `backend:8000`. Partially mitigated since S1's fix moved backend to an `internal` network, but backend still has no self-defense if another container joins that network later.

- [ ] 🟢 Non-backend containers run with image-default privileges — *added 8/19, from codebase audit*
  - Postgres/redis/caddy/frontend don't set an explicit non-root `user:` in `docker-compose.yml`. Backend (the real attack surface) already drops to `appuser`.

- [ ] 🟢 Prompt injection surface is unhardened — *added 8/19, from codebase audit*
  - Transcript and chat text are interpolated directly into prompts (`summary/task.py`, `ramq_codes/task.py`, `ramq_chatbot/engine.py`) with only section headers, no delimiter/escaping scheme. Low impact today given JSON-schema output + mandatory physician review downstream.

## ✨ Features

- [ ] 🟡 Retune `similarity_top_k`/`fused_top_k` for the full-manual codes table — *added 9/30, from the versioned-codes-table migration*
  - `RAMQCodesRetriever` still uses `similarity_top_k=20`, `fused_top_k=40`, sized for the old 362-row, section-B-only table; `codes_2026-06-05` is 4,070 rows across B–V. The eligibility prefilter frees slots that ineligible variants used to take, but that's no substitute for measuring. Run `scripts/eval_extraction.py --retrieval-only` on 2+ cases (per the "a fix validated on one transcript can regress another" rule) before changing either number — `URG-2026-04512`'s `01320…` procedure codes can now appear at all.

- [ ] 🟡 Carry `manual_rev` on code results and claims — *added 9/30, deferred from the versioned-codes-table migration*
  - The `code_versions` registry names each table's `manual_rev`. Not carried anywhere yet: `CodeVersionRow` is read, but `Code`/`ExtractedCode`/`claim_codes` don't record which manual edition a suggestion came from.
  - Wanted: `manual_rev` on `Code`/`ExtractedCode` (extraction result JSON, no migration), `get_by_number(number, manual_rev=None)` opening that revision's `table_name` from the registry (explaining a claim billed under an older manual), and eventually a `manual_rev` snapshot on `claim_codes` — which is a schema change blocked on the No-Alembic item above.

- [ ] 🟢 Show ingestion's `needs_review`/`review_reason` to the physician — *added 9/30, deferred from the versioned-codes-table migration*
  - 135 rows of `codes_2026-06-05` are flagged by ingestion as ambiguous/incomplete. Not selected by `CodeRepository` today. Could flow through `Code` into `ExtractedCode` as a server-only field and show as a small "fiche RAMQ à vérifier" warning in `CodesReview.tsx` (not sent to the LLM).

- [ ] 🟢 Measure per-candidate prompt cost with the deeper `header_path` and procedure `rules` — *added 9/30*
  - `_format_candidate` (`app/ramq_codes/task.py`) prints `header_path` verbatim (now up to ~7 segments) and every rule; procedure-section codes can carry long `rules`. Check the token cost of a 40-candidate prompt on the real table before deciding whether to trim either.

- [ ] 🟢 LLM usage/timing logging (token counts, execution time) — *added 8/27*
  - Every extraction LLM call already funnels through one chokepoint, `app/extraction/engine.py`'s `run_extraction` (`client.achat(...)`), and `ramq_chatbot/factory.py` builds its own `MistralAI` client the same way — so either option below is a single integration point, not scattered instrumentation.
  - Decide between: (a) self-hosted Langfuse, using its `llama_index` instrumentor (`LlamaIndexInstrumentor` from `langfuse.llama_index`, started once in `bootstrap.py`) for full traces/dashboards/cost aggregation, vs (b) lightweight DB logging — wrap the `achat` call with `time.perf_counter()`, read `response.raw["usage"]` (Mistral's API is OpenAI-compatible), and persist onto the existing `ExtractionRecord` row (`app/postgresdb/models.py`).
  - Self-hosted Langfuse means another service to run/maintain but gets a UI, prompt diffing, and cost views; DB logging is zero new infra and keeps prompt/response content off any third-party system (relevant here since transcripts carry patient name + NAM), but you build your own queries/views to look at it.

## 🧹 Cleanup / Dead code

- [ ] 🟢 Ownership guard copy-pasted across repository methods — *added 8/24, from billing-workflow code review, reworded 9/30*
  - The patient copies are gone (patients are global since 8/31, no per-physician ownership). What's left: `record is None or record.physician_id != physician_id` twice in `ClaimRepository` and the same check on `bill` twice in `BillRepository` (`app/postgresdb/repository.py`). A future rule change (e.g. "also block if the physician account is deactivated") means updating all four by hand.

- [ ] 🟢 `patients/router.py` and `extraction/router.py` skip the factory/`Depends` DI pattern — *added 8/24, from billing-workflow code review, reworded 9/30*
  - `claims/factory.py` and `auth/factory.py` both expose a `get_*_service()` wired via FastAPI `Depends`, but `patients/router.py` instantiates `PatientRepository()`/`PhysicianPatientRepository()` inline in every handler (no `patients/factory.py`), and `extraction/router.py` does the same for `PatientRepository()` and `ExtractionRepository()`. Not a bug, just an inconsistent seam: swapping or mocking them at the dependency layer (the way tests already do for `ClaimService`) isn't possible without editing the router.

- [ ] 🟢 A few independent DB round trips are awaited sequentially instead of concurrently — *added 8/24, from billing-workflow code review*
  - `ClaimService.create` (`app/claims/service.py`) awaits the patient/extraction/duplicate-check lookups one at a time even though none depends on another's result. `asyncio.gather` would cut the added latency on the claim-save path. Not measured against real Postgres latency, so profile before spending effort here.
  - (The `extraction/router.py` half of this item and the `update_status` re-fetch are gone: patient suggestion was removed on 8/31, and claims no longer have a status-update route.)

- [ ] 🟢 Remove `MISTRAL_EMBEDDING_MODEL` from `.env` — *added 8/21*
  - `config.py`'s `mistral_embedding_model` reads it from env and `embedings.py` passes it straight to `MistralAIEmbedding`, but it must always match whatever model ramq-ingestion used to embed the `codes_<rev>`/`documents-embeddings` LanceDB tables (`mistral-embed`) — changing it doesn't degrade gracefully, it silently breaks retrieval (embedding-space mismatch). Extraction's model names are already hardcoded per task (`ExtractionTask.model`, `app/tasks/base.py`); this should be too, rather than exposed as an operator-configurable env var.

- [ ] 🟢 Unused dependency: pandas — *added 8/19, from codebase audit*
  - Declared in `backend/pyproject.toml`; zero imports anywhere in `app/`, `scripts/`, or `tests/`.

- [ ] 🟢 Unused "ghost" button variant — *added 8/19, from codebase audit, reworded 9/30*
  - `components/Button.tsx` still declares a `ghost` variant (mapped to shadcn's `ui/button.tsx`), but no call site of `components/Button` passes it. The only `variant="ghost"` in the app is in `ui/dialog.tsx`, which uses the shadcn button directly.

- [ ] 🟢 Unused `tagline` prop — *added 8/19, from codebase audit*
  - `components/PageHeader.tsx` renders it, but its only call site `SiteHeader.tsx` never supplies it.

- [ ] 🟢 `encounter_id` accepted, validated, then discarded — *added 8/19, from codebase audit, needs confirmation*
  - `extraction/models.py` / `extraction/router.py` — router only reads `source.system`; `encounter_id` is parsed and never persisted. Frontend sends `source: { system }` only (`frontend/src/api/extraction.ts`), never an `encounter_id`. CLAUDE.md frames multi-source ingestion (Epic/Plume) as part of the design, so may be intentional scaffolding rather than a mistake.

## ✅ Done

- [x] 🟡 `codes.header_path` is now per code and deeper; family grouping and prompts read it — *added 9/28, done 9/30, reworked 9/29 from ramq-ingestion's model-written sub-paths*
  - ramq-ingestion used to give every code its chunk's path, which stops at H2. Since 9/29 the extraction model adds the sub-headings inside each chunk, once per chunk (`path_groups`), and ingestion joins them under the chunk path. 15801 changes from `B — Consultation, examen et visite > Visites sur rendez-vous (patient de moins de 80 ans)` to `… > Patient non vulnérable inscrit > Visite de prise en charge`, like the 8/28 `v2` rows. Procedure sections get their organ/act groups (`… > Nez > Incision`). Column shape is unchanged (one ` > `-joined string). (The rule-based per-code path of 9/28 described in an earlier version of this item was reverted and never reached a table.)
  - **Families should hold again.** Group-label rows that only separate variants of one act (« Clientèle inscrite de moins de 500 patients », lieu) are kept OUT of the path by instruction, so 15801/15802 share one path and one family. It's a model instruction, not a guarantee: after the rebuild, check `CodeFamilySelector` groups on real rows and look for families split by a stray variant label.
  - **Opportunity: some axes are in the path.** « Patient non vulnérable inscrit » and « (patient de moins de 80 ans) » are path segments (panel size is not). `_text()` only reads `description` + `when_to_use`; adding `header_path` would let the filters use them even when the description leaves one out. The typed axis columns (`min_age`…`requires_vulnerable`) are the better source now, though.
  - **Prompt size.** `_format_candidate` (`app/ramq_codes/task.py`) prints `header_path` verbatim. Paths are now longer (up to ~7 segments in B in the 8/28 model-written run), so check the per-candidate token cost.
  - **Fixtures.** `tests/test_ramq_codes_family.py` hand-writes 15801/15802 with the old H2-deep path; the real rows will be deeper. Refresh the fixtures from the rebuilt table.
  - Needs the ingestion side re-extracted and the `codes` table rebuilt (`"overwrite"`) before any of this shows up here.
  - Fixed 9/30 by removing the thing that depended on it: `CodeFamilySelector` no longer exists, so nothing groups by `header_path` any more — variant disambiguation reads the typed eligibility columns instead (see the typed-axes item below). `header_path` is only shown in the prompt now; its per-candidate token cost is tracked separately in Features.

- [x] 🟡 Read the new `role`/`unit` fee fields from the `codes` table — *added 9/28, done 9/30, from ramq-ingestion's role-column change*
  - ramq-ingestion now writes one fee per amount column of the manual's procedure tables. Each `codes.fees` struct gains `role` (int: the raw R number, R = 1, R = 2, R = 7…; null for a single-amount table) and `unit` (`"dollars"` or `"unités"`). An R = 2 fee is the anesthetist's remuneration in **base units, not dollars**: `07520` now carries 1 344,75 $ (role 1) *and* 17 (role 2, unités).
  - Read side to update: `CodeRowFee` (`app/lancedb/models.py`), `app/lancedb/converter.py`, `CodeFee`/`CodeFeeOut` (`app/ramq_codes/models.py`), and the fee mapping in `app/ramq_codes/task.py`. Most important: `app/claims/service.py` turns the chosen fee's `amount` into the claim's `fee_amount`, so an R = 2 fee picked there would bill "17" as $17. Filter or label unit fees before they reach fee selection or any displayed price.
  - Roles mean different things per section (radiology: R = 7 is the laboratory fee, R = 1 the consultation fee, and the two can be billed together for a referred patient), so don't hardcode one meaning per number.
  - The existing `codes` table must be rebuilt with `"overwrite"` on the ingestion side; an `"upsert"` into it fails on the struct mismatch.
  - Fixed 9/30: `CodeRowFee`/`CodeFee`/`CodeFeeOut` carry `role`, `unit` and `lieux` (the old single `lieu` is gone). `ClaimService._fee_amount` (`app/claims/service.py`) snapshots `fee_amount = NULL` for a `unit="unités"` fee and `_fee_when_to_use` records it as e.g. `17 unités — R = 2`; the review UI labels unit fees and leaves them out of the dollar total (`CodesReview.tsx`, `ExtractionPage/index.tsx`). Roles are shown raw, never mapped to one meaning. Pinned by `test_claims.py`'s `test_a_fee_in_units_is_never_billed_as_dollars`.

- [x] 🟡 Read the current codes table from ramq-ingestion's `code_versions` registry — *added 9/29, done 9/30, from ramq-ingestion's versioned codes tables*
  - ramq-ingestion now writes one table per manual revision, `codes_<rev>` (e.g. `codes_2026-06-05`), and keeps older ones for reference. A small `code_versions` table (`manual_rev`, `table_name`, `is_current`, `promoted_at`, `code_count`) marks the current one, which is the only one to retrieve from. Exactly one row has `is_current = true`; ramq-ingestion flips it in a single commit when a new manual is promoted.
  - `app/lancedb/database.py` opens the hard-coded `CODES_TABLE_NAME = "codes"` once at startup. Instead, read `code_versions where is_current` and open that `table_name`. Re-read it per request (or with a short cache) so a promote takes effect without a restart. Fail loudly if no row is current.
  - Retrieval, `get_by_number` and `get_many` keep their logic, pointed at the current table: each revision table has one row per `number`, so no extra filter is needed.
  - Reference lookups: `get_by_number(number, manual_rev=None)` opens `codes_<manual_rev>` when a revision is given (e.g. to explain a claim billed under an older manual).
  - Carry `manual_rev` on code results so answers can cite which manual edition they come from.
  - The old `codes` table goes away once this lands (ramq-ingestion drops it after re-indexing into `codes_2026-06-05` and promoting it).
  - Fixed 9/30: `CurrentCodeTableProvider` (`app/lancedb/code_versions.py`) reads `code_versions where is_current` on every `CodeRepository` call and opens that `table_name` (handles cached by name); the connection's `READ_CONSISTENCY_INTERVAL` (30s, `app/lancedb/database.py`) bounds how soon a promote or an in-place re-extraction is seen, no restart needed. Zero or several current rows raise `NoCurrentCodesTableError`, checked once at startup by `LanceDB.open()`. `libelle` (dropped upstream) is gone from every read path, and the FTS columns now match ingestion's index exactly (`number`/`description`/`lexical_terms`/`expansion_terms`). `manual_rev` on results and the `get_by_number(number, manual_rev)` historical lookup were deferred — see Features.

- [x] 🔴 `codes` LanceDB table covers only manual section B — *added 8/29, done 9/30, from billing_codes retrieval/prompt optimization*
  - The live `codes` table at `DB_PATH` is 362 rows, every one of them under the "B — Consultation, examen et visite" header path — confirmed by direct query against the real table. No procedure/surgery/other-section codes exist at all: `01320`/`01322`/`01325`/`01327` (Réparation de plaies), which `tests/fixtures/eval_billing_codes.jsonl`'s `URG-2026-04512` entry expects, are entirely absent from the table.
  - This is a hard recall ceiling for any encounter involving a procedure — no amount of retrieval/prompt tuning on this backend's side can surface a code that was never ingested. This is `ramq-ingestion`'s scope (see CLAUDE.md's "RAMQ data is a generated, external artifact"), not something to fix here — needs that repo to ingest the remaining sections of the Manuel des médecins omnipraticiens.
  - Fixed upstream: `codes_2026-06-05` holds 4,070 codes across sections B–V (checked 9/30 against the real table). Retrieval breadth tuning for an 11× larger table is a separate Features item.

- [x] 🟡 Code-family disambiguating axes are free text, not typed columns — *added 8/29, done 9/30, from billing_codes retrieval/prompt optimization*
  - `app/ramq_codes/family.py`'s `CodeFamilySelector` parses panel size (`<500`/`500 patients ou plus`), vulnerability, registration, and age-threshold facts out of each candidate's `description`/`when_to_use` French prose via regex, because the `codes` table doesn't carry them as structured fields. This works (pinned against real corpus text in `tests/test_ramq_codes_family.py`, including the "inscrite ou non inscrite" and duplicate-header-path pitfalls it had to be hardened against), but it's inherently fragile: a rewording in a future manual revision silently breaks the match, and every code sharing a taxonomy `header_path` for an unrelated reason (e.g. distinct consultation complexity tiers, not axis variants) has to be handled defensively rather than by simple grouping.
  - If `ramq-ingestion` emitted these axes as typed columns on the `codes` row (e.g. `min_panel_size`/`max_panel_size`, `requires_vulnerable`, `requires_registered`, `min_age`/`max_age`) instead of leaving them embedded only in prose, family disambiguation could become a LanceDB `WHERE` pre-filter — no regex to maintain on this side, and no risk of silent drift when the source manual's wording changes. Not blocking (the text-parsing approach works today), but worth raising with that repo.
  - Fixed 9/30: ramq-ingestion now emits `min_age`/`max_age`/`min_panel_size`/`max_panel_size`/`requires_registered`/`requires_vulnerable` (inclusive, null = no restriction). `family.py` and its regexes are deleted; `EligibilityFilterFactory` (`app/ramq_codes/eligibility.py`) + `CodeEligibilityWhereBuilder` (`app/lancedb/eligibility.py`) prefilter every `hybrid_search` with a null-safe `WHERE`, and `UnresolvedAxisDetector` only flags an unknown axis when a surviving candidate is actually bounded on it (previously every unknown axis was always flagged). Patient age is floored, not rounded, to match the whole-year bounds — the prompt used to print 79.6 as "80 ans".

- [x] 🟡 NAM matching scans the whole roster instead of an indexed lookup — *added 8/24, from billing-workflow code review, obsolete 8/31*
  - `PatientSuggestionService._match` (`app/patients/suggestion.py`) calls `list_for_physician` and filters for a NAM match in Python, on every `/extract` call. `PatientRepository` has no `find_by_ramq(physician_id, nam)`. Fine at demo scale; a physician with hundreds of roster patients pays for the full roster transfer/deserialization just to find at most one match, on a rate-limited hot path.
  - Obsolete: `PatientSuggestionService` was deleted by the global-patient-identity refactor (332385f/f2f7cde). The physician now picks the patient before `/extract`, which looks it up by id (`PatientRepository.get`), and the global NAM search (`PatientRepository.search`) is a SQL query, not a Python scan.

- [x] 🟡 No server-side check that returned billing codes are from the candidate set — *added 8/19, from codebase audit, note added 8/24, done 8/29*
  - `ramq_codes/task.py`'s `parse()` only validates JSON shape, never cross-checks returned `number`s against the candidates built in `build_prompt`. The "only choose from candidates" constraint lives in the prompt only. Mandatory physician review is the only backstop today — no defense in depth.
  - Note: `POST /claims` (`app/claims/service.py`) *does* validate its `selected_codes` against the referenced extraction's own stored candidates (422 on an unknown code) — but that's checking the physician's selection against what the model already returned, not checking what the model returned against what it was offered. This item is still open.
  - Fixed: `ExtractionTask.build_prompt` now returns a `PreparedPrompt` (`app/tasks/base.py`) carrying the offered `candidate_numbers`, and `BillingCodesTask.parse` (`app/ramq_codes/task.py`) drops any returned code not in that set, appending a note — same "drop and flag, don't fabricate" handling as the existing malformed-shape case.

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

- [x] 🔴 Vector search blocks the event loop — *added 8/19, from codebase audit, done 8/25*
  - `LanceDBVectorStore` has no `aquery` override, so both retrievers' `_aretrieve` (`ramq_codes/retriever.py`, `ramq_chatbot/retriever.py`) fall back to the sync `.retrieve()` call under the hood. Every concurrent physician's request stalls the single event loop for the duration of the native call.
  - Fix: wrap the sync query in `run_in_threadpool`, or move to an async-native vector store call path.
  - Fixed by the LanceDB repository refactor (29980f2): both retrievers now go through `app/lancedb/repository.py`'s `async def hybrid_search` on a native `lancedb.AsyncConnection`/`AsyncTable` — no `LanceDBVectorStore`, no sync `.retrieve()` fallback left.

- [x] 🟢 Docker's default `json-file` log driver has no rotation — *added 8/21, moved from DEPLOY.md, done 8/24*
  - Not a concern at demo traffic/duration. Add `logging: driver: json-file, options: {max-size: 10m, max-file: "3"}` per service in `docker-compose.yml` if this runs long enough to matter.
  - Fixed: all five services in `docker-compose.yml` now set `logging: driver: json-file, options: {max-size: "10m", max-file: "3"}`.

- [x] 🟡 Add a data logger for production — *added 8/21, done 8/24*
  - Fixed: `app/logging_config.py` configures stdlib `logging` to emit one JSON line per event to stdout (same shape as `app/request_logging.py`'s existing per-request access log), wired at startup in `app/main.py`. Added `logger` calls at the silent-failure spots worth surfacing: `CodeTable.get_all` (`app/lancedb/db.py`) now warns on candidate numbers with no matching `codes` row (stale index), `AuthService.login` (`app/auth/service.py`) now logs failed/successful login attempts, and `RequestLoggingMiddleware` now logs unhandled exceptions with the same `request_id` as its access-log line before re-raising.

- [x] 🟢 DEPLOY.md and nginx's allowlist behavior disagree — *added 8/19, from codebase audit, done 8/21*
  - `DEPLOY.md:65-67` says leaving `ALLOWED_CIDRS` unset makes the demo fully public; `frontend/docker-entrypoint.sh` actually `deny all`s everything but `127.0.0.1` in that case. Fails safe, but will send an operator chasing a bogus CIDR issue.
  - Fixed: the "leave `ALLOWED_CIDRS` unset — this deploy is open to the internet" line was dropped from `DEPLOY.md` (448c448). `.env.example` now documents `ALLOWED_CIDRS` as the allowlist in front of the app; `frontend/nginx.conf` still `deny all`s everything else.

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

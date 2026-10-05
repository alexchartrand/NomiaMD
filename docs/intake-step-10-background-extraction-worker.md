# Step 10 — Background extraction worker (arq)

**Phase:** 2 · **Depends on:** 07, 09 (11's inbox already shipped, running extraction inline) · **Unblocks:** batch inbox, 05's purge job, 20's polling
**Plan section:** §4 Background extraction

## Goal
Notes are extracted as they arrive, so by end of day the physician only reviews. The request
path never waits on the LLM, except for the on-demand route.

## Tasks
- [x] `uv add arq`. New `backend/app/worker.py`:
  - `WorkerSettings` with `redis_settings` from `settings.redis_url`
  - `on_startup` enters `application_services()` (`app/bootstrap.py`), the same composition root
  - `on_shutdown` exits it
- [x] Job `extract_encounter(ctx, encounter_id)`:
  - Idempotent: skip if a run already exists for this encounter.
  - Reuses `run_billing_codes_pipeline` and `ExtractionRecorder` unchanged.
  - On failure: `record_extraction_error`, with arq retries and backoff (max 3).
- [x] `ArqExtractionQueue` implements step 07's `ExtractionQueue`. Choose it when `REDIS_URL`
  is a real Redis; otherwise keep `InlineExtractionQueue` (tests, simple dev).
- [x] Concurrency cap (`max_jobs`) sized to the LLM endpoint's throughput (from step 03).
- [x] Cron hook placeholder for later jobs (purge in 05, polling in 20).
- [x] `Makefile`: `worker` target; `dev`/`dev-fake` also start the worker (and a local Redis, or
  document the inline fallback). `docker-compose.yml`: a `worker` service using the backend
  image with `arq app.worker.WorkerSettings`, on the `internal` network.
- [x] `POST /encounters/{id}/extract` re-enqueues a failed (`échec`) encounter, or runs it inline
  when the physician is waiting.

## Done when
- Tests: the job runs the pipeline once, and running it twice gives one run; failure records
  the error and the status becomes `échec`; queue selection by config.
- `make dev-fake`: paste 3 notes and they become `prêt` without staying on the page.

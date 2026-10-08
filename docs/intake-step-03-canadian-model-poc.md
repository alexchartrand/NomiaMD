# Step 03 — Canadian/local model proof of concept and decision

**Phase:** 1 (weeks 1–4) · **Depends on:** 01, 02 · **Unblocks:** go-live with real data
**Plan section:** §3 Data residency (gating)

## Goal
Pick the hosting and the open-weight chat and embedding models that real notes will use,
backed by eval numbers rather than impressions. Write the decision down.

## Tasks
- [ ] Shortlist the hosting: OVHcloud Beauharnois (QC), AWS ca-central-1, Azure Canada Central /
  Canada East, Cohere on Canadian infrastructure. Compare data-residency guarantees, GPU
  availability and monthly cost at the expected volume.
- [ ] Shortlist the models:
  - Chat: 2–3 open-weight models with strong French and JSON-schema adherence, served by vLLM
    with structured outputs.
  - Embeddings: a multilingual model (French-strong) served by TEI or vLLM.
- [ ] Ask ramq-ingestion for a codes table and a documents table embedded with each
  embedding candidate (new `codes_<rev>` rows in `code_versions`, not promoted to
  `is_current`). Track this in ramq-ingestion's BACKLOG.md.
- [ ] Benchmark each combination with `scripts/benchmark.py` over all 58 labeled
  `consultations/` notes (`make bench ARGS="..."`). Record the Mistral baseline first and
  `promote` it. A fix validated on one transcript can regress another, so read the per-note
  comparison (`report <run> --baseline <base>`), not only the averages.
- [ ] Latency and tokens are recorded for every call (`report.md`'s cost table: p50/p95 per
  purpose and model). The inbox batch depends on them.

### Benchmark workflow

Phase 1 covers the summary and retrieval. Phase 2, selection (the `billing_codes` call over frozen
candidates), comes next.

1. **Baseline:** `run --name mistral-base`. 58 `mistral-small` summary calls, plus embeddings.
2. **Control runs:**
   - `run --name transcript-q --stages retrieval --query-source transcript`: what does the summary add over the raw note?
   - `run --name combined-q --stages retrieval --query-source summary+transcript --summaries-from mistral-base`: does adding the note's own query help?
3. **Retrieval tuning:** `sweep --summaries-from mistral-base --similarity-top-k 20,30,40 --fused-top-k 40,60 [--rrf-k 30,60]`. It makes no chat call, and the embeddings are cached after the first combination.
4. **Candidate summary model:**
   - `LLM_PROVIDER=openai_compatible LLM_ENDPOINT=... run --name <model>-sum --summary-model <model>`, then `report <model>-sum --baseline mistral-base`.
   - Watch the summary's failed count: `ExtractionOutputError` is a parse or schema failure, and its raw output is stored.
5. **Candidate embedding model:** `EMBEDDING_PROVIDER=openai_compatible EMBEDDING_MODEL=... run --name <emb>-ret --stages retrieval --summaries-from mistral-base --codes-table codes_<rev>`, on a table re-embedded by ramq-ingestion.
- [ ] Fill in the `decision-llm-hosting.docx` working document (OneDrive, not in the repo): hosting options and prices,
  model candidates, the eval table, the cost estimate, and the final decision.

## Done when
- `decision-llm-hosting.docx` (OneDrive) has a filled-in decision section and an eval table: baseline vs each candidate, ≥2 cases.
- The chosen endpoint works with `LLM_PROVIDER=openai_compatible` and `EMBEDDING_PROVIDER=openai_compatible`.
- Updated `project_llm_model_selection` memory/notes.

## Risks
- Smaller open models may follow the strict JSON schema less reliably. Check the
  `finish_reason` and parse-failure rate, not only code accuracy.
- A GPU running around the clock costs money even when idle. Consider scale-to-zero
  against the latency budget of the batch inbox.

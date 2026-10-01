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
- [ ] Run `scripts/eval_extraction.py --retrieval-only`, then the full eval, on **at least 2
  `consultations/` cases** for each combination. Record the Mistral baseline first. A fix
  validated on one transcript can regress another.
- [ ] Measure latency per extraction (summary + billing_codes), since the inbox batch depends on it.
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

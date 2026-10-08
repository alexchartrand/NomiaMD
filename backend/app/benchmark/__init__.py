"""Benchmarks the extraction pipeline stage by stage over the labeled `consultations/` notes:
each stage's output per note (summary, retrieval, the model's selected codes) is stored under
`backend/benchmarks/`, with every chat/embedding call's tokens and latency, so a stage can
be tuned or a model swapped and compared note by note against a baseline. CLI:
scripts/benchmark.py. Never imported by the app itself."""

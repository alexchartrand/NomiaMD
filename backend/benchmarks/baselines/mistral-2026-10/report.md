# Benchmark run `mistral-base`

|  |  |
|---|---|
| stages | summary, retrieval |
| query source | summary |
| summaries from | (this run) |
| chat provider / summary model | mistral / mistral-small-latest |
| embeddings | mistral / mistral-embed |
| codes table | codes_2026-09-17 (manual 2026-09-17) |
| retrieval | similarity_top_k=20, fused_top_k=40, rrf_k=60 |
| notes | 58 |
| git | 10e56d4fab |
| fixture | tests/fixtures/eval_billing_codes.jsonl (5dbc9ecdcf) |
| updated | 2026-10-08T14:20:11+00:00 |

## Retrieval

Share of expected codes found among the candidates (R@k: within the top k). *family*: only a sibling variant was offered; *inelig.*: the billing context filters the code out (label/context/data issue, not retrieval); *no row*: not in the codes table.

| group | notes | codes | R@5 | R@10 | R@20 | R@40 | recall | MRR | family | inelig. | no row | missed | cands | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all** | 58 | 75 | 41% | 48% | 59% | 65% | 65% | 0.25 | 5 | 9 | 0 | 12 | 32 | 0 |
| difficulty: easy | 10 | 10 | 50% | 60% | 70% | 80% | 80% | 0.35 | 0 | 1 | 0 | 1 | 24 | 0 |
| difficulty: hard | 8 | 16 | 25% | 31% | 38% | 56% | 56% | 0.14 | 1 | 4 | 0 | 2 | 36 | 0 |
| difficulty: medium | 12 | 22 | 55% | 55% | 68% | 68% | 68% | 0.29 | 3 | 1 | 0 | 3 | 33 | 0 |
| difficulty: negative | 3 | 0 | 0% | 0% | 0% | 0% | 0% | 0.00 | 0 | 0 | 0 | 0 | 26 | 0 |
| difficulty: original | 25 | 27 | 37% | 48% | 59% | 63% | 63% | 0.23 | 1 | 3 | 0 | 6 | 34 | 0 |
| labels: draft-unverified | 41 | 54 | 50% | 59% | 70% | 78% | 78% | 0.31 | 2 | 4 | 0 | 6 | 30 | 0 |
| labels: reviewed | 14 | 17 | 18% | 18% | 24% | 29% | 29% | 0.08 | 2 | 4 | 0 | 6 | 35 | 0 |
| labels: to_review | 3 | 4 | 25% | 25% | 50% | 50% | 50% | 0.10 | 1 | 1 | 0 | 0 | 39 | 0 |

## Summary

58 notes, 0 failed

| check | passed | rate |
|---|---|---|
| date | 58/58 | 100% |
| time_start | 57/58 | 98% |

| stat (mean per note) | value |
|---|---|
| add_ons | 0.40 |
| duration_stated | 0.07 |
| pregnancy | 0.05 |
| procedures | 0.97 |
| referral | 0.19 |
| systems | 2.91 |
| uncertain_items | 1.88 |

## Cost and latency

| stage | kind | purpose | model | cached | calls | input tok | output tok | mean in / out | latency ms p50 / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| retrieval | embedding | billing_codes.retrieval | mistral-embed |  | 58 | 37,416 | 0 | 645 / 0 | 932 / 2,033 / 2,227 |
| summary | chat | consultation_summary | mistral-small-latest |  | 58 | 112,232 | 37,016 | 1,935 / 638 | 3,865 / 5,504 / 6,966 |

| stage | wall ms per note p50 / p95 / max |
|---|---|
| summary | 3,865 / 5,504 / 6,966 |
| retrieval | 960 / 2,060 / 2,263 |

## Per note

| note | difficulty | labels | expected codes | cands | error |
|---|---|---|---|---|---|
| URG-2026-04471 | original | to_review | 15058 ineligible | 40 |  |
| URG-2026-04512 | original | draft-unverified | 01323 not_retrieved, 15052 ineligible | 40 |  |
| URG-2026-04538 | original | reviewed | 15058 ineligible | 40 |  |
| CLI-2026-01187 | original | draft-unverified | 15823 #1 | 20 |  |
| CLI-2026-01203 | original | reviewed | 15803 not_retrieved | 40 |  |
| CLI-2026-01220 | original | draft-unverified | 15801 #2 | 20 |  |
| CLI-2026-01221 | original | draft-unverified | 15803 #1 | 20 |  |
| GMF-2026-00301 | original | draft-unverified | 15805 #4 | 20 |  |
| GMF-2026-00302 | original | to_review | 15144 #15, 15811 #3 | 40 |  |
| GMF-2026-00303 | original | draft-unverified | 15813 #6 | 32 |  |
| CLI-2026-01222 | original | reviewed | 15767 not_retrieved | 39 |  |
| CLI-2026-01223 | original | reviewed | 15765 #28 | 40 |  |
| CLI-2026-01224 | original | reviewed | 15803 #5 | 20 |  |
| CLI-2026-01225 | original | reviewed | 08777 not_retrieved | 40 |  |
| CLI-2026-01226 | original | reviewed | 15765 not_retrieved | 40 |  |
| GMF-2026-00304 | original | draft-unverified | 15790 not_retrieved | 20 |  |
| CLI-2026-01227 | original | to_review | 08857 family_only | 36 |  |
| CLI-2026-01228 | original | draft-unverified | 15803 #17 | 37 |  |
| GMF-2026-00305 | original | draft-unverified | 15783 #4 | 39 |  |
| GMF-2026-00306 | original | draft-unverified | 15839 #2 | 40 |  |
| CLI-2026-01229 | original | draft-unverified | 15803 #9 | 40 |  |
| GMF-2026-00307 | original | draft-unverified | 15188 #1, 15823 #6 | 40 |  |
| CLI-2026-01230 | original | reviewed | (negative) | 35 |  |
| TEL-2026-00090 | original | reviewed | 15765 #2 | 36 |  |
| CLI-2026-01231 | original | draft-unverified | 15823 #16 | 39 |  |
| GMF-2026-00410 | easy | draft-unverified | 15804 #1 | 20 |  |
| GMF-2026-00311 | easy | draft-unverified | 15823 #4 | 20 |  |
| CLI-2026-01240 | easy | draft-unverified | 15765 #12 | 39 |  |
| CLI-2026-01241 | easy | draft-unverified | 15837 #1 | 20 |  |
| GMF-2026-00411 | easy | draft-unverified | 15802 #23 | 40 |  |
| CHSLD-2026-00051 | easy | draft-unverified | 15616 #7 | 20 |  |
| HOP-2026-00731 | easy | reviewed | 15639 not_retrieved | 20 |  |
| URG-2026-04620 | easy | draft-unverified | 15052 ineligible | 20 |  |
| DOM-2026-00021 | easy | draft-unverified | 15783 #2 | 20 |  |
| CLSC-2026-00133 | easy | draft-unverified | 15812 #2 | 20 |  |
| GMF-2026-00412 | medium | draft-unverified | 00341 #5, 15804 #2 | 39 |  |
| CLI-2026-01242 | medium | draft-unverified | 01323 #4, 15765 not_retrieved | 30 |  |
| GMF-2026-00312 | medium | draft-unverified | 15785 #1, 15786 #3 | 31 |  |
| GMF-2026-00413 | medium | draft-unverified | 00431 not_retrieved, 15804 #12 | 29 |  |
| CLI-2026-01243 | medium | draft-unverified | 01005 #3, 15765 #11 | 33 |  |
| CHSLD-2026-00052 | medium | draft-unverified | 15615 #1, 15618 #2 | 20 |  |
| CHSLD-2026-00053 | medium | draft-unverified | 15617 family_only, 15624 family_only | 40 |  |
| HOP-2026-00732 | medium | reviewed | 15638 not_retrieved | 40 |  |
| HOP-2026-00733 | medium | reviewed | 15158 #17, 15639 family_only | 38 |  |
| URG-2026-04621 | medium | draft-unverified | 01323 #4, 15059 ineligible | 34 |  |
| DOM-2026-00022 | medium | draft-unverified | 00344 #1, 15781 #3 | 38 |  |
| GMF-2026-00414 | medium | draft-unverified | 08848 #2 | 20 |  |
| GMF-2026-00313 | hard | draft-unverified | 15803 not_retrieved | 40 |  |
| CLI-2026-01244 | hard | draft-unverified | 00215 not_retrieved, 01166 #22, 15803 #31 | 40 |  |
| URG-2026-04622 | hard | reviewed | 15054 ineligible, 15060 ineligible, 15637 ineligible | 40 |  |
| CHSLD-2026-00054 | hard | draft-unverified | 00014 #5, 15265 #10, 15622 #29 | 40 |  |
| GMF-2026-00314 | hard | draft-unverified | 15188 #1, 15821 #16 | 40 |  |
| CLI-2026-01245 | hard | draft-unverified | 00205 #3 | 31 |  |
| HOP-2026-00734 | hard | reviewed | 15641 #2, 15643 family_only | 20 |  |
| URG-2026-04623 | hard | draft-unverified | 15064 ineligible | 40 |  |
| CLI-2026-01246 | negative | draft-unverified | (negative) | 37 |  |
| GMF-2026-00415 | negative | draft-unverified | (negative) | 20 |  |
| GMF-2026-00315 | negative | draft-unverified | (negative) | 20 |  |


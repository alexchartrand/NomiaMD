# Benchmark run `mistral-2026-10-v2`

|  |  |
|---|---|
| stages | summary, retrieval |
| query source | summary |
| summaries from | (this run) |
| chat provider / summary model | mistral / mistral-small-latest |
| embeddings | mistral / mistral-embed |
| codes table | codes_2026-09-17 (manual 2026-09-17) |
| retrieval | similarity_top_k=20, fused_top_k=40, rrf_k=60, max_family_size=6, kept_sources=visit |
| notes | 58 |
| git | 228db050b4 |
| fixture | tests/fixtures/eval_billing_codes.jsonl (5dbc9ecdcf) |
| updated | 2026-10-08T15:44:31+00:00 |

## Retrieval

Share of expected codes found among the candidates (R@k: within the top k). *family*: only a sibling variant was offered; *inelig.*: the billing context filters the code out (label/context/data issue, not retrieval); *no row*: not in the codes table.

| group | notes | codes | R@5 | R@10 | R@20 | R@40 | recall | MRR | family | inelig. | no row | missed | cands | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all** | 58 | 75 | 44% | 59% | 73% | 83% | 88% | 0.29 | 0 | 9 | 0 | 0 | 56 | 0 |
| difficulty: easy | 10 | 10 | 70% | 80% | 90% | 90% | 90% | 0.51 | 0 | 1 | 0 | 0 | 45 | 0 |
| difficulty: hard | 8 | 16 | 19% | 38% | 50% | 62% | 75% | 0.13 | 0 | 4 | 0 | 0 | 60 | 0 |
| difficulty: medium | 12 | 22 | 36% | 55% | 77% | 95% | 95% | 0.20 | 0 | 1 | 0 | 0 | 62 | 0 |
| difficulty: negative | 3 | 0 | 0% | 0% | 0% | 0% | 0% | 0.00 | 0 | 0 | 0 | 0 | 43 | 0 |
| difficulty: original | 25 | 27 | 56% | 67% | 78% | 81% | 89% | 0.37 | 0 | 3 | 0 | 0 | 59 | 0 |
| labels: draft-unverified | 41 | 54 | 50% | 69% | 83% | 89% | 93% | 0.35 | 0 | 4 | 0 | 0 | 54 | 0 |
| labels: reviewed | 14 | 17 | 29% | 35% | 47% | 71% | 76% | 0.14 | 0 | 4 | 0 | 0 | 63 | 0 |
| labels: to_review | 3 | 4 | 25% | 25% | 50% | 50% | 75% | 0.07 | 0 | 1 | 0 | 0 | 61 | 0 |

## Summary

58 notes, 0 failed

| check | passed | rate |
|---|---|---|
| date | 58/58 | 100% |
| time_start | 57/58 | 98% |

| stat (mean per note) | value |
|---|---|
| add_ons | 0.38 |
| duration_stated | 0.07 |
| pregnancy | 0.05 |
| procedures | 0.76 |
| referral | 0.21 |
| systems | 2.81 |
| uncertain_items | 1.95 |

## Cost and latency

| stage | kind | purpose | model | cached | calls | input tok | output tok | mean in / out | latency ms p50 / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| retrieval | embedding | billing_codes.retrieval | mistral-embed |  | 52 | 36,219 | 0 | 697 / 0 | 375 / 795 / 1,164 |
| retrieval | embedding | billing_codes.retrieval | mistral-embed | yes | 6 | 3,460 | 0 | 577 / 0 | 0 / 1 / 1 |
| summary | chat | consultation_summary | mistral-small-latest |  | 58 | 119,250 | 36,672 | 2,056 / 632 | 3,799 / 5,605 / 5,881 |

| stage | wall ms per note p50 / p95 / max |
|---|---|
| summary | 3,800 / 5,606 / 5,881 |
| retrieval | 402 / 841 / 1,239 |

## Compared with `mistral-base`

regressed: 12, mixed: 6, improved: 26, unchanged: 14

| verdict | note | difficulty | changed codes | candidates |
|---|---|---|---|---|
| regressed | GMF-2026-00312 | medium | 15785: #1 → #7; 15786: #3 → #23 | 31 → 48 |
| regressed | CHSLD-2026-00052 | medium | 15615: #1 → #8; 15618: #2 → #6 | 20 → 50 |
| regressed | DOM-2026-00022 | medium | 15781: #3 → #11 | 38 → 62 |
| regressed | CLSC-2026-00133 | easy | 15812: #2 → #8 | 20 → 40 |
| regressed | GMF-2026-00302 | original | 15144: #15 → #18; 15811: #3 → #5 | 40 → 57 |
| regressed | GMF-2026-00306 | original | 15839: #2 → #7 | 40 → 60 |
| regressed | CLI-2026-01243 | medium | 01005: #3 → #5; 15765: #11 → #13 | 33 → 84 |
| regressed | DOM-2026-00021 | easy | 15783: #2 → #5 | 20 → 37 |
| regressed | CLI-2026-01245 | hard | 00205: #3 → #5 | 31 → 51 |
| regressed | GMF-2026-00412 | medium | 15804: #2 → #4 | 39 → 58 |
| regressed | GMF-2026-00303 | original | 15813: #6 → #7 | 32 → 53 |
| regressed | GMF-2026-00414 | medium | 08848: #2 → #3 | 20 → 58 |
| mixed | GMF-2026-00413 | medium | 00431: not_retrieved → #9; 15804: #12 → #17 | 29 → 66 |
| mixed | CLI-2026-01244 | hard | 00215: not_retrieved → #45; 01166: #22 → #44; 15803: #31 → #16 | 40 → 70 |
| mixed | CLI-2026-01242 | medium | 01323: #4 → #5; 15765: not_retrieved → #19 | 30 → 67 |
| mixed | HOP-2026-00734 | hard | 15641: #2 → #7; 15643: family_only → #32 | 20 → 40 |
| mixed | GMF-2026-00314 | hard | 15188: #1 → #8; 15821: #16 → #1 | 40 → 56 |
| mixed | GMF-2026-00307 | original | 15188: #1 → #2; 15823: #6 → #1 | 40 → 64 |
| improved | CLI-2026-01222 | original | 15767: not_retrieved → #2 | 39 → 61 |
| improved | GMF-2026-00304 | original | 15790: not_retrieved → #3 | 20 → 62 |
| improved | URG-2026-04512 | original | 01323: not_retrieved → #13 | 40 → 74 |
| improved | HOP-2026-00731 | easy | 15639: not_retrieved → #15 | 20 → 46 |
| improved | CLI-2026-01225 | original | 08777: not_retrieved → #20 | 40 → 66 |
| improved | GMF-2026-00313 | hard | 15803: not_retrieved → #22 | 40 → 50 |
| improved | CLI-2026-01203 | original | 15803: not_retrieved → #32 | 40 → 80 |
| improved | HOP-2026-00732 | medium | 15638: not_retrieved → #37 | 40 → 73 |
| improved | CLI-2026-01226 | original | 15765: not_retrieved → #62 | 40 → 72 |
| improved | CHSLD-2026-00053 | medium | 15617: family_only → #27; 15624: family_only → #20 | 40 → 63 |
| improved | HOP-2026-00733 | medium | 15158: #17 → #5; 15639: family_only → #27 | 38 → 58 |
| improved | CLI-2026-01227 | original | 08857: family_only → #57 | 36 → 66 |
| improved | CLI-2026-01223 | original | 15765: #28 → #5 | 40 → 59 |
| improved | CHSLD-2026-00054 | hard | 00014: #5 → #4; 15265: #10 → #9; 15622: #29 → #11 | 40 → 60 |
| improved | GMF-2026-00411 | easy | 15802: #23 → #3 | 40 → 34 |
| improved | CLI-2026-01228 | original | 15803: #17 → #1 | 37 → 42 |
| improved | CLI-2026-01231 | original | 15823: #16 → #1 | 39 → 41 |
| improved | CLI-2026-01240 | easy | 15765: #12 → #3 | 39 → 81 |
| improved | CHSLD-2026-00051 | easy | 15616: #7 → #1 | 20 → 38 |
| improved | CLI-2026-01224 | original | 15803: #5 → #2 | 20 → 54 |
| improved | GMF-2026-00311 | easy | 15823: #4 → #1 | 20 → 38 |
| improved | URG-2026-04621 | medium | 01323: #4 → #1 | 34 → 62 |
| improved | CLI-2026-01229 | original | 15803: #9 → #7 | 40 → 48 |
| improved | CLI-2026-01220 | original | 15801: #2 → #1 | 20 → 48 |
| improved | GMF-2026-00301 | original | 15805: #4 → #3 | 20 → 40 |
| improved | GMF-2026-00305 | original | 15783: #4 → #3 | 39 → 56 |

## Per note

| note | difficulty | labels | expected codes | cands | error |
|---|---|---|---|---|---|
| URG-2026-04471 | original | to_review | 15058 ineligible | 61 |  |
| URG-2026-04512 | original | draft-unverified | 01323 #13, 15052 ineligible | 74 |  |
| URG-2026-04538 | original | reviewed | 15058 ineligible | 86 |  |
| CLI-2026-01187 | original | draft-unverified | 15823 #1 | 61 |  |
| CLI-2026-01203 | original | reviewed | 15803 #32 | 80 |  |
| CLI-2026-01220 | original | draft-unverified | 15801 #1 | 48 |  |
| CLI-2026-01221 | original | draft-unverified | 15803 #1 | 43 |  |
| GMF-2026-00301 | original | draft-unverified | 15805 #3 | 40 |  |
| GMF-2026-00302 | original | to_review | 15144 #18, 15811 #5 | 57 |  |
| GMF-2026-00303 | original | draft-unverified | 15813 #7 | 53 |  |
| CLI-2026-01222 | original | reviewed | 15767 #2 | 61 |  |
| CLI-2026-01223 | original | reviewed | 15765 #5 | 59 |  |
| CLI-2026-01224 | original | reviewed | 15803 #2 | 54 |  |
| CLI-2026-01225 | original | reviewed | 08777 #20 | 66 |  |
| CLI-2026-01226 | original | reviewed | 15765 #62 | 72 |  |
| GMF-2026-00304 | original | draft-unverified | 15790 #3 | 62 |  |
| CLI-2026-01227 | original | to_review | 08857 #57 | 66 |  |
| CLI-2026-01228 | original | draft-unverified | 15803 #1 | 42 |  |
| GMF-2026-00305 | original | draft-unverified | 15783 #3 | 56 |  |
| GMF-2026-00306 | original | draft-unverified | 15839 #7 | 60 |  |
| CLI-2026-01229 | original | draft-unverified | 15803 #7 | 48 |  |
| GMF-2026-00307 | original | draft-unverified | 15188 #2, 15823 #1 | 64 |  |
| CLI-2026-01230 | original | reviewed | (negative) | 56 |  |
| TEL-2026-00090 | original | reviewed | 15765 #2 | 56 |  |
| CLI-2026-01231 | original | draft-unverified | 15823 #1 | 41 |  |
| GMF-2026-00410 | easy | draft-unverified | 15804 #1 | 29 |  |
| GMF-2026-00311 | easy | draft-unverified | 15823 #1 | 38 |  |
| CLI-2026-01240 | easy | draft-unverified | 15765 #3 | 81 |  |
| CLI-2026-01241 | easy | draft-unverified | 15837 #1 | 45 |  |
| GMF-2026-00411 | easy | draft-unverified | 15802 #3 | 34 |  |
| CHSLD-2026-00051 | easy | draft-unverified | 15616 #1 | 38 |  |
| HOP-2026-00731 | easy | reviewed | 15639 #15 | 46 |  |
| URG-2026-04620 | easy | draft-unverified | 15052 ineligible | 58 |  |
| DOM-2026-00021 | easy | draft-unverified | 15783 #5 | 37 |  |
| CLSC-2026-00133 | easy | draft-unverified | 15812 #8 | 40 |  |
| GMF-2026-00412 | medium | draft-unverified | 00341 #5, 15804 #4 | 58 |  |
| CLI-2026-01242 | medium | draft-unverified | 01323 #5, 15765 #19 | 67 |  |
| GMF-2026-00312 | medium | draft-unverified | 15785 #7, 15786 #23 | 48 |  |
| GMF-2026-00413 | medium | draft-unverified | 00431 #9, 15804 #17 | 66 |  |
| CLI-2026-01243 | medium | draft-unverified | 01005 #5, 15765 #13 | 84 |  |
| CHSLD-2026-00052 | medium | draft-unverified | 15615 #8, 15618 #6 | 50 |  |
| CHSLD-2026-00053 | medium | draft-unverified | 15617 #27, 15624 #20 | 63 |  |
| HOP-2026-00732 | medium | reviewed | 15638 #37 | 73 |  |
| HOP-2026-00733 | medium | reviewed | 15158 #5, 15639 #27 | 58 |  |
| URG-2026-04621 | medium | draft-unverified | 01323 #1, 15059 ineligible | 62 |  |
| DOM-2026-00022 | medium | draft-unverified | 00344 #1, 15781 #11 | 62 |  |
| GMF-2026-00414 | medium | draft-unverified | 08848 #3 | 58 |  |
| GMF-2026-00313 | hard | draft-unverified | 15803 #22 | 50 |  |
| CLI-2026-01244 | hard | draft-unverified | 00215 #45, 01166 #44, 15803 #16 | 70 |  |
| URG-2026-04622 | hard | reviewed | 15054 ineligible, 15060 ineligible, 15637 ineligible | 76 |  |
| CHSLD-2026-00054 | hard | draft-unverified | 00014 #4, 15265 #9, 15622 #11 | 60 |  |
| GMF-2026-00314 | hard | draft-unverified | 15188 #8, 15821 #1 | 56 |  |
| CLI-2026-01245 | hard | draft-unverified | 00205 #5 | 51 |  |
| HOP-2026-00734 | hard | reviewed | 15641 #7, 15643 #32 | 40 |  |
| URG-2026-04623 | hard | draft-unverified | 15064 ineligible | 74 |  |
| CLI-2026-01246 | negative | draft-unverified | (negative) | 51 |  |
| GMF-2026-00415 | negative | draft-unverified | (negative) | 42 |  |
| GMF-2026-00315 | negative | draft-unverified | (negative) | 35 |  |


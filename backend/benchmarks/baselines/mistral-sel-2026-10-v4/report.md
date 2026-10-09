# Benchmark run `current-table-sel`

|  |  |
|---|---|
| stages | retrieval, selection |
| query source | summary |
| summaries from | mistral-2026-10-v2 |
| candidates from | (this run) |
| chat provider / summary model | mistral / – |
| selection model | mistral-medium-latest |
| embeddings | mistral / mistral-embed |
| codes table | codes_2026-09-17 (manual 2026-09-17) |
| retrieval | similarity_top_k=20, fused_top_k=40, rrf_k=60, max_family_size=6, kept_sources=visit |
| notes | 58 |
| git | d208d7ef4e (dirty) |
| fixture | tests/fixtures/eval_billing_codes.jsonl (5dbc9ecdcf) |
| updated | 2026-10-09T17:43:28+00:00 |

## Retrieval

Share of expected codes found among the candidates (R@k: within the top k). *family*: only a sibling variant was offered; *inelig.*: the billing context filters the code out (label/context/data issue, not retrieval); *no row*: not in the codes table.

| group | notes | codes | R@5 | R@10 | R@20 | R@40 | recall | MRR | family | inelig. | no row | missed | cands | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all** | 58 | 75 | 43% | 57% | 67% | 81% | 88% | 0.32 | 0 | 0 | 0 | 9 | 60 | 0 |
| difficulty: easy | 10 | 10 | 80% | 80% | 80% | 90% | 100% | 0.57 | 0 | 0 | 0 | 0 | 48 | 0 |
| difficulty: hard | 8 | 16 | 19% | 38% | 50% | 75% | 81% | 0.19 | 0 | 0 | 0 | 3 | 62 | 0 |
| difficulty: medium | 12 | 22 | 32% | 50% | 68% | 86% | 91% | 0.25 | 0 | 0 | 0 | 2 | 66 | 0 |
| difficulty: negative | 3 | 0 | 0% | 0% | 0% | 0% | 0% | 0.00 | 0 | 0 | 0 | 0 | 50 | 0 |
| difficulty: original | 25 | 27 | 52% | 67% | 70% | 78% | 85% | 0.36 | 0 | 0 | 0 | 4 | 63 | 0 |
| labels: draft-unverified | 41 | 54 | 54% | 69% | 80% | 89% | 94% | 0.40 | 0 | 0 | 0 | 3 | 57 | 0 |
| labels: reviewed | 14 | 17 | 12% | 29% | 29% | 65% | 71% | 0.12 | 0 | 0 | 0 | 5 | 68 | 0 |
| labels: to_review | 3 | 4 | 25% | 25% | 50% | 50% | 75% | 0.08 | 0 | 0 | 0 | 1 | 68 | 0 |

## Selection

Precision, recall, F1 and exact notes are on the codes the model is sure of (*retained*: what the review ticks), over the notes with expected codes (micro: over code positions). *overall recall*: expected codes found retained or among the other possible codes. *left out*: offered, in neither tier — a selection miss; *not offered*: a retrieval miss; *wrong variant*: a wrong retained code from an expected code's family; *clean negatives*: nothing returned in either tier.

| group | notes | codes | retained | precision | recall | F1 | exact notes | overall recall | possible/note | left out | not offered | wrong variant | clean negatives | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all** | 58 | 75 | 71 | 65% | 61% | 63% | 56% | 79% | 2.7 | 7 | 9 | 4 | 4/4 | 0 |
| difficulty: easy | 10 | 10 | 8 | 100% | 80% | 89% | 80% | 100% | 2.9 | 0 | 0 | 0 | – | 0 |
| difficulty: hard | 8 | 16 | 16 | 56% | 56% | 56% | 38% | 69% | 3.4 | 2 | 3 | 2 | – | 0 |
| difficulty: medium | 12 | 22 | 20 | 65% | 59% | 62% | 50% | 77% | 3.2 | 3 | 2 | 2 | – | 0 |
| difficulty: negative | 3 | 0 | 0 | 0% | 0% | 0% | 0% | 0% | 0.0 | 0 | 0 | 0 | 3/3 | 0 |
| difficulty: original | 25 | 27 | 27 | 59% | 59% | 59% | 54% | 78% | 2.6 | 2 | 4 | 0 | 1/1 | 0 |
| labels: draft-unverified | 41 | 54 | 53 | 75% | 74% | 75% | 71% | 85% | 2.6 | 5 | 3 | 2 | 3/3 | 0 |
| labels: reviewed | 14 | 17 | 14 | 36% | 29% | 32% | 23% | 65% | 2.9 | 1 | 5 | 2 | 1/1 | 0 |
| labels: to_review | 3 | 4 | 4 | 25% | 25% | 25% | 0% | 50% | 3.3 | 1 | 1 | 0 | – | 0 |

Macro precision 63%, macro recall 63%; 1.2 retained and 2.7 possible codes per note; 10% of returned codes ask for a confirmation.

Invented codes (returned but never offered, dropped): 0 (0% of the raw codes), in 0 note(s); malformed entries: 0.

| tier | confidence | returned | correct | precision |
|---|---|---|---|---|
| retained | high | 71 | 46 | 65% |
| retained | medium | 0 | 0 | – |
| retained | low | 0 | 0 | – |
| possible | high | 2 | 0 | 0% |
| possible | medium | 100 | 10 | 10% |
| possible | low | 57 | 3 | 5% |

## Cost and latency

| stage | kind | purpose | model | cached | calls | input tok | output tok | mean in / out | latency ms p50 / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| retrieval | embedding | billing_codes.retrieval | mistral-embed | yes | 58 | 39,679 | 0 | 684 / 0 | 1 / 2 / 2 |
| selection | chat | billing_codes | mistral-medium-latest |  | 58 | 682,156 | 56,695 | 11,761 / 978 | 7,237 / 11,680 / 12,755 |

| stage | wall ms per note p50 / p95 / max |
|---|---|
| retrieval | 46 / 245 / 283 |
| selection | 7,242 / 11,686 / 12,777 |

## Per note

| note | difficulty | labels | expected codes | cands | error |
|---|---|---|---|---|---|
| URG-2026-04471 | original | to_review | 15058 not_retrieved | 72 |  |
| URG-2026-04512 | original | draft-unverified | 01323 not_retrieved (best: overview #12), 15052 not_retrieved | 72 |  |
| URG-2026-04538 | original | reviewed | 15058 not_retrieved | 89 |  |
| CLI-2026-01187 | original | draft-unverified | 15823 #2 | 59 |  |
| CLI-2026-01203 | original | reviewed | 15803 #30 | 89 |  |
| CLI-2026-01220 | original | draft-unverified | 15801 #1 | 54 |  |
| CLI-2026-01221 | original | draft-unverified | 15803 #1 | 39 |  |
| GMF-2026-00301 | original | draft-unverified | 15805 #3 | 36 |  |
| GMF-2026-00302 | original | to_review | 15144 #12, 15811 #5 | 58 |  |
| GMF-2026-00303 | original | draft-unverified | 15813 #7 | 57 |  |
| CLI-2026-01222 | original | reviewed | 15767 #6 | 73 |  |
| CLI-2026-01223 | original | reviewed | 15765 #6 | 67 |  |
| CLI-2026-01224 | original | reviewed | 15803 #1 | 63 |  |
| CLI-2026-01225 | original | reviewed | 08777 #26 | 69 |  |
| CLI-2026-01226 | original | reviewed | 15765 #66 | 80 |  |
| GMF-2026-00304 | original | draft-unverified | 15790 #2 | 64 |  |
| CLI-2026-01227 | original | to_review | 08857 #58 | 74 |  |
| CLI-2026-01228 | original | draft-unverified | 15803 #1 | 52 |  |
| GMF-2026-00305 | original | draft-unverified | 15783 #3 | 59 |  |
| GMF-2026-00306 | original | draft-unverified | 15839 #4 | 59 |  |
| CLI-2026-01229 | original | draft-unverified | 15803 #6 | 54 |  |
| GMF-2026-00307 | original | draft-unverified | 15188 #2, 15823 #1 | 67 |  |
| CLI-2026-01230 | original | reviewed | (negative) | 69 |  |
| TEL-2026-00090 | original | reviewed | 15765 #3 | 54 |  |
| CLI-2026-01231 | original | draft-unverified | 15823 #1 | 48 |  |
| GMF-2026-00410 | easy | draft-unverified | 15804 #1 | 40 |  |
| GMF-2026-00311 | easy | draft-unverified | 15823 #1 | 39 |  |
| CLI-2026-01240 | easy | draft-unverified | 15765 #2 | 85 |  |
| CLI-2026-01241 | easy | draft-unverified | 15837 #1 | 58 |  |
| GMF-2026-00411 | easy | draft-unverified | 15802 #3 | 38 |  |
| CHSLD-2026-00051 | easy | draft-unverified | 15616 #1 | 42 |  |
| HOP-2026-00731 | easy | reviewed | 15639 #21 | 42 |  |
| URG-2026-04620 | easy | draft-unverified | 15052 #55 | 57 |  |
| DOM-2026-00021 | easy | draft-unverified | 15783 #2 | 40 |  |
| CLSC-2026-00133 | easy | draft-unverified | 15812 #3 | 43 |  |
| GMF-2026-00412 | medium | draft-unverified | 00341 #2, 15804 #1 | 72 |  |
| CLI-2026-01242 | medium | draft-unverified | 01323 #14, 15765 #23 | 77 |  |
| GMF-2026-00312 | medium | draft-unverified | 15785 #6, 15786 #5 | 48 |  |
| GMF-2026-00413 | medium | draft-unverified | 00431 #10, 15804 #16 | 68 |  |
| CLI-2026-01243 | medium | draft-unverified | 01005 #1, 15765 #13 | 86 |  |
| CHSLD-2026-00052 | medium | draft-unverified | 15615 #8, 15618 #9 | 40 |  |
| CHSLD-2026-00053 | medium | draft-unverified | 15617 #36, 15624 #49 | 66 |  |
| HOP-2026-00732 | medium | reviewed | 15638 #29 | 81 |  |
| HOP-2026-00733 | medium | reviewed | 15158 not_retrieved, 15639 #35 | 59 |  |
| URG-2026-04621 | medium | draft-unverified | 01323 #2, 15059 not_retrieved (best: overview #18) | 69 |  |
| DOM-2026-00022 | medium | draft-unverified | 00344 #1, 15781 #14 | 64 |  |
| GMF-2026-00414 | medium | draft-unverified | 08848 #3 | 57 |  |
| GMF-2026-00313 | hard | draft-unverified | 15803 #28 | 53 |  |
| CLI-2026-01244 | hard | draft-unverified | 00215 #33, 01166 #15, 15803 #21 | 77 |  |
| URG-2026-04622 | hard | reviewed | 15054 not_retrieved, 15060 not_retrieved, 15637 not_retrieved | 71 |  |
| CHSLD-2026-00054 | hard | draft-unverified | 00014 #3, 15265 #8, 15622 #11 | 63 |  |
| GMF-2026-00314 | hard | draft-unverified | 15188 #9, 15821 #1 | 58 |  |
| CLI-2026-01245 | hard | draft-unverified | 00205 #1 | 56 |  |
| HOP-2026-00734 | hard | reviewed | 15641 #6, 15643 #26 | 46 |  |
| URG-2026-04623 | hard | draft-unverified | 15064 #70 | 74 |  |
| CLI-2026-01246 | negative | draft-unverified | (negative) | 53 |  |
| GMF-2026-00415 | negative | draft-unverified | (negative) | 52 |  |
| GMF-2026-00315 | negative | draft-unverified | (negative) | 44 |  |

## Selection per note

| note | difficulty | expected codes | other retained | other possible | invented | cands | error |
|---|---|---|---|---|---|---|---|
| URG-2026-04471 | original | 15058 ✗ not offered | 15658 | 00062, 15657, 15656, 15055 |  | 72 |  |
| URG-2026-04512 | original | 01323 ✗ not offered, 15052 ✗ not offered | 15055 | 01320, 00060, 00061, 00062, 15656, 15657 |  | 72 |  |
| URG-2026-04538 | original | 15058 ✗ not offered | 15657 | 00006, 15658 |  | 89 |  |
| CLI-2026-01187 | original | 15823 ✓ | – | 15819 |  | 59 |  |
| CLI-2026-01203 | original | 15803 ~ possible | 15790 | 00113, 00118, 15789, 15801, 00111, 00127 |  | 89 |  |
| CLI-2026-01220 | original | 15801 ✓ | – | 15765, 15773, 08775 |  | 54 |  |
| CLI-2026-01221 | original | 15803 ✓ | – | – |  | 39 |  |
| GMF-2026-00301 | original | 15805 ✓ | – | 15159, 15144 |  | 36 |  |
| GMF-2026-00302 | original | 15144 ~ possible, 15811 ✓ | 00474 | 15809 |  | 58 |  |
| GMF-2026-00303 | original | 15813 ✓ | – | 00474, 08877 |  | 57 |  |
| CLI-2026-01222 | original | 15767 ~ possible | 15775 | – |  | 73 |  |
| CLI-2026-01223 | original | 15765 ~ possible | 08775 | 15773 |  | 67 |  |
| CLI-2026-01224 | original | 15803 ~ possible | 08776 | 15801 |  | 63 |  |
| CLI-2026-01225 | original | 08777 ✓ | 00431 | 15789, 15790, 00458 |  | 69 |  |
| CLI-2026-01226 | original | 15765 ✓ | – | 15773 |  | 80 |  |
| GMF-2026-00304 | original | 15790 ✓ | – | 09910, 15789, 08777 |  | 64 |  |
| CLI-2026-01227 | original | 08857 ✗ offered | 15821 | 15775, 15767, 15819, 15823 |  | 74 |  |
| CLI-2026-01228 | original | 15803 ✓ | – | 15801, 15765 |  | 52 |  |
| GMF-2026-00305 | original | 15783 ✓ | – | 15779, 15835, 15837, 15839, 15784 |  | 59 |  |
| GMF-2026-00306 | original | 15839 ✓ | – | 15835, 15837, 15771 |  | 59 |  |
| CLI-2026-01229 | original | 15803 ✗ offered | 08994 | 00474, 08996, 15053 |  | 54 |  |
| GMF-2026-00307 | original | 15188 ✓, 15823 ✓ | – | 15821, 15819, 15767, 15775 |  | 67 |  |
| CLI-2026-01230 | original | (negative) | – | – |  | 69 |  |
| TEL-2026-00090 | original | 15765 ✓ | – | 15773 |  | 54 |  |
| CLI-2026-01231 | original | 15823 ✓ | – | 15819, 15821 |  | 48 |  |
| GMF-2026-00410 | easy | 15804 ✓ | – | 08776, 15802, 15766, 15774 |  | 40 |  |
| GMF-2026-00311 | easy | 15823 ✓ | – | 15819, 15821 |  | 39 |  |
| CLI-2026-01240 | easy | 15765 ✓ | – | 00402, 15773 |  | 85 |  |
| CLI-2026-01241 | easy | 15837 ✓ | – | 15835, 15839 |  | 58 |  |
| GMF-2026-00411 | easy | 15802 ✓ | – | – |  | 38 |  |
| CHSLD-2026-00051 | easy | 15616 ✓ | – | 15617, 15818, 15838, 15770, 15772 |  | 42 |  |
| HOP-2026-00731 | easy | 15639 ~ possible | – | 15640, 15649 |  | 42 |  |
| URG-2026-04620 | easy | 15052 ~ possible | – | 00060, 15656, 15657 |  | 57 |  |
| DOM-2026-00021 | easy | 15783 ✓ | – | 15784, 09063, 09100, 09101 |  | 40 |  |
| CLSC-2026-00133 | easy | 15812 ✓ | – | 15145, 15810, 15144 |  | 43 |  |
| GMF-2026-00412 | medium | 00341 ✓, 15804 ✓ | – | 00340, 15802 |  | 72 |  |
| CLI-2026-01242 | medium | 01323 ~ possible, 15765 ✓ | – | 15773, 01326 |  | 77 |  |
| GMF-2026-00312 | medium | 15785 ✓, 15786 ✓ | – | 08862, 08863 |  | 48 |  |
| GMF-2026-00413 | medium | 00431 ~ possible, 15804 ~ possible | 08776, 00430 | – |  | 68 |  |
| CLI-2026-01243 | medium | 01005 ✓, 15765 ✓ | – | 15773 |  | 86 |  |
| CHSLD-2026-00052 | medium | 15615 ✓, 15618 ✓ | – | 15616, 15617, 15838, 15818 |  | 40 |  |
| CHSLD-2026-00053 | medium | 15617 ✗ offered, 15624 ✓ | 15616 (variant of 15624) | 15623, 15625, 01320, 01322, 01325, 01327 |  | 66 |  |
| HOP-2026-00732 | medium | 15638 ✓ | – | 15640, 30010, 00340, 08280, 09313 |  | 81 |  |
| HOP-2026-00733 | medium | 15158 ✗ not offered, 15639 ✗ offered | 15640 (variant of 15639) | 15649, 15770, 15778, 15772 |  | 59 |  |
| URG-2026-04621 | medium | 01323 ~ possible, 15059 ✗ not offered | 01325, 15660 | 01320, 01322, 09234 |  | 69 |  |
| DOM-2026-00022 | medium | 00344 ✓, 15781 ✗ offered | 15778 | 15770, 00341 |  | 64 |  |
| GMF-2026-00414 | medium | 08848 ✓ | – | 15841, 15844, 08819 |  | 57 |  |
| GMF-2026-00313 | hard | 15803 ✗ offered | 15790 | 15789, 08819 |  | 53 |  |
| CLI-2026-01244 | hard | 00215 ✓, 01166 ✓, 15803 ✓ | – | 00328, 15765, 01184, 01222 |  | 77 |  |
| URG-2026-04622 | hard | 15054 ✗ not offered, 15060 ✗ not offered, 15637 ✗ not offered | 30010 | 15057, 00734, 08885, 15646, 00478 |  | 71 |  |
| CHSLD-2026-00054 | hard | 00014 ✓, 15265 ✓, 15622 ~ possible | 15624 (variant of 15622) | 15234, 00013, 15616, 15617 |  | 63 |  |
| GMF-2026-00314 | hard | 15188 ✓, 15821 ✓ | – | 15775, 15819, 15823 |  | 58 |  |
| CLI-2026-01245 | hard | 00205 ✓ | – | – |  | 56 |  |
| HOP-2026-00734 | hard | 15641 ~ possible, 15643 ✓ | 15638 (variant of 15643) | 15640, 15648, 15642, 08948 |  | 46 |  |
| URG-2026-04623 | hard | 15064 ✗ offered | 15061, 30010, 08968 | 15055, 15058, 00340 |  | 74 |  |
| CLI-2026-01246 | negative | (negative) | – | – |  | 53 |  |
| GMF-2026-00415 | negative | (negative) | – | – |  | 52 |  |
| GMF-2026-00315 | negative | (negative) | – | – |  | 44 |  |


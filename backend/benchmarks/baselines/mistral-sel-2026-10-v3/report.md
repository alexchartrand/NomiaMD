# Benchmark run `mistral-sel-v3`

|  |  |
|---|---|
| stages | selection |
| query source | summary |
| summaries from | mistral-2026-10-v2 |
| candidates from | mistral-2026-10-v2 |
| chat provider / summary model | mistral / – |
| selection model | mistral-medium-latest |
| embeddings | mistral / mistral-embed |
| codes table | codes_2026-09-17 (manual 2026-09-17) |
| retrieval | similarity_top_k=20, fused_top_k=40, rrf_k=60, max_family_size=6, kept_sources=visit |
| notes | 58 |
| git | d793cc8afa |
| fixture | tests/fixtures/eval_billing_codes.jsonl (5dbc9ecdcf) |
| updated | 2026-10-08T17:08:53+00:00 |

## Selection

Precision, recall, F1 and exact notes are on the codes the model is sure of (*retained*: what the review ticks), over the notes with expected codes (micro: over code positions). *overall recall*: expected codes found retained or among the other possible codes. *left out*: offered, in neither tier — a selection miss; *not offered*: a retrieval miss; *wrong variant*: a wrong retained code from an expected code's family; *clean negatives*: nothing returned in either tier.

| group | notes | codes | retained | precision | recall | F1 | exact notes | overall recall | possible/note | left out | not offered | wrong variant | clean negatives | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all** | 58 | 75 | 84 | 57% | 64% | 60% | 50% | 76% | 2.3 | 9 | 9 | 3 | 4/4 | 0 |
| difficulty: easy | 10 | 10 | 10 | 80% | 80% | 80% | 80% | 90% | 2.3 | 0 | 1 | 1 | – | 0 |
| difficulty: hard | 8 | 16 | 19 | 47% | 56% | 51% | 38% | 62% | 2.8 | 2 | 4 | 1 | – | 0 |
| difficulty: medium | 12 | 22 | 20 | 75% | 68% | 71% | 42% | 86% | 2.6 | 2 | 1 | 1 | – | 0 |
| difficulty: negative | 3 | 0 | 0 | 0% | 0% | 0% | 0% | 0% | 0.0 | 0 | 0 | 0 | 3/3 | 0 |
| difficulty: original | 25 | 27 | 35 | 46% | 59% | 52% | 46% | 70% | 2.2 | 5 | 3 | 0 | 1/1 | 0 |
| labels: draft-unverified | 41 | 54 | 55 | 71% | 72% | 72% | 66% | 83% | 2.1 | 5 | 4 | 2 | 3/3 | 0 |
| labels: reviewed | 14 | 17 | 24 | 33% | 47% | 39% | 15% | 65% | 2.5 | 2 | 4 | 1 | 1/1 | 0 |
| labels: to_review | 3 | 4 | 5 | 20% | 25% | 22% | 0% | 25% | 3.0 | 2 | 1 | 0 | – | 0 |

Macro precision 63%, macro recall 65%; 1.4 retained and 2.3 possible codes per note; 12% of returned codes ask for a confirmation.

Invented codes (returned but never offered, dropped): 0 (0% of the raw codes), in 0 note(s); malformed entries: 0.

| tier | confidence | returned | correct | precision |
|---|---|---|---|---|
| retained | high | 70 | 48 | 69% |
| retained | medium | 11 | 0 | 0% |
| retained | low | 3 | 0 | 0% |
| possible | high | 2 | 0 | 0% |
| possible | medium | 79 | 9 | 11% |
| possible | low | 51 | 0 | 0% |

## Cost and latency

| stage | kind | purpose | model | cached | calls | input tok | output tok | mean in / out | latency ms p50 / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| selection | chat | billing_codes | mistral-medium-latest |  | 58 | 647,996 | 53,802 | 11,172 / 928 | 7,629 / 12,359 / 12,966 |

| stage | wall ms per note p50 / p95 / max |
|---|---|
| selection | 7,637 / 12,366 / 12,976 |

## Selection compared with `mistral-sel-v2`

regressed: 11, mixed: 8, improved: 6, unchanged: 33

| verdict | note | difficulty | retained: gained | lost | new wrong | wrong fixed | overall: gained | lost |
|---|---|---|---|---|---|---|---|---|
| regressed | URG-2026-04512 | original | – | 01323 | 02704 | – | – | – |
| regressed | CLI-2026-01222 | original | – | – | 15775 | – | – | – |
| regressed | CLI-2026-01224 | original | – | – | 09928 | – | – | – |
| regressed | CLI-2026-01225 | original | – | – | 08776 | – | – | – |
| regressed | CLI-2026-01226 | original | – | – | 00553 | – | – | – |
| regressed | CLI-2026-01229 | original | – | – | 00474 | – | – | – |
| regressed | GMF-2026-00302 | original | – | – | 00474 | – | – | – |
| regressed | GMF-2026-00313 | hard | – | – | – | – | – | 15803 |
| regressed | HOP-2026-00732 | medium | – | – | 09234 | – | – | – |
| regressed | URG-2026-04471 | original | – | – | 00474 | – | – | – |
| regressed | URG-2026-04623 | hard | – | – | 08802 | – | – | – |
| mixed | CLI-2026-01227 | original | – | 08857 | 15775 | 15819 | – | 08857 |
| mixed | CLI-2026-01203 | original | – | – | 00604, 15790 | 00113, 00118, 15789 | – | – |
| mixed | CLI-2026-01243 | medium | 15765 | 01005 | 01006 | – | – | – |
| mixed | GMF-2026-00303 | original | – | – | 00400 | 00474 | – | 15813 |
| mixed | URG-2026-04622 | hard | – | – | 00340, 15777 | 00341 | – | – |
| mixed | CHSLD-2026-00054 | hard | – | – | 15234 | 15617, 15624 | – | – |
| mixed | GMF-2026-00413 | medium | 00431 | – | 08776 | 00430 | 15804 | – |
| mixed | URG-2026-04538 | original | – | – | 15773 | 15192 | – | – |
| improved | CHSLD-2026-00053 | medium | – | – | – | 01320 | 15617, 15624 | – |
| improved | CLI-2026-01244 | hard | 00215 | – | – | 01184 | 00215 | – |
| improved | CLSC-2026-00133 | easy | 15812 | – | – | 15832 | – | – |
| improved | GMF-2026-00305 | original | 15783 | – | – | 15837 | – | – |
| improved | HOP-2026-00734 | hard | 15643 | – | – | – | – | – |
| improved | TEL-2026-00090 | original | 15765 | – | – | 15789 | – | – |

## Selection per note

| note | difficulty | expected codes | other retained | other possible | invented | cands | error |
|---|---|---|---|---|---|---|---|
| URG-2026-04471 | original | 15058 ✗ not offered | 15192, 00474 | 08800, 15847, 08966, 15633 |  | 61 |  |
| URG-2026-04512 | original | 01323 ~ possible, 15052 ✗ not offered | 02704 | 01320, 01322, 01325, 02014, 02015 |  | 74 |  |
| URG-2026-04538 | original | 15058 ✗ not offered | 15773 | – |  | 86 |  |
| CLI-2026-01187 | original | 15823 ✓ | – | 15821, 15819 |  | 61 |  |
| CLI-2026-01203 | original | 15803 ✗ offered | 15790, 00604 | 15789, 00113, 00118 |  | 80 |  |
| CLI-2026-01220 | original | 15801 ✓ | – | 15765, 15773 |  | 48 |  |
| CLI-2026-01221 | original | 15803 ✓ | – | – |  | 43 |  |
| GMF-2026-00301 | original | 15805 ✓ | – | 15807, 15159 |  | 40 |  |
| GMF-2026-00302 | original | 15144 ✗ offered, 15811 ✓ | 00474 | 15809, 15831 |  | 57 |  |
| GMF-2026-00303 | original | 15813 ✗ offered | 15833, 00400 | 15803, 08877 |  | 53 |  |
| CLI-2026-01222 | original | 15767 ✓ | 15775 | – |  | 61 |  |
| CLI-2026-01223 | original | 15765 ~ possible | 08775 | 15773, 08776, 08777 |  | 59 |  |
| CLI-2026-01224 | original | 15803 ~ possible | 08776, 09928 | 08775, 08777, 09971 |  | 54 |  |
| CLI-2026-01225 | original | 08777 ✓ | 08776, 00431 | 15789, 15790, 00201 |  | 66 |  |
| CLI-2026-01226 | original | 15765 ✓ | 00553 | 15773, 15789 |  | 72 |  |
| GMF-2026-00304 | original | 15790 ✓ | – | 08777, 15773 |  | 62 |  |
| CLI-2026-01227 | original | 08857 ✗ offered | 15775 | 15819, 15821, 15823 |  | 66 |  |
| CLI-2026-01228 | original | 15803 ✓ | – | 15801, 08776 |  | 42 |  |
| GMF-2026-00305 | original | 15783 ✓ | – | 15835, 15837, 15839 |  | 56 |  |
| GMF-2026-00306 | original | 15839 ✓ | – | 15835, 15837 |  | 60 |  |
| CLI-2026-01229 | original | 15803 ✗ offered | 08882, 00474 | 08994, 08996 |  | 48 |  |
| GMF-2026-00307 | original | 15188 ✓, 15823 ✓ | – | 15819 |  | 64 |  |
| CLI-2026-01230 | original | (negative) | – | – |  | 56 |  |
| TEL-2026-00090 | original | 15765 ✓ | – | 15773, 15894 |  | 56 |  |
| CLI-2026-01231 | original | 15823 ✓ | – | 15819, 15821, 15775 |  | 41 |  |
| GMF-2026-00410 | easy | 15804 ✓ | – | 15802 |  | 29 |  |
| GMF-2026-00311 | easy | 15823 ✓ | – | 15819, 15775 |  | 38 |  |
| CLI-2026-01240 | easy | 15765 ✓ | – | 15773 |  | 81 |  |
| CLI-2026-01241 | easy | 15837 ✓ | – | 15839, 15835 |  | 45 |  |
| GMF-2026-00411 | easy | 15802 ✓ | – | 15766, 15774 |  | 34 |  |
| CHSLD-2026-00051 | easy | 15616 ✓ | – | 15617 |  | 38 |  |
| HOP-2026-00731 | easy | 15639 ~ possible | 15640 (variant of 15639) | 15648, 15638, 15766, 15774, 15768 |  | 46 |  |
| URG-2026-04620 | easy | 15052 ✗ not offered | 08775 | 08776 |  | 58 |  |
| DOM-2026-00021 | easy | 15783 ✓ | – | 15784, 09100, 09063, 15763 |  | 37 |  |
| CLSC-2026-00133 | easy | 15812 ✓ | – | 15832, 15144, 00059 |  | 40 |  |
| GMF-2026-00412 | medium | 00341 ✓, 15804 ✓ | – | 00340, 15802 |  | 58 |  |
| CLI-2026-01242 | medium | 01323 ✓, 15765 ✓ | – | 15773, 01320 |  | 67 |  |
| GMF-2026-00312 | medium | 15785 ✓, 15786 ✓ | – | 08862, 08863, 15821, 15823 |  | 48 |  |
| GMF-2026-00413 | medium | 00431 ✓, 15804 ~ possible | 08776 | 15774 |  | 66 |  |
| CLI-2026-01243 | medium | 01005 ~ possible, 15765 ✓ | 01006 (variant of 01005) | 15773, 01451 |  | 84 |  |
| CHSLD-2026-00052 | medium | 15615 ✓, 15618 ✓ | – | 15617, 15816, 15818, 15836, 15838 |  | 50 |  |
| CHSLD-2026-00053 | medium | 15617 ~ possible, 15624 ~ possible | 09245 | 15616 |  | 63 |  |
| HOP-2026-00732 | medium | 15638 ✓ | 09234 | 15639, 15053, 15056, 09231, 09237, 15642 |  | 73 |  |
| HOP-2026-00733 | medium | 15158 ✓, 15639 ✗ offered | – | – |  | 58 |  |
| URG-2026-04621 | medium | 01323 ✓, 15059 ✗ not offered | – | – |  | 62 |  |
| DOM-2026-00022 | medium | 00344 ✓, 15781 ✗ offered | 15770 | 15778, 00341, 00340, 09063 |  | 62 |  |
| GMF-2026-00414 | medium | 08848 ✓ | – | – |  | 58 |  |
| GMF-2026-00313 | hard | 15803 ✗ offered | 08819 | 15790, 08848, 15789 |  | 50 |  |
| CLI-2026-01244 | hard | 00215 ✓, 01166 ✓, 15803 ✓ | 01300 | 01225, 01222, 01184, 15801 |  | 70 |  |
| URG-2026-04622 | hard | 15054 ✗ not offered, 15060 ✗ not offered, 15637 ✗ not offered | 15777, 00340, 00478, 15646 | 00341, 15655, 00474 |  | 76 |  |
| CHSLD-2026-00054 | hard | 00014 ~ possible, 15265 ✓, 15622 ✗ offered | 15234 (variant of 15265) | 15624 |  | 60 |  |
| GMF-2026-00314 | hard | 15188 ✓, 15821 ✓ | – | 15775, 15767 |  | 56 |  |
| CLI-2026-01245 | hard | 00205 ✓ | – | – |  | 51 |  |
| HOP-2026-00734 | hard | 15641 ✓, 15643 ✓ | – | 15650, 15652 |  | 40 |  |
| URG-2026-04623 | hard | 15064 ✗ not offered | 15646, 30010, 08802 | 15645, 15644, 08805, 00340, 00341, 00344 |  | 74 |  |
| CLI-2026-01246 | negative | (negative) | – | – |  | 51 |  |
| GMF-2026-00415 | negative | (negative) | – | – |  | 42 |  |
| GMF-2026-00315 | negative | (negative) | – | – |  | 35 |  |


# Extraction benchmark: results and how to read them

This folder holds the runs of `scripts/benchmark.py` (code in `app/benchmark/`). The benchmark replays the
extraction pipeline stage by stage over the 58 labeled notes of `consultations/`. Labels are in
`tests/fixtures/eval_billing_codes.jsonl`. This page covers what the runs have taught us so far and how to
read a new one without fooling yourself. For the commands, see the `scripts/benchmark.py` docstring and
CLAUDE.md's *Commands* section.

```
runs/<name>/        every run, gitignored: manifest.json, notes/<patient_id>/{summary,retrieval,selection}.json,
                    metrics.json, report.md
baselines/<name>/   runs worth comparing against later, committed (`promote <run> --as <name>`)
.cache/             embedding cache, gitignored
```

## Before trusting any number

- **The labels are drafts.** No expected code has been verified by a physician or billing expert. Only
  the `reviewed` ones went through a human review (see `consultations/README.md`). Several misses below
  look like label questions as much as model errors. A metric that moves on 2–3 notes may be the label
  that's wrong.
- **9 of the 75 expected codes are ER codes that are hard to reach.** Until 10/8 the ER codes 15052–15070
  and 15637 carried `requires_registered=True` in `codes_2026-09-17`. At the ER, "patient inscrit" means a
  non-admitted patient, not GMF registration, so eligibility filtered them out. Every run up to and including
  the baselines below shows them as *ineligible* / *not offered*. On those 7 ER notes the model then
  retained the closest wrong code: 12 of v3's 36 wrong retained codes. ramq-ingestion fixed the data on
  10/8 and patched `codes_2026-09-17` in place, so **those baselines no longer match the current table**.
  The fix alone didn't recover the codes: they were eligible but not retrieved (see *Codes tables*). The
  care setting brought them in on 10/9 (*Care setting* below): retrieval recall 88% → 97%.
- **Scores are computed at report time** against the fixture as it is now. Relabeling never needs a rerun:
  `report <run>` again.
- **The models aren't deterministic, even at temperature 0.** See the next section.

## Run-to-run variance

Two identical selection runs (`mistral-sel-v2` and `mistral-sel-v2-rerun`) used the same prompt, model,
candidates and summaries:

| | v2 | v2 rerun |
|---|---|---|
| expected codes retained | 44 | 44 |
| retained precision / recall | 59% / 59% | 59% / 59% |
| overall recall (both tiers) | 75% | 73% |
| per-note changes | | 15 of 58 notes, 9 of 75 expected codes changed status |

The totals barely move, but individual notes do: a code flips between *retained*, *possible* and *left out*
from one run to the next. The summary stage behaves the same way: in `mistral-v2` vs `mistral-v2-rerun`,
one note's code moved from rank #2 to #3.

Rules of thumb:
- **A change of about ±3 codes in a total is noise.** Rerun before believing it.
- **A single note that regressed or improved proves nothing.** Look for a pattern across several notes
  with the same cause, and read the model's `analysis` / `explanation` in `selection.json` to check that
  the cause is the one you think.
- **Before tuning a prompt, rerun the baseline once** (`run --name <base>-rerun ... --baseline <base>`).
  Its "compared with" section is the noise you're working against.

## How to compare two runs fairly

- Compare selection runs on the **same candidates** (`--stages selection --candidates-from <run>`). The
  only thing that changes is then the selection step, and no embedding call is made.
- Read the per-note comparison (`report <run> --baseline <base>`), not only the averages. A fix for one
  transcript can regress another.
- Check the breakdown by difficulty and label status: an average can hide a group that got worse.
- Check the cost table: output tokens and p50/p95 latency matter for the inbox batch.

## Retrieval (2026-10)

| run | candidates/note | recall (exact) | R@10 | R@40 | MRR | not retrieved |
|---|---|---|---|---|---|---|
| `mistral-2026-10` (baseline, first version) | 32 | 65% | 48% | 65% | 0.25 | 12 |
| `transcript-q`: query with the raw note | 20 | 47% | 36% | 47% | 0.19 | 26 |
| `combined-q`: summary + raw note | 38 | 69% | 48% | 69% | 0.24 | 11 |
| `mistral-2026-10-v2` (baseline, current) | 56 | **88%** | 59% | 83% | 0.29 | **0** |

- **The structured summary is worth it.** Querying with the raw note finds far fewer codes (47% vs 65%).
  Adding the note's own query to the summary's is mixed per note (14 regressed, 10 improved) for +4 points.
- **v2 finds every code it is allowed to find (66/66 eligible).** Three changes got it there:
  - the visit query is built from the encounter's form only and scoped to the manual's visit section;
  - families of up to 6 variants are completed;
  - every hit of the visit query is kept past the top-40 cut.
- **The price is longer candidate lists** (32 → 56 per note). Selection showed it was worth it: 5 correct
  selected codes came from ranks past 40 or from family completion, against about 40 wrong ones the
  model mostly rated low or medium.

## Selection: the `billing_codes` call (2026-10)

All four runs use mistral-medium on `mistral-2026-10-v2`'s candidates and summaries.

| run | prompt | retained/note | retained precision | retained recall | F1 | exact notes | overall recall | clean negatives | needs confirmation |
|---|---|---|---|---|---|---|---|---|---|
| `mistral-sel` | recall-first, one list | 1.6\* | 57% | 68% | 62% | 44% | 81% | 1/4 | 66% |
| `mistral-sel-v2` | two tiers | 1.3 | 59% | 59% | 59% | 48% | 75% | 4/4 | 12% |
| `mistral-sel-v2-rerun` | same as v2 | 1.3 | 59% | 59% | 59% | 48% | 73% | 4/4 | 10% |
| `mistral-sel-v3` | one code per service | 1.4 | 57% | 64% | 60% | 50% | 76% | 4/4 | 12% |
| **v3 + high-confidence rule** | (server-side, see below) | 1.2 | **69%** | **64%** | **66%** | **57%** | 76% | 4/4 | 12% |

\* `mistral-sel` predates the two tiers: its high-confidence codes stand in as "retained", which is what the
review used to pre-tick. Committed baseline: `baselines/mistral-sel-2026-10-v3`. Its own report shows the
"as run" numbers, since the rule is applied by `parse()` after these runs were recorded.

**Metric definitions.**
- *Retained*: the codes the model is sure of, which the review pre-ticks and inbox approve-all bills.
  Precision, recall, F1 and *exact notes* (retained codes exactly equal to the expected ones) are computed
  on them.
- *Overall recall*: expected codes found in either tier (retained or possible).
- *Clean negatives*: notes whose right answer is no code that came back with nothing at all.

**What each step taught us**

1. **The recall-first prompt (`mistral-sel`) lists everything.** It returned 4.4 codes per note at 25%
   precision:
   - 2–4 alternative visit codes per note;
   - codes whose own explanation said "ne s'applique pas";
   - `needs_confirmation` used as a generic "please check" on 66% of codes, though 50 of 58 notes had
     no unresolved fact.
   Its overall recall (81%) is the highest of all runs because of that generosity.
2. **The two-tier answer (`v2`) fixed the negatives and the hedging but over-tightened.** No-code notes came
   back empty (4/4), and confirmations fell to 12%. But "keep only one" made the model pick the specific
   visit code over the general one the labels expect: MSK 08775/08776 vs 15803/15765, 15832 vs 15812,
   15837 vs 15783, 15640 vs 15639. It also demoted codes billed on top of the visit: family meeting
   15643, death certificate 00014, pregnancy supplement 15144, the visit next to an injection 15804.
3. **"One code per service, general unless the specific one's conditions are documented" (`v3`) won back
   4 codes:** 00215, 00431, 15812 and 15783, all retained in v3 while both v2 runs missed them. It is just
   above the noise floor. Still missed: 15804, 15639, 15144, and 15803 on the MSK follow-up.
4. **Confidence is the strongest signal we have.** Across the v2/v3 runs, retained codes rated medium or
   low were right **2 times in 26**. High-confidence ones were right about 2 times in 3 (69% in v3). Since
   2026-10-08, `BillingCodesTask.parse` (now `SelectionParser`) turns a retained code without high confidence into a possible one.
   Re-scored on every stored run, the rule raises precision each time and loses at most 2 hits (v2):

   | run | as run (P / R / F1) | high-confidence rule (P / R / F1) |
   |---|---|---|
   | `mistral-sel-v2` | 59% / 59% / 59% | 64% / 56% / 60% |
   | `mistral-sel-v2-rerun` | 59% / 59% / 59% | 62% / 59% / 60% |
   | `mistral-sel-v3` | 57% / 64% / 60% | 69% / 64% / 66% |

5. **Low-confidence possible codes are almost never right.** v2 had 3 right in 126, the rerun 7 in 112,
   v3 none in 51. The review already folds them away. They aren't dropped server-side, because the
   rerun shows they occasionally hold a right code.
6. **The model never invented a code.** No run returned a code outside the candidate list, and none
   returned a malformed entry.
7. **Cost is stable across prompts.** About 11k input and 0.9–1k output tokens per note; p50 7.6–8.1 s,
   p95 12.3–13.5 s. Writing the `analysis` first costs about 100 output tokens.

## Codes tables (2026-10)

ramq-ingestion builds candidate tables beside the current one (`codes_<rev>__<variant>`, another model's
extraction). Compare one with a **control run on the current table made with the same code**, not with the
baselines above: those predate the ER data fix and the two-halves `HybridSearch` (10/9). Both runs below
run retrieval + selection (mistral-medium, the v3 prompt with the high-confidence rule) on
`mistral-2026-10-v2`'s summaries:

```
run --name <x> --stages retrieval,selection --summaries-from mistral-2026-10-v2 --codes-table <table>
```

| run | codes table | recall | R@5 / R@10 / R@20 / R@40 | MRR | retained P / R / F1 | exact notes | overall recall | input tok/note | p50 |
|---|---|---|---|---|---|---|---|---|---|
| `current-table-sel` (control) | `codes_2026-09-17` | 88% | 43 / 57 / 67 / 81 | **0.32** | 65% / 61% / 63% | 56% | 79% | 11.8k | 7.2 s |
| `sonnet-sel` | `codes_2026-09-17__claude-sonnet-4-6` | 87%\* | 40 / 52 / 68 / 81 | 0.27 | 61% / 57% / 59% | 48% | 76% | 13.0k | 8.1 s |

\* 65 exact + 15622 offered only as a sibling variant.

- **The Sonnet table isn't better.** Selection is 3 correct retained codes behind (43 vs 46), which is at
  the noise level (9 notes regressed, 6 improved). Retrieval *is* worse: with cached embeddings and a fixed
  table it's deterministic, so the MRR drop is real. It also costs 10% more input tokens per note.
- **It moves add-ons up and visit codes down.** Procedures and add-ons rise (01166 #15→#1, 00431 #10→#1,
  15643 #26→#3, 08857 #58→#15, 15639 #35→#11). About 25 expected codes fall, mostly visit codes (15616
  #1→#11, 15790 #2→#13, 15839 #4→#12, 15765 #6→#17, psychotherapy 15785/15786 #5–6→#27–30). Its rows are
  templated: siblings share the same wording, with about 4 lexical terms instead of 7. So variants of one
  family are harder to tell apart (15617 now outranks 15616 on the CHSLD note).
- **The selection follows the rank.** Every code the Sonnet run lost moved down: 15785/15786 lost to
  08862/08863, 15616 to 15617, 15790 to 08777, and 00014. The codes it gained moved up: 15803 on GMF-00313
  (#28→#3), 15641, 00431, 01323. mistral-medium favours candidates near the top of the list, so the order
  of the candidates in the prompt is a lever of its own, whichever table is used.
- **The ER fix recovered nothing.** On the current table 7 of the 9 expected ER codes are still never
  offered (15052 and 15064 come in at #55 and #70 on one note each). They are eligible now, but the visit
  query surfaces 00006, 00057, 15645 and 15055 (« avec déplacement ») instead of 15058 (« sans
  déplacement »). Fixed by the care setting, next section.

## Care setting (2026-10-09)

The section-B-wide visit query's « urgence » ranks the « déplacement d'urgence » supplements (15633–15635,
15847–15849, 08966…) above every ER visit code. The encounter's care setting (`app/care_setting.py`; in the
app from the note's source or the physician, here from the fixture's `encounter_context`) now adds the same
visit query within the setting's own subsection (ER only for now), and states the setting in the prompt.
Same command as *Codes tables*, on `codes_2026-09-17`, compared with `current-table-sel`:

| run | recall | R@5 / R@10 / R@20 / R@40 | MRR | retained P / R / F1 | exact notes | overall recall | input tok/note |
|---|---|---|---|---|---|---|---|
| `current-table-sel` (control) | 88% | 43 / 57 / 67 / 81 | 0.32 | 65% / 61% / 63% | 56% | 79% | 11.8k |
| `care-setting-sel` | **97%** | 43 / 59 / 69 / 87 | 0.32 | 68% / 64% / 66% | 57% | **84%** | 11.9k |

- **Every expected ER visit code is offered now** (7 notes improved, none regressed). The 51 other notes plan
  the same queries as before, so their retrieval is identical. The two codes still missed are 01323 on
  URG-2026-04512 and 15158 on HOP-2026-00733, neither a visit code.
- **The ER codes are offered low**, #35–#70 on 5 of the 7 notes. The subsection query is one list among
  six to twelve, so its hits fall below the fused top-40 and come in as kept visit hits, after it. The
  model favours the top of the list (*Codes tables*), and the visit query's déplacement supplements are
  still above them. Fixed below.
- **Selection on the 7 ER notes:** retained correct 0 → 2 (15058 on 04471, 15060 on 04622), wrong retained
  9 → 5. 15052 and 15058 are offered but not picked on 04512/04538, 15064 on 04623. The selection changes
  on the 51 other notes (6 regressed, 4 mixed, 5 improved) are at the noise level, so the prompt's
  « Lieu de la consultation » line hasn't measurably moved them.

### ER notes: pinning and « patient inscrit » (2026-10-09)

Variants run on the 7 URG notes only (`--notes URG-…`), against `care-setting-sel`'s numbers on the same
notes. 11 expected codes; on 7 notes a difference of 1–2 codes is noise.

| run | ER codes ranked | retained | retained P / R | overall recall |
|---|---|---|---|---|
| `care-setting-sel` (both visit queries, ER hits after the cut) | #7–#70 | 7 | 29% / 18% | 36% |
| `er-a-subsection-only` (no section-B-wide visit query) | #3–#68 | 6 | 33% / 18% | 55% |
| `er-b-pinned` (ER subsection's hits first) | #2–#9 | 3 | 0% / 0% | 36% |
| `er-clarified-only` (prompt clarification, no pinning) | #7–#70 | 9 | 11% / 9% | 36% |
| `er-a-clarified` (no B-wide query + clarification) | #3–#68 | 8 | 25% / 18% | 45% |
| **`er-b-pinned-clarified`** (kept) | **#2–#9** | 8 | 25% / 18% | **64%** |

- **Pinning alone made selection worse.** With the ER codes on top, the model read them and ruled every one
  out: their descriptions say « d'un patient inscrit », and the prompt states « Le patient n'est pas
  inscrit auprès de ce médecin ». At the ER, « inscrit » means registered at the emergency department, as
  opposed to « admis » (P.G. 2.2.6 C), the same ambiguity as the upstream `requires_registered` data bug.
- **So the prompt now says so** when the care setting is the ER (`prompt.py`'s known facts). Alone it changes
  nothing (the codes are too far down to be read); with pinning, overall recall goes 36% → 64%.
- **What's left is the variant.** The model now retains ER codes, mostly the wrong one: « ordinaire »
  where the label says « principal » (04471, 04538), « avec déplacement » where it says « sans »
  (04512, 04621, 04622). The labels are drafts and these are judgment calls (BACKLOG.md).
- Both changes act only when the setting is the ER (the pinned query and the prompt line exist only then),
  so the other 51 notes are unchanged by construction; a retrieval rerun on the 7 notes after the cleanup
  gave identical candidates.
- On all 58 notes (`bedrock-cands`, next section) the pinning moves expected codes up without changing
  what is found: recall stays 97%, R@5 / R@10 / R@20 / R@40 go 43 / 59 / 69 / 87 → 49 / 68 / 79 / 93, MRR
  0.32 → 0.35.

## Selection models (2026-10-09, 2026-10-16 and 2026-10-19)

Nine chat models answer the same `billing_codes` prompt (v3, high-confidence rule, the ER « inscrit »
line) on the same candidates and summaries, so the model is the only thing that changes:

```
run --name <x> --stages selection --candidates-from bedrock-cands --selection-model <model id>
```

The candidates come from `bedrock-cands`, a retrieval-only run of the current pipeline (care setting, ER
hits pinned) on `codes_2026-09-17` over `mistral-2026-10-v2`'s summaries: 61 candidates per note, the same
two codes not retrieved as in `care-setting-sel`. mistral-medium, the control, goes through the Mistral API;
six others through Bedrock Converse (`LLM_PROVIDER=bedrock`); the two Augure models through Augure's
Canadian-hosted OpenAI-compatible API (`LLM_PROVIDER=openai_compatible
LLM_ENDPOINT=https://api.augureai.ca/v1`, the Augure key as `LLM_API_KEY`).

| run | model | retained P / R / F1 | correct / wrong retained | exact notes | overall recall | possible/note | clean negatives | notes worse / better\* | in / out tok per note | p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| `mistral-medium-sel` (control) | mistral-medium | 68% / 65% / 67% | 49 / 23 | 56% | **88%** | 2.7 | 4/4 | – | 11.9k / 940 | **7.4 / 11.9 s** |
| `augure-ossington-5-sel`† | Augure Ossington 5 | **78%** / **79%** / **78%** | **59** / **17** | **67%** | 87% | 0.8 | 4/4 | 2 / 11 | 12.5k / 2.8k | 29.6 / 61.6 s |
| `sonnet46-sel` | Claude Sonnet 4.6 | 74% / 69% / 72% | 52 / 18 | 57% | 85% | 1.3 | 4/4 | 5 / 8 | 15.3k / 1.2k | 16.8 / 26.1 s |
| `qwen3-vl-235b-sel` | Qwen3-VL 235B A22B | 75% / 67% / 70% | 50 / **17** | 59% | 85% | 2.1 | 2/4 | 7 / 8 | 13.3k / 1.2k | 20.4 / 87.0 s |
| `gpt-oss-120b-sel` | gpt-oss-120b | 68% / 65% / 67% | 49 / 23 | 57% | 76% | 2.7 | 2/4 | 9 / 9 | 11.4k / 1.4k | 8.3 / 20.5 s |
| `haiku45-sel` | Claude Haiku 4.5 | 69% / 64% / 66% | 48 / 22 | 50% | 79% | 1.3 | 4/4 | 8 / 7 | 15.3k / 1.2k | 10.6 / 18.3 s |
| `qwen3-next-sel` | Qwen3-Next 80B A3B | 62% / 64% / 63% | 48 / 29 | 54% | 85% | 4.2 | 1/4 | 7 / 7 | 13.3k / 1.6k | 19.3 / 31.1 s |
| `mistral-large3-sel` | Mistral Large 3 | 55% / 61% / 58% | 46 / 37 | 44% | 76% | 1.6 | 2/4 | 9 / 5 | 11.9k / 1.1k | 7.1 / 21.1 s |
| `augure-tofino-3-sel` | Augure Tofino 3 | 55% / 53% / 54% | 40 / 33 | 43% | 77% | 2.0 | 2/4 | 11 / 2 | 12.6k / 1.2k | 36.2 / 72.1 s |

\* Notes with fewer / more correct retained codes than the control (notes that lost one code and gained
another are left out).
† Run with `MAX_TOKENS` raised to 8192 in `app/llm/openai_client.py` (see *Reliability*).

1. **Ossington 5 is the first model past the noise.** 59 correct retained codes against 49, with 17 wrong
   against 23: +10 is three times the ±3 band, and it is worse on 2 notes, better on 11 — a pattern, not
   the 5–9 / 5–9 churn of the other models. The gain holds on both label groups: draft-unverified 88% / 91%
   retained P / R (control 79% / 76%), reviewed 50% / 47% (control 44% / 41%). It has run once; rerun it
   and the control before switching.
2. **Where Ossington 5 gains:** codes billed next to the visit (15188 on GMF-2026-00307, 15144 on
   GMF-2026-00302, psychotherapy 15785/15786 on GMF-2026-00312), the CHSLD variants (15616, 15617, 15622),
   15803 on two follow-ups, 15781 on DOM-2026-00022, and two ER codes (15058, 15064). It loses 15765 on
   CLI-2026-01226 and 15790 on GMF-2026-00304, the two label questions of point 4. It is the most decisive
   model: 0.8 possible codes per note (control 2.7) and 4% flagged for confirmation. That is why overall
   recall stays at 87%, one code short of the control.
3. **Of the other models, none clearly beats mistral-medium.** Correct retained codes range from 40 to 52
   against 49, inside the ±3 noise band except Mistral Large 3 and Tofino 3. Sonnet 4.6 and Qwen3-VL are
   more precise (74–75% vs 68%): they retain 17–18 wrong codes against 23. Sonnet also returns half as many
   possible codes (1.3 vs 2.7 per note), at the cost of a little overall recall (85% vs 88%). It flags 27% of
   returned codes for confirmation (control: 8%), but these aren't the generic hedging of `mistral-sel`: each
   one names the variant question and the alternative code (« Confirmer si la visite est qualifiée de
   complexe — si oui, utiliser 15773 à la place de 15765 »).
4. **Some misses are mistral-medium's own.** On GMF-2026-00307 every other model retains 15188 next to the
   visit, while mistral-medium leaves it possible. On DOM-2026-00022 six of eight retain 15781
   where mistral-medium retains the variant 15770. The reverse cases look like label or eligibility
   questions:
   - CLI-2026-01226's 15765 is retained only by mistral-medium and Qwen3-Next; the others pick 15789 or
     15773.
   - On GMF-2026-00304, Sonnet, Haiku, gpt-oss and both Augure models retain the MSK code 08777 instead of
     15790 (the designation gap, below).
5. **Tofino 3 is the weakest model.** 40 correct retained, 33 wrong, worse on 11 notes and better on 2.
   It mostly retains the wrong variant of the right visit family (15803 for 15811, 15619 for 15615, 15810
   for 15812, 15650 for 15641, 15773 for 15765), and it bills 09825 on a no-code note.
6. **ER notes (7 notes, 11 codes): every model still has the variant problem.** Correct retained ER codes:
   Haiku 6, Ossington 5 5, Sonnet / gpt-oss / Qwen3-VL 4, mistral-medium / Qwen3-Next 3, Mistral Large 3 and
   Tofino 3 1 (Mistral Large 3 with 11 wrong retained). On 7 notes, 1–2 codes is noise.
7. **Reliability.**
   - Qwen3-Next returned 2 codes outside the candidates and Mistral Large 3 one; `SelectionParser` dropped
     them.
   - gpt-oss-120b fails on URG-2026-04512, also on a forced rerun after the reasoning-leak fix (7e8008e): its
     output is `**analysis{` followed by blank lines, an `ExtractionOutputError`.
   - **The 4096-token output cap is too small for Augure's reasoning models**: their thinking counts toward
     it. Ossington 5 averages 2.8k output tokens per note and 6 notes used 4.3k–6.8k, so at 4096 they would
     fail; it ran with 8192 and failed none. Tofino 3 doesn't reason, yet its `analysis` ran away on
     CLI-2026-01230 and hit 4096 (an `ExtractionOutputError`). Ossington 4, Ossington 4.1, Rosedale 1 and
     GLM-5.3 failed a 2-note smoke test at 4096 (Augure answers 502 `reasoning_cutoff`, or the JSON is cut
     off) and haven't been run in full.
   - Only the Claude models, Ossington 5 and mistral-medium return nothing on all 4 no-code notes.
     Qwen3-Next also lists the most possible codes (4.2 per note, 146 of them low-confidence).
8. **Cost and latency.**
   - The Claude models tokenize the same prompt into about 15.3k input tokens against 11.9k for Mistral and
     12.5k for Augure, so compare prices per note, not per token.
   - Augure, in CAD: Ossington 5 costs about 1.57 $ per 58-note run (2.7 ¢ per note: 1.50 / 3.00 $ per million
     tokens in / out, most of the output being its thinking), Tofino 3 about 0.58 $.
   - Ossington 5's p50 is 4× mistral-medium's, Sonnet's 2.3×. Augure generates about 70 tokens/s (one
     timed `tofino-3` call); a smoke-test Ossington 5 call took 274 s, so watch the p95 on reruns.
   - Qwen3-VL's p95 comes from 3 calls of about 90 s out of 58; Qwen3-Next had one.
   - Bedrock, Augure and the Mistral API aren't the same path, so latencies aren't like-for-like.

Before switching models, commit a larger output cap (or one per model), then rerun the control and
Ossington 5 once each to confirm the gap; Sonnet 4.6 and Qwen3-VL are the fallbacks.

## Where the remaining misses are

- **ER visit variant** (*Care setting*): every ER visit code is offered near the top now, and the model
  retains one from the right family, but often the wrong variant (principal vs ordinaire, avec vs sans
  déplacement).
- **Eligibility gaps** that leave both variants in the list for the model to guess (BACKLOG.md, "Eligibility
  can't see several RAMQ conditions"):
  - the care setting: CHSLD-specific 15617/15624 vs the general emergency code 09245;
  - MSK visits needing a designation;
  - hospital unit level A/B.
- **Label questions**, waiting for a physician (BACKLOG.md, "Physician review of the selection judgment
  calls"): periodic vs pediatric intake, follow-up vs psychiatric evaluation, hospital intake vs follow-up,
  a visit billed next to an injection.

Tuning the prompt further against unverified labels risks fitting the labels' mistakes. The next gains are
more likely from the data fix, the eligibility axes and a label review than from prompt wording. Of the
selection models (*Selection models*), only Augure's Ossington 5 has shown a gain beyond the noise, in a single
run so far.

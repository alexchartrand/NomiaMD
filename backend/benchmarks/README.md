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
   2026-10-08, `BillingCodesTask.parse` turns a retained code without high confidence into a possible one.
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
  still above them.
- **Selection on the 7 ER notes:** retained correct 0 → 2 (15058 on 04471, 15060 on 04622), wrong retained
  9 → 5. 15052 and 15058 are offered but not picked on 04512/04538, 15064 on 04623. The selection changes
  on the 51 other notes (6 regressed, 4 mixed, 5 improved) are at the noise level, so the prompt's
  « Lieu de la consultation » line hasn't measurably moved them.

## Where the remaining misses are

- **ER visit codes offered too low** (*Care setting*): offered on every ER note now, but at #35–#70 on
  most, and the model still retains a wrong code on 5 of the 7.
- **Eligibility gaps** that leave both variants in the list for the model to guess (BACKLOG.md, "Eligibility
  can't see several RAMQ conditions"):
  - the care setting: CHSLD-specific 15617/15624 vs the general emergency code 09245;
  - MSK visits needing a designation;
  - hospital unit level A/B.
- **Label questions**, waiting for a physician (BACKLOG.md, "Physician review of the selection judgment
  calls"): periodic vs pediatric intake, follow-up vs psychiatric evaluation, hospital intake vs follow-up,
  a visit billed next to an injection.

Tuning the prompt further against unverified labels risks fitting the labels' mistakes. The next gains are
more likely from the data fix, the eligibility axes and a label review than from prompt wording.

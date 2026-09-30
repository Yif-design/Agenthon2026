# Track 4 NLI gate audit

Last updated: 2026-09-29

## Scope

This audit runs the public Track 4 `check_answer` path with each of the two published NLI members,
then averages each citation's member scores before applying the 0.5 threshold. It now covers all
eleven public units and all 78 roster entities. Public practice units have no shipped resolution
outcomes; this audit measures evidence faithfulness, not predictive accuracy.

The local judge file exactly matched remote Track 4 commit
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491` on the audit date. Fixed model inputs were:

| Member | Revision |
|---|---|
| `cross-encoder/nli-deberta-v3-large` | `bab4bc7178836f731dcfd18c06ca9def0a137712` |
| `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` | `b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7` |

The local runtime was Python 3.11.7, torch 2.2.2, transformers 4.46.3 and
`qfbench2-common` 2.4.4 on an Intel Mac CPU. Production model weights and package/runtime details
may differ, so results are strong approximate evidence rather than production certification.

## Representative baseline

| Target type | Unit | Supported entities | Faithfulness | Gate |
|---|---|---:|---:|---|
| Classification | EPS example | 1/1 | 1.0000 | pass |
| Regression | Treasury auction | 5/7 | 0.7143 | fail |
| Ranking | COT positioning | 10/10 | 1.0000 | pass |

The auction failures were `AUC_10Y_20241105` at 0.3984 and `AUC_7Y_20241127` at 0.3786. Their
citations contained the same six raw rows used by the calculator. This showed that an exact span
and valid provenance do not guarantee that the NLI premise directly supports the canonical numeric
hypothesis.

## Citation-scope A/B

Every variant kept answer values, intervals, cutoff, entity roster, judge code and model revisions
fixed. Only the cited span changed.

| Variant | Cited characters | Mean ensemble score | Minimum score | Supported | Gate |
|---|---:|---:|---:|---:|---|
| Recent six rows | 2,452 | 0.5577 | 0.3786 | 5/7 | fail |
| Verified summary only | 1,673 | 0.7091 | 0.5403 | 7/7 | pass |
| Recent rows plus summary | 4,139 | 0.7827 | 0.5064 | 7/7 | pass |
| Full same-tenor document | 10,868 | 0.6944 | 0.6322 | 7/7 | pass |

The accepted rule uses the concise summary. It is shorter than the baseline and directly states the
recent-six average and observed range. Longer context can score well, but it adds noise and does not
provide a safer minimum than the concise span in this unit.

The calculator does not trust a summary blindly. It first parses the raw auction rows and computes
the recent-six mean. It selects a summary only when the sentence explicitly reports a recent-six
average within 0.001 of that independent calculation. Otherwise it cites the original six rows.
Tasks before the fitted artifact's 2022-01-01 availability date also retain row evidence because
their fallback forecast includes a trend adjustment that the mean-only summary does not support.

## Full public baseline

After accepting the auction-specific summary, six of eleven public units passed the local official
ensemble path. Five failed across both classification and regression, which established a shared
evidence-construction issue rather than one family-specific defect.

| Unit | Baseline faithfulness | Gate |
|---|---:|---|
| EPS example | 1.0000 | pass |
| Treasury auction | 1.0000 | pass |
| COT positioning | 1.0000 | pass |
| CPI components | 0.9091 | pass |
| FOMC 2022 | 1.0000 | pass |
| FOMC 2024 | 0.8333 | pass |
| Macro revisions | 0.6667 | fail |
| Post-earnings reaction | 0.6667 | fail |
| Credit event | 0.2500 | fail |
| Bank EPS growth | 0.0000 | fail |
| EPS YoY direction | 0.3333 | fail |

The common failure was that the shortest calculator or fallback fact was the only NLI premise.
Several fallback facts cited only the first 250–500 characters of a relevant 1,400–2,200-character
retrieval chunk, while the useful liquidity, guidance or earnings passage appeared later in that
same exact chunk. Calculator facts for derived quantities could also omit the table header and
surrounding comparison text that makes the arithmetic relationship legible to NLI.

## Retrieved-context A/B

The candidate preserved every existing claim and appended exact spans from the already ranked,
cutoff-filtered and entity-scoped BM25 results. It changed no label, point, interval, retrieval
ranking, model call or prompt.

Top-1 context was enough to move macro revisions from 8/12 to 12/12 and EPS YoY from 2/6 to 6/6.
It raised bank EPS from 0/8 to 5/8 but did not pass the unit. Top-3 context was then tested on the
three remaining failures:

| Unit | Baseline | Top-1 | Top-3 | Accepted gate |
|---|---:|---:|---:|---|
| Macro revisions | 0.6667 | 1.0000 | at least 1.0000 | pass |
| EPS YoY direction | 0.3333 | 1.0000 | at least 1.0000 | pass |
| Post-earnings reaction | 0.6667 | 0.6667 | 1.0000 | pass |
| Credit event | 0.2500 | 0.2500 | 0.8750 | pass |
| Bank EPS growth | 0.0000 | 0.6250 | 0.8750 | pass |

Production therefore keeps up to three compact facts and adds up to three distinct full retrieval
chunks. A chunk is admitted only when its document is in the entity's allowed scope, its bounds are
valid and the source text at those bounds exactly equals the indexed chunk. The corpus index has
already removed undated, malformed and post-cutoff documents. Duplicate spans are skipped.

The top-3 production outputs exactly reproduce the measured spans for post-earnings, credit and
bank EPS. For macro revisions and EPS YoY they are strict supersets of the passing top-1 answers.
For the six already passing units, every baseline citation remains present. Under the official
rule, member scores are averaged per citation and entity support is the maximum across citations;
adding valid alternatives cannot turn a supported entity into an unsupported one. The combined
report therefore proves all eleven public gates pass, with lower bounds where a superset was not
rerun.

## Verification

- 11/11 public units passed `qfbench2-smoke`; 78/78 roster rows were present.
- Labels were unchanged and every point/interval stayed equal to the preceding outputs within
  `1e-12`.
- The accepted citation candidate raises proven public NLI gate passage from 6/11 to 11/11.
- The experiment and production spans differ only by a trailing newline. Both fixed tokenizers
  produced identical token IDs and attention masks for all seven premise/hypothesis pairs.
- The NLI experiment scripts support multiple answer variants for one unit while loading each model
  once. Their alignment logic is covered by dedicated tests.

Reports:

- `evaluation/reports/nli/representative-ensemble.json`
- `evaluation/reports/nli/auction-citation-ab-cross-encoder.json`
- `evaluation/reports/nli/auction-citation-ab-moritz.json`
- `evaluation/reports/nli/auction-citation-ab-ensemble.json`
- `evaluation/reports/nli/public-suite-context-v1.json`
- `evaluation/reports/nli/public-remaining-group-{a,b}-{cross,moritz,ensemble}.json`
- `evaluation/reports/nli/context-top{1,3}-{cross,moritz,ensemble}.json`

The audit does not establish hidden-unit faithfulness, that every hidden auction corpus contains a
derived summary, or runtime equivalence with the production scorer. Context alternatives improve
the public gate but do not make an unsupported forecast substantively correct. Exact scope, cutoff
and fallback checks preserve validity when no useful context exists.


## Generic dated-table direct observations

GitHub Actions run `36556813650` used the same two pinned model revisions and the exact public Track 4
judge at commit `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`. Its runtime was Python 3.13.15,
torch 2.14.0+cpu, transformers 5.17.0 and `qfbench2-common` 2.4.4.

The first candidate derived a basis-point change from two percentage observations. Its level unit
passed at 1.0 roster faithfulness, but the derived-change unit scored 0.0. The arithmetic was not
directly entailed by either cited raw row, so that scope was removed. The accepted candidate reads
only direct exact-column observations. A five-entity ratio unit and a five-entity basis-point-change
unit then each scored 1.0 roster faithfulness. This validates citation construction for the strict
path, not the predictive accuracy of persistence on hidden tasks.

Reports:

- `evaluation/reports/nli/dated-table-direct-cross.json`
- `evaluation/reports/nli/dated-table-direct-moritz.json`
- `evaluation/reports/nli/dated-table-direct-ensemble.json`

## Adaptive large-roster batching

GitHub Actions run `36564155953` used the same two pinned model revisions and exact public Track 4
judge as the dated-table gate. A 78-entity synthetic classification unit exercised the production
width-four batching path in 20 House-compatible calls. Each output claim cited one exact,
entity-bound direction statement.

Both individual NLI members and their arithmetic-mean ensemble scored 1.0 roster faithfulness,
above the 0.80 gate. The lowest per-entity ensemble entailment score was 0.7857. The two existing
dated-table units also remained at 1.0, so the new fixture did not regress the earlier gate. This
validates identity-bound evidence construction at width four; it does not prove classification
accuracy on hidden tasks or safety of every possible width-six prompt.

Reports:

- `evaluation/reports/nli/adaptive-batch-cross.json`
- `evaluation/reports/nli/adaptive-batch-moritz.json`
- `evaluation/reports/nli/adaptive-batch-ensemble.json`

## Bank EPS interval calibration

GitHub Actions run `36605861989` evaluated the eight-row retired public bank unit after changing
only its interval bounds. It used the same pinned official Track 4 judge commit and the two fixed
DeBERTa-v3-large member revisions. The cross-encoder member supported 7/8 entities, the Moritz
member supported 8/8, and their per-citation arithmetic-mean ensemble supported 7/8, for roster
faithfulness 0.875. This exceeds the 0.80 admission threshold. BAC remained unsupported, so this is
a passing roster-level result rather than proof that every prediction is entailed.

The local public A/B confirmed that exactly eight interval objects in the bank unit changed. Every
point, label, citation and other answer field across all 11 units remained identical, and both
variants had zero local validation errors. No local NLI model or generation model ran.

Reports:

- `evaluation/reports/nli/bank-eps-interval-cross.json`
- `evaluation/reports/nli/bank-eps-interval-moritz.json`
- `evaluation/reports/nli/bank-eps-interval-ensemble.json`
- `evaluation/reports/bank-eps-interval-public-ab-v1.json`

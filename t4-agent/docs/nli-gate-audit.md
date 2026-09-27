# Track 4 NLI gate audit

Last updated: 2026-09-27

## Scope

This audit runs the public Track 4 `check_answer` path with each of the two published NLI members,
then averages each citation's member scores before applying the 0.5 threshold. It covers one public
classification unit (`t4-EXAMPLE-eps-beat`), one regression unit
(`t4-auction-btc-202411-us7`) and one ranking unit (`t4-cotpos-202411-us10`). Public practice units
have no shipped resolution outcomes; this audit measures evidence faithfulness, not predictive
accuracy.

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

## Verification

- 11/11 public units passed `qfbench2-smoke`; 78/78 roster rows were present.
- The auction point forecasts and intervals stayed equal to the previous outputs within `1e-12`;
  the remaining ten unit answers were byte-identical.
- The experiment and production spans differ only by a trailing newline. Both fixed tokenizers
  produced identical token IDs and attention masks for all seven premise/hypothesis pairs.
- The NLI experiment scripts support multiple answer variants for one unit while loading each model
  once. Their alignment logic is covered by dedicated tests.

Reports:

- `evaluation/reports/nli/representative-ensemble.json`
- `evaluation/reports/nli/auction-citation-ab-cross-encoder.json`
- `evaluation/reports/nli/auction-citation-ab-moritz.json`
- `evaluation/reports/nli/auction-citation-ab-ensemble.json`

The audit does not establish that every hidden auction corpus contains a derived summary, or that
the remaining eight public units pass the full ensemble. Fallback behavior and the 11-unit smoke
suite preserve validity when no verified summary is available.

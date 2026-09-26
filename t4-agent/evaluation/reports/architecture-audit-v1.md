# Track 4 architecture audit v1

Date: 2026-09-27  
Production baseline: `139e4a9`  
Role: choose the next experiment from L1 to L5; this report does not accept a production change.

## Official evidence that changes priority

The current Track 4 README says the eleven published units are format exemplars rather than a
representative sample. The hidden set is substantially larger, spans all three target types, and
contains many families with no published counterpart. It also recommends a text-blind tabular
baseline before adding retrieval. These statements increase the overfitting risk of continuing to
optimize one published family at a time.

Verified current rules remain toolkit `v2.4.4`, 25 admitted House requests per unit, at most 4,000
output tokens per request, no cumulative token allowance, 600 seconds per unit and restricted
network. The actual serving input/context ceiling and Development House access remain unpublished.

Sources:

- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/Agenthon-2026/Agenthon2026-public/releases/tag/v2.4.4>
- <https://www.agenthon.net/guides/submission-format/>

## L1-L5 findings

| Level | Current evidence | Most important gap | Priority |
|---|---|---|---|
| L1 architecture | Deterministic fallback and bounded signal extraction work; 11/11 public smoke passes | No fair direct-vs-signal-vs-hybrid comparison | 1 |
| L2 shared capability | Cutoff filter, entity scoping, exact-span rejection and atomic fallback exist | Official prediction-bound NLI has not been run; unknown-family retrieval is broad | 2 |
| L3 target type | Output validation and ranking normalization exist | No shared tabular baseline or learned architecture selector by target type | 3 |
| L4 family | Eleven published shapes route to isolated calculators | Hidden families mostly have no public analogue | 4 |
| L5 coefficient | Several real time-forward calibrations exist | Further public-family tuning has the highest overfitting risk | 5 |

## Selected falsifiable hypothesis

Nemotron direct forecasts or a fixed 50/50 blend with the deterministic baseline may improve more
than one target type while retaining exact-span citations and bounded fallback. The first screen
uses identical task fields, cutoff-scoped BM25 excerpts, model, temperature and seed. It records
prediction quality, calibration, exact-span validity, calls, tokens and latency.

The eleven reconstructed public outcomes have influenced development. They are therefore a
development feasibility screen only. A direct or hybrid candidate cannot enter production from
this result. It must first pass a newly built, time-forward, previously unused holdout covering at
least two known families plus synthetic unknown-schema reliability cases.

## Pre-registered candidates

- **Signal/calculator:** current production answers.
- **Direct:** one task-level structured forecast call; any missing row, invalid number, invalid label
  or non-exact citation falls back row-wise to production.
- **Hybrid:** 50% direct and 50% production point forecast; an interval covering both component
  intervals around the blended point; direct classification label with production fallback.

No production code changes until the feasibility screen and the independent holdout both pass.

## Result

The exact free Nemotron-family endpoint completed eleven task-level calls with 139,272 prompt
tokens, 12,927 completion tokens, zero reported cost and no inference errors. Fifty-two of 78 rows
passed numeric, label and exact-quote validation; 26 fell back to the current production answer.

| Configuration | Mean predictive quality | Mean coverage | Mean pre-gate composite |
|---|---:|---:|---:|
| Current signal/calculator | 0.3864 | 0.6636 | 0.1878 |
| Guarded direct | 0.2576 | 0.3061 | 0.0012 |
| Fixed 50/50 hybrid | 0.2804 | 0.7221 | 0.1311 |

Direct and hybrid answers both passed 11/11 official smoke units, demonstrating again that schema
admissibility does not establish prediction quality. The task-level direct call collapsed every COT
score to zero, omitted most macro-revision rows and materially hurt several classification and
regression tasks. This candidate is rejected without spending a new holdout. The rejection applies
to one complete-roster call and the pre-registered fixed blend; smaller direct batches remain a
separate, falsifiable candidate.

Structured result: `evaluation/reports/architecture-ab-v1.json`.

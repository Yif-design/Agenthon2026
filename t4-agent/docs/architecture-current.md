# Current Track 4 architecture

Last updated: 2026-09-27

The submitted path is a baseline-first bounded workflow:

1. Load the task and cutoff-filter the frozen corpus.
2. Route the target to an isolated family specification.
3. Hard-scope documents by entity, series, tenor or shared macro source.
4. Retrieve evidence with BM25 and extract explicit numerical parameters deterministically.
5. Compute and atomically write a complete model-free baseline answer.
6. For families that need text judgement, batch up to three entities and ask the House-compatible
   model for five-level signals, explicit numbers and exact quotes.
7. Reject model facts with a foreign document, non-exact quote or invalid value.
8. Re-run the deterministic family calculator with accepted signals and parameters.
9. Normalize rankings, validate the complete answer, and atomically replace the baseline only when
   the enhanced answer is valid.

This design uses at most 18 requests by default, a 420-second model phase, 40-second request
timeouts and a circuit breaker. A failed API, invalid JSON or trace-write failure leaves the
already-written baseline answer intact.

## Why this remains the baseline

The bounded signal interface provides exact evidence validation, deterministic replay, low request
count and a reliable offline fallback. It also isolates retrieval errors from reasoning and
calculation errors.

It is not a permanent restriction. The official House model is Nemotron 3 Super 120B A12B, which
is materially stronger than the 7B model originally assumed. Direct prediction, model-generated
parameters, tool selection, thinking-enabled prompts and hybrid forecasts must be compared against
this baseline on cutoff-safe held-out outcomes before adoption.

## Current measured result

On the 11 retired public practice units with 78 independently reconstructed outcomes:

| Configuration | Calls | Input tokens | Output tokens | Cost | Mean predictive quality | Mean coverage | Mean pre-gate composite |
|---|---:|---:|---:|---:|---:|---:|---:|
| Model-free | 0 | 0 | 0 | 0 | 0.3122 | 0.5454 | 0.1058 |
| Nemotron 3 Super free, thinking off | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.5606 | 0.1581 |
| Same saved signals, accepted credit probability support | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6061 | 0.1662 |
| Same signals, plus accepted post-earnings interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6364 | 0.1753 |
| Same signals, plus accepted COT mean reversion and interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus accepted CPI interval floor | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |

These are diagnostic practice results, not a private leaderboard score. The official ensemble-NLI
gate has not yet been run locally.

For positioning rankings, the deterministic calculator now forecasts five-week change as `-0.2`
times current noncommercial net positioning as a percent of open interest. It accepts an exact
`net_pct_oi` field or selects the latest `net_pct_oi_YYYYMMDD` field, so hidden units are not tied to
the retired example date. Its 90% interval has a fixed 11.3 percentage-point half-width calibrated
only from the historical training/development period.

For CPI components, the existing point formula remains unchanged. The 90% interval uses the larger
of 1.65 times the nine-month historical standard deviation and a 0.75 percentage-point half-width.
The higher floor was selected on real-time ALFRED vintages and improved time-forward calibration;
it did not happen to change coverage on the single retired public CPI unit.

# Current Track 4 architecture

Last updated: 2026-09-26

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

These are diagnostic practice results, not a private leaderboard score. The official ensemble-NLI
gate has not yet been run locally.

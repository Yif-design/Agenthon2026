# Experiment methodology

1. Freeze the baseline commit, prompt configuration, model identifier and dataset checksum.
2. Change one primary hypothesis per candidate.
3. Run unit, schema, scope, citation and failure-mode tests first.
4. Select parameters on cutoff-safe train/dev data only.
5. Lock the candidate before running the time-forward holdout.
6. Compare the current official metrics: quality relative to the unit's declared naive answer,
   MAE/accuracy/rank correlation, mean interval score and interval quality. Record width and
   coverage only as diagnostics. For claims, run the scorer-version-matched deterministic rail and
   use contradiction NLI only when changed claims or citations make it decision-relevant. Also
   compare requests, tokens, latency and fallback rate.
7. Accept only when official gates do not regress and held-out predictive or reliability evidence
   improves enough to justify complexity.
8. Record accepted and rejected experiments; do not silently tune on the final holdout.

The retired public outcome set is useful diagnostics but is no longer an independent test after it
has influenced design. Every claimed family improvement needs a separate time split.

Scorer changes invalidate proxy metrics when their ordering can change. A candidate accepted under
the retired coverage-gap score must be re-audited before it is treated as current. Historical
reports remain immutable evidence of what was tested; a new report records the rescore and any
production rollback.

# Rolling-origin numerical evaluation

Historical numerical candidates must be evaluated in public-availability order. At an origin
`t`, a row is eligible as training evidence only when its `resolution_date < t`; observation dates
or target periods alone are insufficient. Rows from the same release/event origin are predicted
together before any of their outcomes can enter history.

Use whole-origin chronological development, time-forward test and confirmation partitions. Any
window, candidate, coefficient or interval rule selected from history must be recomputed from the
eligible prefix. Explicit and transformed schemas for one economic event share the same split and
selection decision. Report per-origin errors, family-macro metrics and leave-one-family-out results
so a large roster cannot dominate the conclusion.

The reusable implementation is `evaluation/rolling_origin.py`; the frozen-panel runner is
`evaluation/experiments/rolling_origin_reference_screen.py`. The runner is evaluation-only and
does not change production predictions.

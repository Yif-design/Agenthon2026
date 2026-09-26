# Experiment methodology

1. Freeze the baseline commit, prompt configuration, model identifier and dataset checksum.
2. Change one primary hypothesis per candidate.
3. Run unit, schema, scope, citation and failure-mode tests first.
4. Select parameters on cutoff-safe train/dev data only.
5. Lock the candidate before running the time-forward holdout.
6. Compare predictive quality, MAE/accuracy/rank correlation, interval coverage, NLI
   faithfulness, requests, tokens, latency and fallback rate.
7. Accept only when official gates do not regress and held-out predictive or reliability evidence
   improves enough to justify complexity.
8. Record accepted and rejected experiments; do not silently tune on the final holdout.

The retired public outcome set is useful diagnostics but is no longer an independent test after it
has influenced design. Every claimed family improvement needs a separate time split.

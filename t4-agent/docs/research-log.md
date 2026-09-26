# Research log

## 2026-09-26

### Official findings

- House identity is Nemotron 3 Super 120B A12B rather than the previously assumed 7B class.
- The model thinks by default; disabling thinking is supported but is a strategy choice.
- The 262,144 value is tokenizer metadata, not a promised serving context limit.
- The old cumulative token allowance is withdrawn. The operative budget is 25 admitted requests
  and 4,000 output tokens per request.
- Track 4 allows disclosed non-neural predictors and calibration artifacts, but no second language
  model or adapter in the submission image.

### Public implementation review

The GitHub search found one other clearly Track-4-specific participant repository:
<https://github.com/garroshub/agenthon2026-t4>, inspected at
`75efbb0ada0fff404a6df721dad6179790de24a2`. It has no repository license, so no code was copied.

Ideas independently worth testing against primary data:

- Direct House forecasts over batches rather than signal-only extraction
- Family-specific deterministic adapters for auction and EPS growth
- Cutoff-safe historical calibration for rate, EPS and classification intervals
- Wider probability support for credit-event intervals
- Reducing House calls through larger batches

The official strong-RAG scaffold independently recommends direct row-level prediction plus a
calibration head. Its claimed quality remains a specification pending staging validation.

### First model experiment

OpenRouter's exact public model-family endpoint was free on the research date. The first call failed
because the production client correctly denied provider data collection; a public-corpus-only,
explicit opt-in was added for development. A second incompatibility consumed the completion budget
as reasoning with no final content; mapping the local `T4_ENABLE_THINKING` setting to OpenRouter's
`reasoning.enabled` fixed it.

The complete thinking-off signal-extraction run improved mean predictive quality from 0.3122 to
0.3804 and mean pre-gate composite from 0.1058 to 0.1581 at zero cost. Credit-event accuracy rose
from 0.50 to 0.75 and EPS-YoY accuracy from 0.50 to 1.00. FOMC and post-earnings remained weak.

### FOMC interval calibration v1 — rejected

The experiment used official U.S. Treasury daily par-yield CSVs from 2000 through 2021. It fitted
35-trading-day absolute-move quantiles through 2016 and selected the quantile closest to 90% coverage
on 2017–2021. The selected 80th-percentile half-widths were 36–43 basis points depending on tenor,
with 91.2% development coverage. Neither the calibration script nor selection step read the 2022 or
2024 retired public outcomes.

After locking the artifact (`06bf01b45a28e4f77fc27218b7e8a9a7065d60af50ac6d31a9128c8898ddb20f`),
the one-time holdout check found 0% coverage for both the current +/-75 bp intervals and the candidate
intervals. Mean calibration loss stayed at 0.9, so the candidate was rejected. The failure indicates
that the current FOMC point model misses post-decision curve direction and magnitude; narrowing a
historical interval cannot repair it. The holdout report SHA-256 is
`cb2247567bdf13cf60b62c02eac637c692b6df64c32853fd6e8f671a6af04e4e`.

Next experiment: apply probability-domain interval bounds to credit-event forecasts. This is a
semantic invariant of the requested output, rather than a coefficient fitted to the retired cases.

### Credit probability support v1 — accepted

Credit-event point forecasts are probabilities, and there is no cutoff-safe population calibration
sample in the current bundle. Using the fixed probability support `[0, 1]` preserves point forecasts,
labels, retrieval, and citations. On the 11-unit diagnostic set, mean predictive quality stayed at
0.3804, mean coverage rose from 0.5606 to 0.6061, and mean pre-gate composite rose from 0.1581 to
0.1662. The full 30-test suite passed and the CLI produced all eight credit rows with the new legal
interval. The change is accepted, with the public-set and missing-NLI limitations recorded in the
experiment report.

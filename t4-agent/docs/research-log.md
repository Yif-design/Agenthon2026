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

### Thinking-on extraction v1 — rejected as the default

The exact public Nemotron endpoint was tested on the EPS teaching unit with identical retrieval,
prompt, temperature and seed. At the production extraction allowance of 700 output tokens, two
attempts exhausted the allowance without one parseable JSON object and opened the circuit breaker.
At the official maximum of 4,000 output tokens, one attempt returned valid JSON after 2,143 completion
tokens and about 23 seconds. Thinking-off returned valid JSON in 213 completion tokens. Thinking
changed the extracted signal from neutral to +1, but both paths produced the same final `1.50` /
`inline` forecast, so there was no measured output benefit to justify roughly ten times the completion
tokens. Thinking remains an opt-in experiment for tasks where it can change the scored answer.

### Submission-image checkpoint

GitHub Actions run <https://github.com/Yif-design/Agenthon2026/actions/runs/36243893020> passed unit
tests, linux/amd64 image build and push, and the container command smoke test. Immutable image:
`ghcr.io/yif-design/agenthon2026-t4@sha256:09ddf7a8cc9d027263255d26a1f2fa74256eb59768165d3c781b1dbd9a261d9b`.

### FOMC point models v1 — rejected

The research baseline follows the Federal Reserve's finding that Treasury yields are close to
non-stationary and that yield-only models rarely beat a no-change random walk consistently:
<https://www.federalreserve.gov/pubs/ifdp/2010/993/ifdp993.htm>. The level/slope/curvature candidate
follows the dynamic Nelson-Siegel interpretation described by Diebold and Li:
<https://www.nber.org/papers/w10048>.

A new dataset combines 152 official Federal Reserve policy statements with official Treasury daily
curves. A per-tenor curve-and-policy ridge selected on 2016–2018 improved development MAE to 13.91
bps, but deteriorated to 19.18 bps on the untouched 2019–2021 test, 34.8% worse than the 14.22 bps
zero-change baseline. It was rejected. The existing policy-decay rule scored 14.58 bps on test;
zero-change was slightly better on test but slightly worse on development. On the retired public
diagnostic pair, the two rules had identical average MAE and identical official-quality proxy scores.
Evidence was therefore insufficient to replace the current production point model with zero-change.
The structured report SHA-256 is
`8112b2acbc33dc265184915f23b23e8a757e51449da75c423cfe7872a1d7bfc5`.

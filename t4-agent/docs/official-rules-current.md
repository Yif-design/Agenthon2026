# Agenthon Track 4 current rules

Last verified: 2026-10-01.

Pinned official sources checked for this development round:

- Shared starter/toolkit main: `8c0b3f7bf031b595c2e45c2e488cdd33fbf0c7fd`
- Latest shared toolkit tag: `v2.5.1` (`50fb2dc2b39c70f4cf81fcd269943782eddfaed0`)
- Track 4 public main: `ede7381d8c1ba9d8c84068f9d142f5e093a33892`
- Track 4 scorer: `5.2.2`

The preceding project baseline used scorer semantics from Track 4 commit `7b2bce1` and toolkit
2.4.4. Its coverage-gap composite and roster-level 0.80 NLI gate are historical results, not the
current scoring contract.

## Scoring

A structurally valid unit uses:

```text
composite = 0.70 * predictive_quality + 0.30 * interval_quality
analysis_score = composite * (1 - F / (F + min(T, 3 * E)))
leaderboard_final = -0.27 + 1.27 * analysis_score + 0.25 * reasoning_score
```

Here `F` is the number of false claims, `T` the number of other claims and `E` the roster
size. With no false claim, the factor is 1. The reasoning score is in `[0, 1]`; the bonus is
uncapped, so the maximum final score is 1.25. With no judged reasons the reasoning contribution is
zero, so omitting reasons never subtracts from the analysis result. A structurally inadmissible unit
has analysis score 0 and is displayed as -0.27 before any reasoning bonus.

- Regression predictive quality is `naive_MAE / (naive_MAE + own_MAE)`.
- Classification quality is accuracy anchored so the unit's declared naive answer scores 0.5.
- Ranking uses Spearman rescaled to `[0, 1]`, then anchored against the stronger of the declared
  naive answer and the constant-forecast floor.
- A numeric unit's interval quality is `naive_IS / (naive_IS + own_IS)`, using mean interval
  score at the declared interval level. For a 90% interval, each row costs its full width plus
  twenty times any distance by which the realized value falls below `lo` or above `hi`.
- Interval quality is capped at `max(0.5, predictive_quality)`.
- Coverage remains a useful diagnostic but is not the scored interval statistic. Wide intervals
  pay through their width even when they cover every outcome.
- Pure-label units have no numeric interval leg.

A missing roster row, duplicate or unknown entity, missing required prediction, invalid interval,
NaN or Infinity is a whole-unit validation failure rather than a dropped row.

Source: the scorer and README at the pinned Track 4 commit above.

## Claims, citations and NLI

The former roster-level `faithfulness >= 0.80` admission gate is no longer the scoring rule.
Faithfulness is evaluated per claim and false claims reduce the unit through the factor above.

The deterministic claim rules run in Development and Final. A claim can be false for a wrong entity,
an out-of-range or malformed citation, an unanchored figure, excessive length, a citation longer
than 8,000 characters, content-free wording, or carrying the removed claim-level `citations`
list. Numbers that appear only inside a URL do not anchor a figure.

Development does not run the NLI contradiction check, but it does run the deterministic rules.
In Final, the pinned two-member DeBERTa ensemble adds the three-way contradiction check. The old
two-way entailment quantity remains a diagnostic named prediction relevance; it is not an
admission gate and does not prove a forecast is correct.

Each claim should be one short extractive fact supported by its own `doc_id`, `span_start` and
`span_end`. Computed changes, ratios, averages and forecasting derivations belong in the optional
top-level `submitted_reasons` field. The held-out reasoning grader compares up to three submitted
reasons with hidden target reasons for coverage, evidence grounding, inferential link and answer
consistency. Omitting `submitted_reasons` adds no reasoning bonus and does not reduce the analysis
score; a malformed block can still fail schema validation.

The project runs the official 5.2.2 deterministic claim rail without a local language model.
The tokenizer-specific 400-token claim cap remains unchecked unless the official judge tokenizer
is present. Heavy local dual-model NLI is not required for unchanged claims and is run remotely
when a changed claim or citation makes contradiction evidence decision-relevant.

## House model

The approved model is `nvidia/nemotron-3-super-120b-a12b`, snapshot and tokenizer revision
`rl-030326-fp8`. It is a 120B-parameter mixture-of-experts model with 12B active parameters.
The runtime model value comes from `MODEL_NAME`.

The model thinks by default. The route accepts
`chat_template_kwargs: {"enable_thinking": false}`. Production currently disables thinking
because the saved extraction A/B used materially fewer completion tokens without changing the
parsed signal. This is a project choice, not an official requirement.

The tokenizer metadata reports 262,144 tokens, but the organizer does not publish that value as a
guaranteed serving context window or accepted request size. The serving input ceiling and model
training cutoff remain unresolved.

Source: <https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/HOUSE-MODEL.md>.

## API and runtime

- `POST $MODEL_ENDPOINT/v1/chat/completions`
- bearer authentication via `MODEL_TOKEN`
- at most 25 admitted generation requests per unit
- at most 4,000 output tokens per request
- no published cumulative per-unit token allowance
- public Track 4 unit timeout: 600 seconds
- 16 CPU and 128 GiB Development grant; current cards request one B200
- restricted network; only the organizer House route is available at evaluation time
- non-root user, read-only root filesystem, 64 MiB `/tmp`, 64 MiB complete output tree
- Linux/amd64 image by immutable digest, anonymously pullable unless an organizer-confirmed
  private mirror is used

The current runtime document describes limits at the participant Development opening but does not
serve as an access-status announcement. Do not infer current account access from that wording;
check the competition site or an authorized Development run when access status matters.

Source:
<https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/DEVELOPMENT-RUNTIME.md>.

## Artifacts and restricted inference

The submitted agent may call only the injected House model. It may not bundle additional language
model weights or adapters. Deterministic code, statistical transformations, fitted linear/tree
models, thresholds and calibration parameters are allowed when their data, cutoff, selection and
license are disclosed.

Evaluation inputs and citations must come from the supplied task and frozen corpus. Vendor search,
vendor tools and personal API keys are not available in the restricted evaluation network. The
agent must still emit a valid answer when the House route fails.

The eleven published units are format exemplars, not a representative syllabus. Hidden evaluation
contains classification, regression and ranking tasks and many unpublished families, so public-row
hard-coding is not a generalization strategy.

## Submission and image notes

The image implements
`analyze --task /input/task.json --corpus /input/corpus --out /output/answer.json`.
The current project builds on GitHub's Ubuntu runner, publishes Linux/amd64, then pulls and runs the
immutable image. This avoids the macOS `com.apple.provenance` layer issue reported in Track 4
Issue 16.

Development allows 5 uploads per team per day and 20 total for Track 4 at the participant opening.
This development loop must not perform a formal competition submission or use the team key.

## Unresolved facts

- actual House serving input/context ceiling
- model training cutoff
- whether Final compute is identical to Development
- statistical output equivalence across House reruns
- account-specific Development availability unless checked through the authorized site or run

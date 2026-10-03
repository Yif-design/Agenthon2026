# Agenthon Track 4 current rules

Last verified: 2026-10-03.

Pinned official sources checked for this development round:

- Shared starter/toolkit main: `bd01548e34d21fd660d88fd06157078fb25ece4e`
- Latest shared toolkit tag: `v2.6.0` (`bd01548e34d21fd660d88fd06157078fb25ece4e`)
- Track 4 public main: `1c744e1d6725340643a533f436517d72b53ca0e1`
- Track 4 scorer: `5.2.2`

Toolkit 2.6.0 is an organizer-side contract/runtime update. The official release says existing
2.5.1 submissions remain valid. A direct blob comparison confirms that the Track 4 scorer,
`analysis.schema.json` and `submission.schema.json` are byte-identical to their preceding pinned
versions. The toolkit adds purpose-bound trust-store keys, the scored `not_reached` failure code,
stricter unit handles and Final leakage-scan support; none changes the T4 answer contract.

The preceding project baseline used scorer semantics from Track 4 commit `7b2bce1` and toolkit
2.4.4. Its coverage-gap composite and roster-level 0.80 NLI gate are historical results, not the
current scoring contract.

## Scoring

A structurally valid unit uses:

```text
composite = 0.70 * predictive_quality + 0.30 * interval_quality
analysis_score = composite * (1 - F / (F + min(T, 3 * E)))
development_board = -0.27 + 1.27 * analysis_score
final_score = -0.27 + 1.27 * analysis_score + 0.25 * reasoning_score
```

Here `F` is the number of false claims, `T` the number of other claims and `E` the roster
size. With no false claim, the factor is 1. The reasoning score is in `[0, 1]`; the bonus is
uncapped, so the maximum final score is 1.25. With no judged reasons the reasoning contribution is
zero, so omitting reasons never subtracts from the analysis result. Development does not grade
submitted reasons and its board shows only the analysis mapping. A structurally inadmissible unit
has analysis score 0 and is displayed as -0.27. The `-1000000000` sentinel means no unit was
scored; it is not a metric value.

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

The organizer's 2026-10-03 diagnosis in Track 4 Issue 20 confirms that Development House requests
are active: all ten units in the diagnosed run made 5–21 requests and none was refused. Image pull
time counts against each unit when pre-pull does not finish, so image size remains a reliability
concern. The current project image is about 44.2 MiB compressed, far below the 6 GiB image in that
diagnosis.

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

Every image must carry `qfbench2.interface_version="2.0"`. A missing label can allow every unit to
run yet stop record creation and scoring, as confirmed in Issue 20. The current image has the label.
The complete output tree also has a 4,096-node cap and stricter UTF-8/NFC path checks. A nonzero
process exit is `container_crashed` even when an answer exists; timeout and OOM retain their own
failure codes.

The C5 submission descriptor uses an `image` object with `registry`, `repository` and immutable
`digest` fields. A string image reference is invalid. `qfbench2 submission pack` derives `team_id`
and `descriptor_digest`; the tracked template deliberately omits those two generated fields.

Development allows 5 uploads per team per day and 20 total for Track 4 at the participant opening.
This development loop must not perform a formal competition submission or use the team key.

## Unresolved facts

- actual House serving input/context ceiling
- model training cutoff
- whether Final compute is identical to Development
- statistical output equivalence across House reruns
- account-specific Development availability unless checked through the authorized site or run

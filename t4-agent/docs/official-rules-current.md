# Agenthon Track 4 current rules

Last verified: 2026-09-27

Pinned development sources:

- Shared toolkit main: `95a0de3d9a814f3883c151b7efdbbcf579139244`
- Track 4 public main: `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`
- Installed `qfbench2-common`: `2.4.4`

## House model

The approved model is `nvidia/nemotron-3-super-120b-a12b`, snapshot and tokenizer revision
`rl-030326-fp8`. It is a 120B-parameter mixture-of-experts model with 12B active parameters, not a
7B model. The runtime alias comes from `MODEL_NAME` and is currently documented as `house`.

The reported tokenizer maximum-length metadata is 262,144 tokens. The organizer explicitly says
this is not a guaranteed serving context window or an allowed request size. No authoritative
serving input-token ceiling has been published. The training cutoff is unpublished.

The House model thinks by default. The route accepts
`chat_template_kwargs: {"enable_thinking": false}`. Our current production default disables
thinking, but this remains an experimental choice rather than an official requirement.

Source: <https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/HOUSE-MODEL.md>

## API and runtime

- `POST $MODEL_ENDPOINT/v1/chat/completions`
- `Authorization: Bearer $MODEL_TOKEN`
- 25 admitted generation requests per unit
- at most 4,000 output tokens per request
- no cumulative per-unit token allowance; the former 1,000,000 input plus 100,000 output figure is withdrawn
- Track 4 container ceiling: 600 seconds per unit
- 16 CPU quota, 128 GiB memory, one B200 requested by current Development cards
- restricted network; only the organizer House route is available at evaluation time
- non-root user, read-only root filesystem, 64 MiB `/tmp`, 64 MiB complete output-tree limit
- linux/amd64 image, immutable digest, anonymous public pull unless a private mirror handoff is confirmed

Development House access remains held according to the current runtime page. A local
OpenAI-compatible endpoint may be used to exercise the call shape.

Source: <https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/DEVELOPMENT-RUNTIME.md>

## Track 4 artifacts and evidence

The scored submission may use the House language model only. Additional language-model weights or
adapters cannot be bundled. Deterministic code, statistical transformations, fitted linear/tree
models, boosting models, thresholds and calibration parameters are permitted when their fitting,
selection and calibration data obey the relevant cutoff and are disclosed.

Evaluation-time inputs and citations must come from the supplied task and frozen corpus. The NLI
gate operates on a canonical hypothesis derived from the submitted prediction, not merely on the
participant's claim prose. A unit needs at least 0.80 roster-level faithfulness at a 0.5
per-citation entailment threshold and no embargo violation.

Sources:

- <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/ARTIFACT-POLICY.md>
- <https://github.com/Agenthon-2026/track4-analysis-public>

The official README states that the eleven published units are format exemplars, not a
representative syllabus. The hidden set is substantially larger, spans classification, regression
and ranking, and contains many families with no published counterpart. Architecture selection must
therefore test unknown schemas and cross-family behavior rather than optimize only published shapes.

## Unresolved official facts

- Actual serving context window and maximum accepted input size
- Participant access date for Development House runs
- Whether Final resources will exactly match Development resources
- House output equivalence across reruns beyond the documented statistical reproducibility rule

These unknowns must not be represented as confirmed limits.

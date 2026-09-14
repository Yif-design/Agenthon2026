# t4-agent - Track 4 design note

This directory holds our Track 4 agent. The current implementation is a first working skeleton: cutoff-safe lexical retrieval, deterministic fallback calculations, optional Qwen 7B row prediction through an OpenAI-compatible endpoint, exact-span citation grounding, and local validation.

## Decision

Use a fixed workflow with small model-judgment steps. Do not build a free-form agent that decides which tools to call, and do not build a complex skill registry in the first version.

Track 4 is a structured prediction task over a frozen corpus. The hard parts are schema safety, citation faithfulness, cutoff hygiene, and stable row coverage. A 7B model should act as an evidence judge, not as a programmer or tool orchestrator.

## Official Constraints That Shape The Design

The command contract is:

```bash
analyze --task /input/task.json --corpus /input/corpus --out /output/answer.json
```

Each output must include one prediction per entity row. Every row needs:

- `entity_id`;
- `label` for classification, or `point_forecast` for regression and ranking;
- `interval` with `level`, `lo`, and `hi`;
- one or more `claims` with `doc_id`, `span_start`, `span_end`, and `claim`.

The top-level `target_type` must match the task. The interval level is pinned by the card, normally `0.90`.

Faithfulness is a gate, not decoration. The judge checks whether a cited span supports the submitted prediction. It does not reward long explanations. If citations do not support enough row predictions, the submission can be ineligible even if the numeric predictions are good.

For ranking tasks, `point_forecast` is the scored value. Do not put the rank integer in `point_forecast`. If we include an optional `rank`, it must be a full permutation over the roster, but the score still comes from ordering `point_forecast`.

The public families are examples, not a closed list. The held-out set may contain unseen family shapes. The workflow must have a generic fallback.

## Skill And Tool Policy

Do not let the model freely call tools in version 1.

Use deterministic routing and fixed tool calls:

- the workflow reads `task.json` and decides the target type;
- the workflow chooses a short rubric based on target name, prompt text, and row fields;
- the workflow always runs retrieval;
- the workflow always runs the cheap table calculations that apply;
- the model receives the retrieved evidence, table facts, calculated facts, and rubric;
- the model returns a small intermediate JSON object;
- the workflow validates, repairs, grounds citations, and writes final `answer.json`.

Rubrics replace heavy skills. A rubric is a short prompt block, usually 300-800 tokens, such as "credit-event checks liquidity, debt maturities, covenant waivers, going concern language, ratings, and payment default language." The model does not choose external tools from the rubric.

## Workflow

```text
task.json + corpus/
        |
        v
Task Loader
        |
        v
Schema Planner
        |
        v
Family Router + Short Rubric
        |
        v
Cutoff-Safe Retriever
        |
        v
Deterministic Calculator
        |
        v
Row Predictor, one model call per entity
        |
        v
Citation Grounder
        |
        v
Cross-Row Normalizer
        |
        v
Validator + Fallback
        |
        v
answer.json
```

## Component Responsibilities

`Task Loader` reads `task.json` and extracts `task_id`, `schema_version`, `target`, `target_type`, allowed labels, `cutoff_date`, `resolution_date`, `interval_level`, and entity rows.

`Schema Planner` decides the required fields from `target_type`.

- Classification needs `label`, `interval`, and `claims`. `point_forecast` may be included when useful.
- Regression needs `point_forecast`, `interval`, and `claims`.
- Ranking needs `point_forecast`, `interval`, and `claims`. Optional `rank` is produced only after all rows are scored.

`Family Router` uses target name, prompt, family slug when present, and entity fields to choose a short rubric. Known routes include EPS direction, EPS growth, credit event, post-earnings reaction, rate curve, CPI component, macro revision, auction demand, and positioning shift. Unknown tasks use a generic tabular prediction rubric.

`Cutoff-Safe Retriever` indexes the frozen corpus into chunks with exact offsets. It must filter `doc_date <= cutoff_date` before scoring chunks. A stale document must never reach the model.

`Deterministic Calculator` computes simple values from task rows and extracted numbers. First-version tools should stay basic: `diff`, `pct_change`, `growth_rate`, `rank_values`, `safe_interval`, unit normalization, and label mapping. The model may see the results, but it should not be trusted to perform these calculations.

EPS beat/miss/inline tasks use a stricter tool path: the model may propose a target-quarter EPS forecast, but the workflow computes `beat`, `miss`, or `inline` from `consensus_eps` and `threshold_pct`. A guardrail rejects the common error of copying a pre-cutoff historical EPS number, such as a prior quarter EPS, into the target-quarter forecast.

`Row Predictor` calls the 7B model once per entity. The prompt contains task summary, entity fields, short rubric, calculated facts, and top evidence chunks. It asks for a strict intermediate JSON object, not the final answer.

`Citation Grounder` requires model evidence to include a verbatim quote. The workflow maps the quote back to exact `doc_id`, `span_start`, and `span_end`. If the quote cannot be found, the claim is dropped or replaced with the retrieved chunk's known span.

`Cross-Row Normalizer` enforces consistency after all rows are predicted. For ranking, it sorts rows by `point_forecast` and optionally assigns a full rank permutation. For classification, it maps off-vocabulary labels to allowed labels. For regression, it ensures point forecasts and intervals use the target's units.

`Validator + Fallback` prevents whole-unit failure. It checks exact roster coverage, legal labels, numeric points, interval bounds, interval level, non-empty claims, resolvable spans, and cutoff compliance. If the model fails, use conservative defaults and top retrieved evidence rather than emitting invalid JSON.

## Model Configuration For Local Experiments

Design for Qwen 7B first.

OpenRouter local experiment:

```bash
MODEL_ENDPOINT=https://openrouter.ai/api/v1
MODEL_NAME=qwen/qwen-2.5-7b-instruct
MODEL_API_KEY=...
```

Ollama local experiment:

```bash
MODEL_ENDPOINT=http://localhost:11434/v1
MODEL_NAME=qwen2.5:7b
```

Use low randomness:

- `temperature`: `0.0` or `0.1`;
- fixed `seed` when supported;
- no vendor tools;
- no web search;
- no model-side retrieval;
- one row per call.

## Token Budget Assumption

The official budget is per unit: `1,000,000` input tokens and `100,000` output tokens. This is not a single-call context window.

For 7B local simulation, target roughly:

- 3K-6K input tokens per entity;
- 300-800 output tokens per entity;
- 5-10 retrieved chunks per entity;
- one retry only when parsing fails.

For a 30-row task, this is usually around 90K-180K input and 9K-24K output, within the official unit budget.

## First Implementation Milestones

V0: model-free skeleton. Parse a public unit, index corpus chunks, output schema-valid conservative predictions with grounded fallback claims. Done.

V1: BM25 retrieval. Improve entity queries and cutoff filtering. Record retrieved chunks for debugging. First version done.

V2: Qwen 7B row predictor. Add strict intermediate JSON prompts and parsing. First version done.

V3: short rubrics. Add compact domain rubrics for known public families and a generic fallback.

V4: local evaluation harness. Save prompt hashes, model id, retrieved chunks, raw model output, parsed output, final answer, token usage, and smoke/schema results.

V5: parameter-extraction tools. Generalize the EPS guardrail pattern: model extracts parameters, deterministic tools compute labels or numeric transforms, and final answer generation uses tool outputs rather than raw model labels.

## Core Principle

Do not make the 7B model a programmer. Make it an evidence judge. The workflow owns retrieval, calculation, schema, citation grounding, and fallbacks.

## Local Commands

Model-free fallback run:

```bash
cd /Users/joezhou/PycharmProject/Agenthon2026-team/t4-agent
MODEL_ENDPOINT= /Users/joezhou/PycharmProject/Agenthon2026/.venv/bin/python -m t4agent.cli analyze \
  --task /Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units/t4-EXAMPLE-eps-beat/task.json \
  --corpus /Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units/t4-EXAMPLE-eps-beat/corpus \
  --out /tmp/t4-agent-example-noapi.json
```

OpenRouter Qwen 7B run:

```bash
cd /Users/joezhou/PycharmProject/Agenthon2026-team/t4-agent
MODEL_ENDPOINT=https://openrouter.ai/api/v1 \
MODEL_NAME=qwen/qwen-2.5-7b-instruct \
/Users/joezhou/PycharmProject/Agenthon2026/.venv/bin/python -m t4agent.cli analyze \
  --task /Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units/t4-EXAMPLE-eps-beat/task.json \
  --corpus /Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units/t4-EXAMPLE-eps-beat/corpus \
  --out /tmp/t4-agent-example-qwen7b.json
```

The program reads `MODEL_API_KEY` if set. For local OpenRouter experiments it can also read `.secrets/openrouter_api_key.txt`, which is git-ignored. Do not print or log the key.

## Current Test Status

Smoke-tested on 2026-09-15:

- model-free mode produced locally valid answers for all 11 public Track 4 units;
- official smoke verifier admitted all 11 model-free outputs through g0-g3;
- Qwen 7B API mode ran on the EPS example plus representative regression, ranking, and classification multi-row units;
- official smoke verifier admitted those Qwen 7B outputs too.
- EPS example was corrected after adding the EPS tool path: the first raw model output copied Q1 FY2024 EPS `2.18` and labeled `beat`; the guarded tool path returns `point_forecast=1.53` and `label=inline` for the Q2 FY2024 target.

Public units generally do not include resolved outcomes, so local smoke score is `null`; it checks admissibility, schema, roster, cutoff, and citation plumbing rather than leaderboard predictive quality.

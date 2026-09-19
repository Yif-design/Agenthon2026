# t4-agent - Track 4 design note

This directory holds our Track 4 agent. The current implementation uses cutoff-safe lexical retrieval, minimal observable deterministic models, optional House-model coarse-signal extraction, exact-span citation grounding, and local validation. Qwen 7B is retained only as a local behavioral approximation.

Detailed design notes:

- [Track 4 题型模型契约](docs/family-model-contracts-zh.md)：当前实现的权威设计；逐题定义输入白名单、计算方法、LLM 判断和缺失 fallback。
- [Track 4 最小可观测预测模型 V1](docs/t4-minimal-observable-model-v1-zh.md)：形成当前契约前的总体精简原则。
- [Track 4 各题型解法与工具设计](docs/t4-problem-solving-guide-zh.md)：逐一说明 11 个公开 unit 的输入、预测目标、解题步骤、参数和待实现工具，并包含隐藏题型通用解题器。
- [Track 4 family tool plan](docs/family-tool-plan.md)：面向代码实现的英文参数抽取与工具契约草稿。

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
- the workflow chooses a minimal family specification based on target name, prompt text, and row fields;
- the workflow always runs retrieval;
- the workflow computes baselines directly from task fields and historical tables;
- when text judgment is needed, the model returns only named signals on a five-level scale with verbatim evidence;
- the deterministic family tool turns baselines and signals into labels, points, intervals, and ranks;
- the workflow validates, grounds citations, and writes final `answer.json`.

The model cannot return a final label, probability, interval, beta, or confidence. Missing or ambiguous evidence becomes a neutral signal, and the deterministic baseline remains in place.

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
Family Router + Minimal Signal Spec
        |
        v
Cutoff-Safe Retriever
        |
        v
Entity / Series / Tenor Document Scope
        |
        v
Baseline And History Calculator
        |
        v
Optional Signal Extractor
        |
        v
EvidenceFact Validator
        |
        v
Deterministic Family Solver
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

`Family Router` uses target name and family slug to choose the permitted input fields and text signals. Unknown tasks use a generic one-signal baseline.

`Cutoff-Safe Retriever` indexes the frozen corpus into chunks with exact offsets. It filters `doc_date <= cutoff_date` before scoring chunks, then applies a hard entity scope before BM25: CIK for company filings, series ID for macro vintages, tenor for auctions, market ID for COT, and a documented shared-file scope for CPI and FOMC units. A stale or foreign-entity document must never reach the model.

`Baseline And History Calculator` computes values from task rows and parseable frozen tables. Macro revisions, auction history, CPI component history, and COT baselines do not require a model call.

`Optional Signal Extractor` calls the organizer-injected House model only for families that need simple text judgment or when a family parser cannot extract an explicit number. It returns named signals from `-2` to `+2`; the bank EPS parser normally extracts its two same-table EPS values without a model call. Every non-zero signal or extracted model value needs an entity-scoped quote. Historical-only, ambiguous, or missing evidence must return `0` or `null`. Shared task-level signals, such as FOMC policy direction, are extracted once and reused across rows.

`EvidenceFact Validator` turns model and deterministic extractions into typed facts carrying `entity_id`, value, `doc_id`, exact source span, quote, and extractor. Whitespace-only formatting differences may be normalized and mapped back to the original span. A foreign document, invented quote, or ungrounded number is rejected before the solver runs; rejected non-zero signals become neutral and rejected numbers become missing.

`Deterministic Family Solver` combines the baseline with a capped signal adjustment. It owns final points, labels, intervals, and ranking. EPS uses consensus or prior-year EPS; credit uses explicit risk-flag tiers; rates use one policy-direction signal and fixed maturity sensitivity; post-earnings reaction defaults to flat without explicit forward guidance.

`Citation Grounder` uses the facts actually consumed by the solver. Structured calculators return the historical rows used in their computation, and model-derived facts already carry their validated source span. A quote that cannot be mapped to the source is rejected; it is never replaced with an unrelated retrieved chunk. A scoped factual context passage is used only when the deterministic neutral fallback has no non-neutral fact, so output remains schema-valid without fabricating a prediction claim.

`Cross-Row Normalizer` enforces consistency after all rows are predicted. For ranking, it sorts rows by `point_forecast` and optionally assigns a full rank permutation. For classification, it maps off-vocabulary labels to allowed labels. For regression, it ensures point forecasts and intervals use the target's units.

`Validator + Fallback` prevents whole-unit failure. It checks exact roster coverage, legal labels, finite points, ordered intervals containing the point, non-empty claims, resolvable spans, cutoff compliance, and entity/document scope. If the model fails, use the family baseline and entity-scoped factual context rather than a generic cross-entity claim.

## Model Configuration

Official evaluation injects the House route. Do not set or package participant credentials:

```bash
MODEL_ENDPOINT=http://model:8443
MODEL_NAME=house
MODEL_TOKEN=<injected per-unit bearer>
```

The client calls `$MODEL_ENDPOINT/v1/chat/completions`, caps itself at 25 attempted calls per unit and caps `max_tokens` at 4,000. When the endpoint is unavailable it falls back to the deterministic family solvers and still writes a schema-valid answer.

Qwen 7B remains a local behavioral approximation only. It is not an eligible submitted model.

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

## Token Budget

The official budget is per unit: `1,000,000` input tokens, 25 admitted requests, and at most 4,000 output tokens per call. This is not a single-call context window. A retry can consume another request slot.

For 7B local simulation, target roughly:

- 3K-6K input tokens per entity;
- 300-800 output tokens per entity;
- 5-10 retrieved chunks per entity;
- one retry only when parsing fails.

For a 30-row task, this is usually around 90K-180K input and 9K-24K output, within the official unit budget.

## First Implementation Milestones

V0: model-free skeleton. Parse a public unit, index corpus chunks, output schema-valid conservative predictions with grounded fallback claims. Done.

V1: BM25 retrieval. Improve entity queries and cutoff filtering. Record retrieved chunks for debugging. First version done.

V2: OpenAI-compatible coarse-signal extractor with strict JSON and verbatim evidence. Done.

V3: minimal observable family specifications and deterministic solvers. Done.

V4: local evaluation harness. Each run writes `trace/route.json`, `trace/rows.json`, and `trace/usage.json`; row traces contain allowed documents, retrieved chunks, raw model output, validated and rejected facts, used fact IDs, derivation, fallback reason, and final prediction. Done.

V5: improve table parsers and calibrate model constants when labeled development outcomes become available.

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

Family-isolated model update tested on 2026-09-17:

- all 11 public units generated locally valid answers in model-free mode;
- the official smoke verifier admitted all 11 outputs;
- Qwen 7B signal extraction ran successfully on every public family that requires text judgment: EPS consensus, EPS YoY, credit event, post-earnings reaction, and the 2024 rate curve;
- deterministic same-table parsing extracted both bank EPS values for all eight public rows, so that family needs no model call on those documents;
- the official smoke verifier admitted all six representative API/parser-mode outputs;
- thirteen unit tests cover routing, strict and generic field whitelists, parameter extraction, EPS thresholds and bank arithmetic, credit tiers, rate maturity sensitivity, and CPI component identification.

Evidence-chain hardening tested on 2026-09-19:

- all 11 public units and all 78 rows completed with entity/series/tenor/market document scopes;
- the Qwen 7B API path completed every model-using family, while each FOMC unit used one shared policy call rather than six maturity calls;
- auction, COT, CPI, macro-revision and bank calculators cite the exact historical tables used in their derivations;
- all 11 API outputs passed the official smoke verifier;
- 21 tests cover cross-entity isolation, scoped BM25, rejection of foreign documents and invented quotes, whitespace-normalized quote-to-source mapping, deterministic replay, shared FOMC extraction, routing and family calculations;
- every local run writes complete ignored traces, and all 78 offline rows reproduced their calculator output exactly from recorded inputs.

Public units generally do not include resolved outcomes, so local smoke score is `null`; it checks admissibility, schema, roster, cutoff, and citation plumbing rather than leaderboard predictive quality.

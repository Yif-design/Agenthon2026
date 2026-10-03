# Track 4 proxy benchmark

This directory defines a local benchmark for choosing Track 4 architectures. It is not an attempt
to reconstruct the organizer's hidden set. The questions use the same contract and similar public
source classes, while deliberately covering targets and schemas beyond the eleven official practice
units.

## Status

`question_catalog.json` contains twenty question specifications. One question, proxy-18 COT
positioning rank, is now materialized as two runnable schema variants; the other nineteen remain
design records. A question becomes runnable only after its generator has produced a cutoff-safe
`task.json`, `card.toml`, `manifest.json`, frozen `corpus/`, hidden `reference/outcome.json`, and
`reference/naive_answer.json` with complete provenance.

The first control run is in `baselines/control-v1/` and
`../evaluation/reports/proxy-18-cot-control-v1.json`. It deliberately makes no production-change
claim: one event can verify the benchmark plumbing, but cannot establish hidden-family
generalization.

## Reproduce the materialized slice

Use the repository's existing Python 3.13 installation; no virtual environment or model API is
required.

```bash
python3.13 proxy-benchmark/build_cot_proxy.py
python3.13 proxy-benchmark/validate_proxy.py
python3.13 proxy-benchmark/run_control.py
python3.13 -m unittest tests.test_proxy_benchmark -v
```

The tracked source snapshot is sufficient for rebuilds. `--raw-cache
evaluation/cache/cot/legacy_2015_2023.json` recreates that snapshot from the earlier CFTC download,
but the cache is git-ignored and is not required for ordinary runs.

## Design goals

- Preserve the official Track 4 output contract: classification, regression, or ranking; a numeric
  point and 90% interval where applicable; and exact citations into a frozen corpus.
- Keep sources close to the competition: SEC filings and releases from BLS, BEA, Federal Reserve,
  Treasury, EIA, CFTC, and other public US-government publishers.
- Broaden what is predicted: level, change, growth, surprise, revision, probability, volatility,
  quintile, and cross-sectional rank.
- Test long documents, mixed tables and prose, multi-document evidence, shared macro context,
  renamed fields, unit conversions, missing fields, distractors, and reordered rosters.
- Separate input construction from outcome construction. No resolved outcome may enter the task,
  corpus, prompt, retrieval index, or production artifact.

## Catalog composition

| Target type | Count | Purpose |
|---|---:|---|
| Classification | 6 | Thresholds, probabilities, surprise bands, and direction labels |
| Regression | 8 | Levels, changes, ratios, revisions, and inventory quantities |
| Ranking | 6 | Whole-roster ordering and relative prediction |

Six questions are near-neighbor controls for published families. Fourteen are deliberately broader
families. Each economic question has two required schema variants, so the completed catalog should
yield at least forty runnable cases without collecting forty independent datasets.

## Required unit layout

```text
units/<unit-id>/
  task.json
  card.toml
  manifest.json
  corpus/*.json
  reference/outcome.json
  reference/naive_answer.json
  provenance.json
```

The agent receives only the first four paths. Local scoring receives `reference/`. The generator
must prove that every visible fact and corpus document was available by the unit cutoff. Observation
dates alone are insufficient for revised releases.

## Evaluation views

Every architecture comparison must report all four views:

1. chronological development;
2. time-forward test;
3. untouched confirmation;
4. leave-one-family-out, with both schema variants held out together.

Official practice units remain compatibility tests and may not select the proxy benchmark's model,
weights, prompts, or interval rules.

## Completion gate for a question

A question is complete only when:

- all entities have a reproducible resolved outcome and naive answer;
- source URL, release timestamp, license status, download timestamp, and SHA-256 are recorded;
- task inputs contain no post-cutoff values or outcome-derived features;
- the two schema variants preserve the same economic target and outcome;
- an official-format answer can be scored for the full roster;
- a generator rerun reproduces hashes or records an explicit upstream revision.

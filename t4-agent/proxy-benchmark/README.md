# Track 4 proxy benchmark

This directory defines a local benchmark for choosing Track 4 architectures. It is not an attempt
to reconstruct the organizer's hidden set. The questions use the same contract and similar public
source classes, while deliberately covering targets and schemas beyond the eleven official practice
units.

## Status

All twenty catalog questions are materialized as forty runnable units: one `explicit` and one
`transformed` schema per economic target. The set contains six classification, eight regression,
and six ranking questions. Every unit has a frozen visible corpus, hidden outcome, declared naive
answer, manifest, provenance, and a zero-model control result. All forty naive answers score at the
neutral 0.5 anchor.

The catalog is evaluation infrastructure. Its historical outcomes may be used to expose routing,
unit-conversion, interval, and schema-dependence failures; they do not prove hidden-set gains and do
not change production behavior by themselves.

## Reproduce the complete catalog

Use the repository's existing Python installation. No virtual environment or model API is required.
The tracked compact snapshots are sufficient for ordinary rebuilds; the SEC raw downloads under
`evaluation/cache/` are git-ignored and needed only to recreate those compact snapshots.

```bash
python3.13 proxy-benchmark/build_sec_proxies.py
python3.13 proxy-benchmark/build_segment_proxy.py
python3.13 proxy-benchmark/build_payroll_proxy.py
python3.13 proxy-benchmark/build_macro_proxies.py
python3.13 proxy-benchmark/build_auction_proxy.py
python3.13 proxy-benchmark/build_energy_proxy.py
python3.13 proxy-benchmark/build_gas_proxy.py
python3.13 proxy-benchmark/build_cot_proxy.py
python3.13 proxy-benchmark/build_fx_proxy.py
python3.13 proxy-benchmark/validate_proxy.py
for n in $(seq -w 1 20); do
  python3.13 proxy-benchmark/run_control.py --experiment "proxy-$n"
done
python3.11 -m pytest -q
```

## Run the unified evaluation suite

`evaluation/benchmark_suite.json` inventories the eleven published compatibility units and all
forty proxy schema cases. The proxy cases are grouped into twenty economic events, so an explicit
and transformed pair shares one unit of weight instead of counting twice. Public outcomes remain
local and git-ignored.

Run and score the current model-free agent on all 51 runnable units with:

```bash
python3 evaluation/run_benchmark_suite.py --name current
```

The command writes answers under the ignored `evaluation/runs/benchmark-suite-current/` tree and
a compact report to `evaluation/reports/benchmark-suite-current.json`. Add `--reuse` to rescore
existing answers without rerunning the agent, or select `--scope public` / `--scope proxy`.

The report macro-averages economic events and includes cohort, target-type, and paired-schema
slices. Its composite excludes the private citation-faithfulness gate and is therefore a local
development diagnostic, not a leaderboard score.

## Run the historical rolling-origin screen

The 51-unit suite measures final-event behavior. A separate evaluation-only screen uses the
project's frozen auction, COT, CPI, EPS, FOMC, macro-revision and post-earnings panels to test
numeric rules at thousands of earlier origins:

```bash
python3 evaluation/experiments/rolling_origin_reference_screen.py
```

For every origin, an outcome enters training only when its recorded resolution date is strictly
earlier than that origin. Whole event groups stay together, and each family is split chronologically
into development, time-forward test and confirmation periods. The report compares simple rules,
the current production prior and a Wang-inspired rolling selector. It is evaluation infrastructure:
passing its leakage checks does not authorize a production change.

Network refreshes are explicit: `build_macro_proxies.py --fetch`,
`build_payroll_proxy.py --fetch`, `build_sec_proxies.py --raw-dir <companyfacts-dir>`, and
`build_segment_proxy.py --raw-dir <filing-dir>`. Existing dedicated builders retain their documented
raw-cache options.

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

Six questions are near-neighbor controls for published families and fourteen deliberately broaden
the family set. Each economic question has two schema variants, yielding forty runnable cases from
twenty historical event definitions.

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

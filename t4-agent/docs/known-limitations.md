# Known limitations

- No authoritative House serving input/context ceiling is published.
- Official Development House access is not yet open; OpenRouter is only an analogue.
- All eleven public units have a proven passing lower bound under the local official two-model NLI
  path, but this does not establish hidden-unit faithfulness. The local CPU/runtime package set is
  not guaranteed byte-identical to production.
- Up to three retrieved context citations are added per entity. They increase answer size and
  scoring work, and NLI passage does not prove that a forecast is substantively correct.
- Existing 11-unit outcomes are retired public practice cases and have influenced development.
- Accepted interval changes lift diagnostic mean coverage to 66.4%, still below the 90% target.
- Rate-curve and post-earnings predictions have zero predictive quality on the public diagnostics.
- The generic hidden-family path now has target-field, numeric-noise, row-order and change-vs-level
  robustness tests, but no broad real-outcome benchmark. Its field selection is lexical and does not
  yet solve arbitrary label semantics for unknown classification targets.
- Retrieval remains lexical BM25 without semantic reranking. Punctuation-normalized tokens fix exact
  identifier misses, but aliases, abbreviations and paraphrases can still rank the wrong chunk.
- Complete-roster and batch-3 direct prediction plus fixed 50/50 hybrids were rejected on public
  development diagnostics. The results do not cover every possible direct prompt or learned blend,
  but further batch-size tuning is not justified without a new independent hypothesis and holdout.
- Public-corpus free inference opts into provider data collection and must never be used for private data.
- The COT mean-reversion coefficient is deliberately simple. It improved a 96-date time-forward test,
  but its mean rank correlation was only 0.0379 and may vary across market regimes.
- The auction model uses only recent same-tenor BTC outcomes. Offering size, bidder composition and
  rate-volatility features were not adopted, so it may miss regime changes despite improving the
  2022-2024 time-forward checks. The 2022-2023 point test was inspected before interval calibration
  was added; the combined candidate therefore relies on the untouched 2024 confirmation period.
  Its concise-summary citation rule helps only when the frozen corpus contains a summary whose
  reported recent-six average can be independently verified from the raw rows.
- Artifact-availability gates cover the four currently fitted family constants. Any future fitted
  artifact still requires its own recorded availability date and early-cutoff fallback; the helper
  cannot infer provenance automatically.

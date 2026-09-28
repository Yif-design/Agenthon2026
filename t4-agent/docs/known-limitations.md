# Known limitations

- No authoritative House serving input/context ceiling is published. Public production-shaped
  prompts currently range from 4,410 to 41,167 characters. The agent does not impose an arbitrary
  fixed character cap; an explicit context-length HTTP 400 falls back for that batch while allowing
  later shorter batches to continue under the existing circuit and request limits.
- Official Development House access is not yet open; OpenRouter is only an analogue.
- All eleven public units have a proven passing lower bound under the local official two-model NLI
  path, but this does not establish hidden-unit faithfulness. The local CPU/runtime package set is
  not guaranteed byte-identical to production.
- Up to three retrieved context citations are added per entity. They increase answer size and
  scoring work, and NLI passage does not prove that a forecast is substantively correct.
- Existing 11-unit outcomes are retired public practice cases and have influenced development.
- Accepted interval changes lift diagnostic mean coverage to 70.9%, still below the 90% target.
- The EPS YoY interval is deliberately broad: mean full width was 8.44 USD/share on the inspected
  2022–2023 test and 6.75 on the locked 2024–2025 confirmation. The official score penalizes only
  coverage error and has no width or sharpness term. The rule is independently confirmed and
  width-minimal within the selected grid, but it should not be interpreted as a tight economic
  confidence bound.
- Rate-curve and post-earnings predictions have zero predictive quality on the public diagnostics.
- The generic hidden-family path now has target-field, numeric-noise, row-order, change-vs-level and
  bounded scalar-feature visibility tests, but no broad real-outcome benchmark. Input reachability
  does not prove prediction accuracy. Schema query terms now decompose common identifier styles,
  but retrieval remains lexical and cannot infer true synonyms or domain meaning. For opaque
  schemas, the fallback reads only the first 512 prompt characters and retains at most 24 lexical
  terms, so a late definition, indirect synonym or boilerplate-looking domain term can still be
  missed. Later fields may be omitted after the 64-field/6,000-character budget. The generic
  label-role mapper handles explicit
  directional rules and common role words, but an ambiguous, indirect or domain-specific label
  definition still falls back deterministically. It cannot correct a wrong direction signal.
- Specialist routing and specialist document-scope dispatch are intentionally conservative. A task
  with an unpublished name can recover a specialist only when its target type and roster-wide field
  set uniquely contain one complete known structural signature whose required values are non-null,
  non-blank and finite. Renamed tasks with changed, partial, mixed or ambiguous fields therefore
  remain on the generic calculator and generic `corpus_ref`
  scope. This avoids applying a domain formula or dropping shared evidence after one incidental
  substring or field, but it can leave specialist accuracy unavailable on a genuinely new schema.
- Retrieval remains lexical BM25 without semantic reranking. Punctuation-normalized tokens fix exact
  identifier misses, schema components cover common identifier styles, and rubric dispatch now
  follows the strict shared router, but aliases, abbreviations and paraphrases can still rank the
  wrong chunk.
- Official category and baseline documents describe per-entity `corpus_ref` subtrees, while the
  published authoring guide describes flat `corpus/<doc_id>.json` files. The agent supports both
  shapes and rejects duplicate IDs, but no public unit exercises a non-root reference, so nested
  scorer resolution remains unverified against a real organizer unit.
- Complete-roster and batch-3 direct prediction plus fixed 50/50 hybrids were rejected on public
  development diagnostics. The results do not cover every possible direct prompt or learned blend,
  but further batch-size tuning is not justified without a new independent hypothesis and holdout.
- Public-corpus free inference opts into provider data collection and must never be used for private data.
- A malformed batch can now fall back while later batches continue, so a partially failing provider
  may consume more attempts than the former eager circuit policy. The 25-call hard cap, four-failure
  circuit and model-phase deadline still bound this behavior. With batch size three, more than 75
  model-required rows necessarily use the deterministic fallback, and retries can lower that number.
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

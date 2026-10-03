# Known limitations

- No authoritative House serving input/context ceiling is published. Public production-shaped
  prompts currently range from 4,410 to 41,167 characters. The agent does not impose an arbitrary
  fixed character cap; an explicit context-length HTTP 400 splits a multi-row batch into single-row
  attempts while allowing later shorter batches to continue under the existing limits. A single-row
  prompt that still exceeds the serving limit uses the deterministic fallback.
- The official runtime guide specifies conditions at the participant Development opening but does
  not itself announce account-specific access. OpenRouter remains only a development analogue.
- Saved two-model NLI reports were produced for the pre-5.2 roster gate. Scorer 5.2.2 instead uses
  deterministic per-claim rules in Development and a claim-level contradiction penalty in Final.
  The current 11 public outputs have zero deterministic false reasons under the pinned 5.2.2 rail,
  with the tokenizer-specific 400-token cap unchecked; this does not prove hidden-unit
  faithfulness.
- Bounded submitted reasons pass the official 5.2.2 schema and local reason rail on all 11 public
  units, and one Gemini Flash-Lite proxy found them grounded and answer-consistent. The official
  reasoning grader runs only in Final against hidden target reasons, so no current leaderboard or
  proxy result proves a positive reasoning bonus. At worst, a valid but unhelpful reason scores
  zero; `T4_ENABLE_SUBMITTED_REASONS=0` omits the field.
- Context-only reason evidence now uses a fixed method-aware lexical selector. It replaced four
  public premises while preserving all 15 computed-input controls and every analysis field, but the
  11 public units influenced its design. A single blind Gemini proxy rejected the broader six-row
  selector; the final version reverted two weak replacements and reranked DOW to a numeric EPS
  table without spending a second call. The selector still cannot prove hidden target-reason
  coverage or causal relevance. `T4_ENABLE_REASON_RELEVANCE=0` restores first-valid selection.
- Up to three retrieved context citations are added per entity. They increase answer size and
  scoring work, and NLI passage does not prove that a forecast is substantively correct.
- Existing 11-unit outcomes are retired public practice cases and have influenced development.
- The C5 descriptor template has been pack-tested only with a synthetic team number and non-secret
  key. The official packer accepted its shape, but this optimization loop does not use the real team
  key or perform a competition upload; account linkage and platform intake remain team-operated.
- The proxy catalog has twenty question designs, but only proxy-15 Treasury auction share and
  proxy-18 COT positioning are runnable, with one 2023 event and two schema variants each. They
  cover regression and ranking and expose transformed-schema failures, but do not yet provide
  classification, development, confirmation or leave-one-family-out evidence.
- The recorded 72.0% practice-set coverage is a legacy diagnostic. Current interval selection must
  minimize mean interval score relative to the unit's naive interval; coverage alone is insufficient.
- The EPS YoY interval is deliberately broad: mean full width was 8.44 USD/share on the inspected
  2022–2023 test and 6.75 on the locked 2024–2025 confirmation. A scorer 5.2.2 rescore found that it
  still beats its narrow predecessor on both periods, but it has not been re-optimized against a
  broader candidate grid under mean interval score.
- The scorer 5.2.2 cross-family rescore found that the accepted CPI 0.75 floor and Treasury-auction
  2.5 standard-deviation multiplier were worse than their immediate predecessors on both forward
  test and confirmation mean interval score. Isolated production validation restored CPI to its
  0.35 floor and the auction multiplier to 1.65. Their point forecasts are unaffected. The auction
  score gain is small, so a broader interval search would need new independent data.
- The bank EPS 100-point minimum half-width was reverted after scorer 5.2.2 made interval width
  explicit. The restored `max(20, 0.75 * abs(point))` rule lowers held-out mean interval score, but
  the development split contains extreme percentage-growth errors around small EPS denominators;
  a new interval rule still needs a robust, predeclared selection hypothesis.
- Rate-curve and post-earnings predictions have zero predictive quality on the public diagnostics.
- The dated-table fallback supports only pipe tables with an exact target or series header and an
  explicit matching unit. It deliberately abstains on synonyms, missing units, derived changes and
  unit conversion. Its historical quality evidence covers bid-to-cover ratios and quarterly diluted
  EPS, while its remote NLI evidence covers two synthetic five-entity units; neither proves hidden
  distribution accuracy.
- The generic hidden-family path now has target-field, numeric-noise, row-order, change-vs-level,
  explicit-unit and bounded scalar-feature visibility tests. A transformed-schema benchmark covers
  five real-outcome datasets across regression and ranking, but it is not a hidden-unit benchmark
  and does not cover generic classification accuracy. Input reachability does not prove prediction
  accuracy. Unit compatibility is enforced only when both identifiers explicitly declare a known
  percent, basis-point or USD unit; equivalent scale encodings such as decimals versus percentages
  remain unresolved. Schema query terms now decompose common identifier styles,
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
  wrong chunk. Recency affects only exact score ties; it assumes a newer cutoff-safe document is
  preferable in that narrow case and treats invalid or missing document dates as least recent.
- Official category and baseline documents describe per-entity `corpus_ref` subtrees, while the
  published authoring guide describes flat `corpus/<doc_id>.json` files. The agent supports both
  shapes and rejects duplicate IDs, but no public unit exercises a non-root reference, so nested
  scorer resolution remains unverified against a real organizer unit.
- Complete-roster and batch-3 direct prediction plus fixed 50/50 hybrids were rejected on public
  development diagnostics. The results do not cover every possible direct prompt or learned blend,
  but further batch-size tuning is not justified without a new independent hypothesis and holdout.
- Public-corpus free inference opts into provider data collection and must never be used for private data.
- A malformed batch can now fall back while later batches continue. An explicit context-limit error
  on a multi-row batch can consume up to one failed batch attempt plus one attempt per row. The
  25-call hard cap, four-failure circuit and model-phase deadline still bound this behavior, so
  single-row recovery runs only after normal batches and may receive no remaining slot on a large
  roster. Batch width increases only when needed, from three to at most six, so a clean route can
  cover at most 150 model-required rows. Larger rosters still require deterministic fallback. Larger
  batches also carry more evidence and may encounter the unpublished House context ceiling; the
  bounded context-split recovery remains active. Evidence for widths above three currently consists
  of deterministic fault injection, one four-row free remote-model A/B and a synthetic 78-row
  official NLI run; it does not establish hidden-task predictive accuracy.
- The COT mean-reversion coefficient is deliberately simple. It improved a 96-date time-forward test,
  but its mean rank correlation was only 0.0379 and may vary across market regimes.
- The CPI twelve-month mean is confirmed only for core and food on 42 complete-history rows in
  2024-2025. It does not cover headline, energy or the other components, and it deliberately falls
  back when fewer than twelve monthly changes are available. The 2025 shutdown left October
  unpublished and the December 2025 core/food histories incomplete for this rule.
- The auction model uses only recent same-tenor BTC outcomes. Offering size, bidder composition and
  rate-volatility features were not adopted, so it may miss regime changes despite improving the
  2022-2024 time-forward checks. The 2022-2023 point test was inspected before interval calibration
  was added; the combined candidate therefore relies on the untouched 2024 confirmation period.
  Its concise-summary citation rule helps only when the frozen corpus contains a summary whose
  reported recent-six average can be independently verified from the raw rows.
- Artifact-availability gates cover the four currently fitted family constants. Any future fitted
  artifact still requires its own recorded availability date and early-cutoff fallback; the helper
  cannot infer provenance automatically.

# Track 4 local numerical artifact provenance

This image contains deterministic code and fixed non-neural parameters. It does not contain an
additional language model, adapter, evaluation outcomes, or the datasets listed below. Evaluation
time citations still come only from the supplied frozen corpus.

## Treasury auction bid-to-cover

- Runtime artifact: six-observation same-tenor mean and `2.5 * population standard deviation`
  interval half-width, with a `0.15` floor.
- Availability gate: used only for task cutoffs on or after `2022-01-01`; earlier tasks retain the
  preceding heuristic.
- Selection data: U.S. Treasury Fiscal Data Auctions Query, development period 2020-2021. The
  underlying history starts in 2010.
- Selection target: official `bid_to_cover_ratio` for nominal 2-, 3-, 5-, 7-, 10-, 20- and 30-year
  coupon auctions.
- Validation only: 2022-2023 test and 2024-01 through 2024-10-31 confirmation; these periods did
  not fit the stored window or multiplier.
- Tracked disclosure: `evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json` and
  `evaluation/reports/auction-model-comparison-v1.json` in the source repository.

## Other fixed family parameters

- CFTC positioning: `-0.2 * current net percent of open interest`, 11.3-point half-width. Selected
  with CFTC public-reporting data through 2021 and used by the current 2024 public family.
- CPI component interval: maximum of `1.65 *` recent population standard deviation and a 0.75-point
  floor. Selected with ALFRED real-time vintages through 2021 and tested on 2022-2023.
- Post-earnings reaction interval: 8.3 percentage-point half-width. Selected with 2018-2021
  announcement/price data and tested on 2022-2023.

Full sources, immutable hashes, splits, rejected candidates and known limitations are recorded in
`docs/dataset-provenance.md`, `docs/research-log.md`, `evaluation/accepted_changes.jsonl` and the
tracked evaluation reports. Those research files are excluded from the runtime image.

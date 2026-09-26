# Dataset provenance

## Retired public practice outcome reconstruction

- Local file: `evaluation/realized/public_all_realized.json` (git-ignored)
- SHA-256: `0cd90a6caec80c6edf21cb4ff461baaa8588e9940c21bd1dffef69aa093fe5bf`
- Created: 2026-09-17
- Coverage: 11 retired public practice units, 78 entities
- Status: independently reconstructed from post-resolution primary sources; not an organizer key
- Use: diagnostic baseline comparison only
- Leakage control: these outcomes are never copied into the runtime image; `evaluation/` is excluded
  by `.dockerignore`

The source file records Apple, SEC, TreasuryDirect, CFTC, BLS, FRED/ALFRED and issuer primary URLs.
Because the same public cases have already informed development, they are not an independent final
test set. New family artifacts require earlier train/dev histories and a time-forward holdout.

## FOMC interval calibration dataset

- Primary source: U.S. Department of the Treasury daily Treasury par-yield curve CSV files
- Source pattern: `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?...`
- Stored period: 2000–2021, one source file per year
- Tenors used: 2, 3, 5, 7, 10 and 30 years
- Target: absolute yield change over the next 35 available trading observations
- Sampling: every fifth valid origin to reduce overlap
- Training split: 2000–2016
- Development split: 2017–2021
- Retired-public holdout: 2022-07-28 and 2024-09-18 units, read only after locking the artifact

The interval candidate was rejected on the one-time holdout check. The raw primary-source data and
reproducible experiment remain tracked so the failed result is auditable and is not repeated.

## FOMC inter-meeting event dataset

- Local file: `evaluation/datasets/fomc/events_2000_2021.json`
- SHA-256: `dc15b069e70a2ae8221055a1d62ba0a40f653dbf4d461a6a296e497e5e5b148b`
- Sources: Federal Reserve historical policy statements and the Treasury CSVs above
- Construction: first complete Treasury close after a statement through the last complete close
  before the next statement
- Coverage: 152 events and six maturities, 2000–2021
- Policy signal: sign of the parsed target-rate midpoint change; 111 hold, 26 ease and 15 tighten
- Missing statement targets: four liquidity/market-operation statements without a target decision
- Structural gap: most 2003–2005 events lack a complete 30-year tenor because 30-year issuance was
  suspended; incomplete six-tenor events are skipped
- Model split: train through 2015, development 2016–2018, one-time test 2019–2021

Each event stores its Federal Reserve URL and a SHA-256 of the visible statement text. Downloaded
HTML is a git-ignored reproducibility cache and is never included in the submission image.

## Post-earnings reaction calibration panel

- Announcement source: Quant500 S&P 500 earnings announcements CSV
  (<https://quant500.com/api/descarga/anuncios.csv>), CC0 1.0
- Price source: Yahoo Finance chart endpoint for adjusted daily closes
- Full-source SHA-256 at access: recorded inside each derived dataset
- Small validation set: AAPL, AMZN and META, 72 events from 2018–2023
- Main panel: deterministic alphabetical first 100 tickers among companies with 23–25 unique,
  reliable after-close rows in 2018–2023
- Main output: 2,092 events from 88 price-resolvable tickers
- Main dataset SHA-256: `d4cb45d4d9af39f07731b84ce7cec9b66accbe8e80c79459958686c4acb7f32d`
- Split: train 2018–2020, development 2021, one-time test 2022–2023
- Target: adjusted-close company return from announcement close to next session close, minus SPY over
  the same dates; labels use the task's +/-1 percentage-point thresholds

Twelve selected historical/current symbols failed Yahoo resolution and remain in the dataset metadata
with their HTTP errors. Selection happened before price download and never inspected returns. Raw CSV
and Yahoo responses are git-ignored cache files; derived events retain the SEC accession and source URL.

## CFTC legacy futures-only positioning panel

- Local file: `evaluation/datasets/cot/legacy10_2015_2023.json`
- Dataset SHA-256: `a0edbd3ce9c7851b2251d0d29245e284d903d2341e2c8510a383d207729ab10e`
- Primary source: CFTC Public Reporting Socrata resource `6dca-aqww`
  (<https://publicreporting.cftc.gov/resource/6dca-aqww.json>)
- Raw cache SHA-256: `dfa3770a1415d5a9f5d6c47e2f3f1c6cac1b3602a435500a0bb7a3b1aa5e62d3`
- Coverage: ten task-aligned legacy futures-only contracts, 4,690 weekly rows from 2015–2023
- Aligned sample: 445 common-date groups with a 28-day trailing window and 35-day target window
- Target: change in noncommercial net contracts from origin to five weeks later, divided by origin
  open interest and multiplied by 100
- Split: 298 training groups through 2020, 51 development groups in 2021, and a one-time 96-group
  test covering 2022–2023
- Leakage control: the model and interval were selected on development before inspecting test; the
  retired 2024 public outcome was used only for the final diagnostic comparison

The raw CFTC response is a git-ignored reproducibility cache. The tracked derived panel contains the
source contract codes and no post-origin feature values other than the explicitly labeled target.

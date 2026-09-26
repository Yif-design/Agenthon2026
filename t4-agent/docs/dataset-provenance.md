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

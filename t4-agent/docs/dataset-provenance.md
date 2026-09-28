# Dataset provenance

## Generic explicit-unit transformed-schema benchmark

`evaluation/reports/generic-unit-compatibility-v1.json` combines five previously recorded official
or first-party historical panels: BLS/FRED ALFRED CPI vintages, CFTC legacy COT, U.S. Treasury
auctions, ALFRED macro revisions and Federal Reserve/Treasury FOMC yield events. The report pins the
SHA-256 of every source dataset and reuses their existing cutoff-safe time splits. It changes only
the feature and target identifiers presented to the generic selector; numeric features and realized
outcomes are unchanged. The transformed cases test unknown-schema behavior and must not be described
as hidden competition units.

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

## Quarterly diluted-EPS year-over-year panel

- Local file: `evaluation/datasets/eps_yoy/quarterly_diluted_eps_2015_2025.json`
- Dataset SHA-256: `d192f63d6008677a4cf69f2d4af0b5eae27125a256629e02849e0b9f223fa307`
- Primary source: SEC EDGAR Company Concept API, standard
  `us-gaap:EarningsPerShareDiluted` facts
- Source documentation: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- Universe: all 88 ticker-resolvable companies in the pre-existing post-earnings panel
- Coverage: 2,321 comparable same-company year-over-year quarter pairs with target periods from
  2015–2025
- Split: 980 train rows in 2015–2019, 440 development rows in 2020–2021, and a one-time
  444-row test in 2022–2023; 457 confirmation rows in 2024–2025
- Runtime availability: the selected interval constants are enabled only for task cutoffs on or
  after 2022-01-01

The builder accepts only 10-Q facts with 60–120 day contexts, keeps the earliest filed version of
each reporting period, pairs periods 330–400 days apart, and requires the prior filing to predate
the target quarter. It also requires the target filing's comparative prior-quarter EPS to match the
original prior filing within the larger of $0.01 or 1%. This removes 139 split/recast basis changes
and six rows without a comparator instead of treating unit changes as forecast errors. It excludes
`abs(prior EPS) < 0.05`, where a relative-width rule is unstable; this filter uses only the
already-public feature. Every retained row stores the comparator, tolerance, both filing dates,
accessions and SEC endpoint. Raw SEC responses are a git-ignored cache. Rebuilding from that cache
produced the tracked dataset byte-for-byte.

Interval selection used the current no-positive-signal fallback point so calibration does not assume
that the text model gets direction right. Among a fixed grid, development selected half-width
`max(2.75 USD/share, 1.15 * abs(prior EPS))`. The official score has no interval-width term, but the
selection still minimizes mean width after matching 90% development coverage. The 2022–2023 test
was read after selection but before the comparability audit was added, so it is not claimed as a
pristine holdout. Extraction and candidate were then locked before the one-time 2024–2025
confirmation read.

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

## CPI component real-time vintage panel

- Local file: `evaluation/datasets/cpi/components_2015_2023.json`
- Dataset SHA-256: `2a4f72da454d964a322bd359a9f4c12aa8112277bbc6071e4ef59aa2ca2f0f40`
- Primary source: ALFRED archival CSV (<https://alfred.stlouisfed.org/graph/alfredgraph.csv>), using
  the eleven BLS/FRED series IDs from the public task
- Raw used-cache SHA-256: `bcb2e25310d63f130df1c238085eb4f001f7f873ca200afe2ed0535638a644d3`
- Coverage: 1,188 rows, eleven components by 108 reference months from 2015-01 through 2023-12
- Feature snapshot: month-end vintage before the target release, with twelve known monthly changes
- Target snapshot: next month-end vintage after the target release and before the following release
- Split: 792 training rows in 2015–2020, 132 development rows in 2021, and a one-time 264-row test
  in 2022–2023
- Validation: all eleven 2023-12 targets round to the values in the archived BLS release Table A

For the 25 used-car snapshots from 2022-01 through 2024-01, the builder deterministically uses the
same-month day-20 vintage. Official BLS archive URLs show every 2022 and 2023 release occurred by day
14, and the December 2023 release occurred on 2024-01-11, so no CPI release falls between day 20 and
month-end. Each substitution is listed in the dataset metadata. Raw CSVs are git-ignored and the
submission image excludes the entire evaluation directory.

### CPI core and food 2024-2025 confirmation

- Local file: `evaluation/datasets/cpi/components_2024_2025_confirmation.json`
- Dataset SHA-256: `794cdfbc72ff46a0db76cf7f470e85f9b3b76da898e18ab7bc80084cc8380cdb`
- Raw used-cache SHA-256: `1541c671dcaf03bf5ca1baeeb5a143cbf0e4adf8e206d543d965ff4d5d904a2b`
- Source and vintage construction: the same ALFRED endpoint, series roster and cutoff-safe
  month-end snapshots as the 2015-2023 panel
- Coverage: 245 component rows from reference months 2024-01 through 2025-12
- Locked decision subset: 24 core/food rows in 2024 and 18 in 2025 with exactly twelve known
  monthly changes
- Missing-history policy: 2025-12 core and food are excluded because the canceled October 2025 CPI
  release leaves only ten calculable prior monthly changes
- Runtime availability: the confirmed twelve-month mean is enabled only for task cutoffs on or
  after `2026-02-01`

The candidate was fixed from the Cleveland Fed Inflation Nowcasting FAQ's twelve-month moving
average specification for core and food CPI before reading this confirmation. It was accepted only
if MAE and RMSE improved and direction accuracy did not decline in 2024 and 2025 separately.
Rebuilding the parameterized builder over its original 2015-2023 range reproduced all 1,188 rows
and the raw-cache hash exactly.

## U.S. Treasury nominal coupon auction panel

- Local file: `evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json`
- Dataset SHA-256: `1dd97882feb1a754fa4ade81f06d77bca871d3c5dae2f8e2922dec8628bfbb1a`
- Canonical source-payload SHA-256: `e9208637c7edefb0db257d41df29ab10108f165163830ddac226f328efaec9b0`
- Raw cache-file SHA-256: `7f1d7e213234636d1d4b5be4ea4bf287a1b4ac6e09d64e30b0ad164dc08c2b9b`
- Primary source: U.S. Treasury Fiscal Data Auctions Query
  (<https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query>)
- Coverage: 1,124 nominal fixed-rate coupon auctions from 2010-01-01 through 2024-10-31
- Tenors: 2-, 3-, 5-, 7-, 10-, 20- and 30-year, using `original_security_term` so reopenings remain
  in their original tenor group
- Outcome: Treasury's official `bid_to_cover_ratio`
- Forecast features: only earlier same-tenor outcomes and the current auction's pre-auction
  new/reopening status; result fields for the target auction are outcomes only
- Split: 685 training samples through 2019, 159 development samples in 2020-2021, 168 test samples
  in 2022-2023 and 70 confirmation samples from 2024-01 through 2024-10-31
- Runtime availability: the selected constants are enabled only for task cutoffs on or after
  2022-01-01

The builder excludes floating-rate and inflation-indexed securities. It retains the authoritative
reported BTC rather than requiring equality with `total_tendered / total_accepted`: those totals
include category and add-on semantics that make the naive ratio differ from the published measure.
Rebuilding from the git-ignored raw API cache produced the tracked dataset byte-for-byte.

## Recent FOMC inter-meeting Treasury panel

- Local file: `evaluation/datasets/fomc/events_2022_2026.json`
- Dataset SHA-256: `d51d0b231c0df5312dae367e802aa445b06f921d13ba9e0a03e1b710162b4580`
- Primary sources: Federal Reserve annual FOMC release indexes and policy-actions table, plus U.S.
  Treasury daily par-yield CSVs
- Coverage: 37 completed inter-meeting events from 2022-01-26 through 2026-07-29, with six
  maturities per event
- Features available at the forecast origin: first complete post-decision Treasury close, signed
  target-rate change and direction
- Outcome: yield change from that origin close to the final Treasury close before the next FOMC
  decision
- Leakage control: the two retired public events (2022-07-27 and 2024-09-18) are excluded from
  interval selection and confirmation; 2022-2025 selects the candidate and five completed 2026
  events form the one-time confirmation set

The builder records SHA-256 values for every tracked annual Treasury CSV. Federal Reserve policy
action dates are effective dates, so the builder maps them to the preceding decision date; meetings
absent from the actions table are holds. The dataset and experiment are research artifacts and are
excluded from the submission image.

## ALFRED monthly macro-revision panel

- Local file: `evaluation/datasets/macro_revision/alfred_monthend_2014_2024.json`
- Dataset SHA-256: `1dfd5172b99834966a4410b36fcaf4eb26ee9354dcd85a1d82ecc60cec8ceb6c`
- Primary source: ALFRED archival CSV
  (<https://alfred.stlouisfed.org/graph/alfredgraph.csv>)
- Series: `DGORDER`, `HOUST`, `INDPRO`, `PAYEMS`, `PI`, and `RSAFS`
- Coverage: 2,450 non-zero next-snapshot revisions from requested month-end vintages spanning
  2014 through 2024; experiment splits use 2015–2023 only
- Feature boundary: each row contains only revision transitions strictly earlier than its cutoff,
  limited to the preceding eight monthly snapshots and recent reference months
- Outcome: the change in the same reference month's value between the cutoff month-end ALFRED
  snapshot and the next month-end snapshot
- Split: 2015–2019 train, 2020 development, 2021–2022 test, and 2023 one-time confirmation
- Raw-cache SHA-256: `73b489ad737c911616fbb181a4623a2a5e5eb5dcb3900bf8006d1d0718707b62`

The month-end construction can combine multiple releases within a calendar month, so this panel is
an offline model-selection proxy rather than an exact reconstruction of every agency release. The
raw 792 ALFRED CSV snapshots remain in a git-ignored cache; the tracked derived rows and builder
record the requested range, actual response-header digest, and leakage boundary.

## Post-earnings 2024–2025 confirmation panel

- Local file: `evaluation/datasets/postearn/panel88_confirmation_2024_2025.json`
- Dataset SHA-256: `7fa1418262baa7daae49166b1ff0d1b91fe720d647f336ac89697eaf86250d44`
- Fixed universe: the 88 price-resolvable tickers selected by the earlier 2018–2023 panel before
  confirmation outcomes were inspected
- Announcement source: Quant500 S&P 500 earnings announcements CSV, CC0 1.0
- Price source: Yahoo Finance adjusted-close chart endpoint
- Coverage: 696 reliable after-close events, with 353 in 2024 and 343 in 2025
- Raw price-cache SHA-256: `b2af3b327ee2a820c2e492b68255d44aa64a746b53c7d5477c6b843e152e2aec`
- Historical-universe SHA-256: `d4cb45d4d9af39f07731b84ce7cec9b66accbe8e80c79459958686c4acb7f32d`
- Target: next-session company adjusted-close return minus SPY return, with +/-1 percentage-point
  labels identical to the public task

Twelve symbols in the fixed universe could not be resolved by the price endpoint and are explicitly
listed in the dataset metadata. The universe and candidate were selected from 2018–2023 before the
2024–2025 result was generated. Raw responses remain in the git-ignored cache.

## Post-earnings 2026 YTD confirmation panel

- Local file: `evaluation/datasets/postearn/panel88_confirmation_2026_ytd.json`
- Dataset SHA-256: `325910df8af5f307f12495ce7e43b2b1acd05d2b0c419883111511a1f15fb1a1`
- Fixed universe: the same 88 tickers selected before the 2024–2026 outcomes were inspected
- Coverage: 261 reliable after-close events from 2026-01-01 through 2026-09-24
- History used by the locked candidate: only the 2018–2023 panel
- Raw price-cache SHA-256: `c1c07faaf63d3427f286c062f160eb8631a6a2e331cfeadde99e34e2251d18c2`
- Historical-universe SHA-256: `d4cb45d4d9af39f07731b84ce7cec9b66accbe8e80c79459958686c4acb7f32d`

Ten fixed-universe symbols could not be resolved and are recorded in metadata. This panel was built
after locking `ticker_recent4`; it was not used to change the method or its threshold.

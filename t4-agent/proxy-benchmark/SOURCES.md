# Source registry

The catalog refers to source IDs below. A generator must record the exact endpoint, series or filing,
retrieval date, release timestamp and content hash. This registry is not blanket permission to
redistribute every response: licenses and terms must be checked at dataset or series level.

| ID | Publisher | Intended material | License / redistribution note |
|---|---|---|---|
| `sec-edgar` | US SEC EDGAR | 10-K, 10-Q, 8-K, XBRL company facts and filing text | Public records; retain accession, filing date and source URL. Verify redistribution terms for filer-authored text. |
| `bls-release` | US Bureau of Labor Statistics | CPI, payroll, unemployment and release tables | US-government source; record vintage release time and later revisions separately. |
| `bea-release` | US Bureau of Economic Analysis | GDP, PCE and revision releases | US-government source; preserve release vintage and table identity. |
| `fred-alfred` | Federal Reserve Bank of St. Louis | Historical vintages and daily/monthly series | Verify each underlying series' notes and rights; use ALFRED vintage dates where revisions matter. |
| `treasury-auction` | US Treasury | Auction announcements and results | US-government source; preserve security term, auction date and result publication time. |
| `treasury-fiscaldata` | US Treasury Fiscal Data | Debt and related public tables | US-government source; preserve dataset version and update time. |
| `eia-release` | US Energy Information Administration | Weekly petroleum and natural-gas reports | US-government source; preserve report publication time and units. |
| `cftc-cot` | US Commodity Futures Trading Commission | Commitments of Traders reports | US-government source; distinguish as-of date from publication date. |
| `federal-reserve` | Federal Reserve Board | FOMC statements, minutes and policy releases | US-government source; preserve publication timestamp. |
| `dol-claims` | US Department of Labor | Weekly unemployment-insurance claims releases | US-government source; preserve initial release and revisions. |

## Materialized source snapshots

`sources/proxy-10-payroll-2023.json` records cutoff and first-print ALFRED vintages for total
nonfarm payrolls and ten major-industry aggregates around the August 2023 Employment Situation.
The cutoff vintage ends in July; August appears only in the resolution fields used to construct
the hidden labels. Every downloaded CSV has its own content hash. The snapshot is 18,864 bytes and
its SHA-256 is
`f889d3f964693e8b838b2a6313c725cfef7a78a0dc143dbdea7c21977976b70a`.

`sources/proxy-18-cot-2023.json` is a redistributable CFTC legacy futures-only snapshot for ten
markets. It contains 26 weeks of cutoff-safe history plus the single next-report row kept solely to
construct the hidden local outcome. The generator never copies that resolution row into
`task.json` or `corpus/`. Its SHA-256 is
`9428ac2f750afa7f8b7395691e1fb29f57d366dd23abd84e43a88d3fdf8c94db`; the parent raw response
SHA-256 is `dfa3770a1415d5a9f5d6c47e2f3f1c6cac1b3602a435500a0bb7a3b1aa5e62d3`.

`sources/proxy-15-auctions-2023.json` is a redistributable U.S. Treasury Fiscal Data snapshot for
3-, 10-, and 30-year nominal coupon auctions. It contains same-term history through the
2023-08-02 announcement cutoff and the three subsequently published auction results kept solely to
construct hidden local outcomes. Its SHA-256 is
`0c7e7cc0819e1dc77726d45b79a5353962f5ab2d7d1509f8d10ba9427564846d`; the parent raw response
SHA-256 is `7f1d7e213234636d1d4b5be4ea4bf287a1b4ac6e09d64e30b0ad164dc08c2b9b`.

`sources/proxy-16-eia-crude-2026.json` is a redistributable snapshot derived from 57 dated EIA
Weekly Petroleum Status Report `table4.csv` archives. It covers 52 consecutive first-release weeks
through the 2026-09-23 cutoff, four additional same-ISO-week seasonal observations from 2021-2024,
and the 2026-09-30 resolution release. Each archived URL, release date, byte count and SHA-256 is
stored in the snapshot. The six series are U.S. commercial crude excluding SPR and PADD 1-5; the
snapshot SHA-256 is `16a1c0e4cd11f6a2177ca715fb9655fbc69297536e71578f80b3b20d466041ad`.

`sources/proxy-17-eia-gas-2026.json` combines the EIA natural-gas history, revisions workbook and
the 2026-10-01 release payload for six regions. The visible side contains 52 recent weeks and five
same-ISO-week seasonal observations per region; the target week is retained only for the hidden
outcome. The release reports no target/prior revision or reclassification flags. Its SHA-256 is
`61e33e904b3e92b3938365ad8cdc7b94d0ec0bf8e4696abc9f0530a3e63b06b2`.

`sources/proxy-19-fx-2023.json` freezes ten Federal Reserve Board H.10 bilateral USD exchange-rate
series downloaded through FRED. It retains cutoff-safe history through 2023-09-29 and the next 20
common observations through 2023-10-30 solely to construct hidden realized-volatility outcomes.
Every source CSV has an individual content hash. The 184,730-byte snapshot SHA-256 is
`5175c90917ef826f4ee1eb11bc56cf98a45b8bf3be06f489c22ed4c3743ee163`.

## Data boundary

External public data may be used to construct historical proxy tasks and offline artifacts only
under the official training policy. At evaluation time the agent may read only the generated task
and frozen corpus. Any fitted artifact intended for the submission image needs a separate provenance
record and an availability gate proving its fitting, selection and calibration labels were public
before the cutoff of every task where the artifact is enabled.

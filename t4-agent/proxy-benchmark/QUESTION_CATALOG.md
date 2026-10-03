# Question catalog

The machine-readable definitions are in `question_catalog.json`. This table is the review index.

| ID | Target | Relationship | Question | Main sources | Primary stress |
|---|---|---|---|---|---|
| 01 | Classification | Control | Quarterly revenue surprise band | SEC | Estimate versus guidance and fiscal period |
| 02 | Regression | Novel | Gross-margin change in basis points | SEC | Derived arithmetic and units |
| 03 | Regression | Novel | Forward free-cash-flow margin | SEC | Multi-table arithmetic and YTD conversion |
| 04 | Regression | Novel | Capital-expenditure intensity | SEC | Numerator/denominator and guidance ranges |
| 05 | Classification | Novel | Next regular-dividend action | SEC | Regular versus special dividends |
| 06 | Classification | Novel | Diluted share-count direction | SEC | Average versus period-end shares |
| 07 | Ranking | Novel | Share-repurchase intensity | SEC | Authorization versus execution |
| 08 | Classification | Novel | Twelve-month liquidity stress | SEC | Boilerplate versus active warnings |
| 09 | Ranking | Novel | Business-segment growth | SEC | Shared documents and segment identity |
| 10 | Classification | Novel | Payroll first-print surprise | BLS, DOL, ALFRED | First print versus revision |
| 11 | Classification | Novel | Weekly initial-claims direction | DOL, ALFRED | Seasonality and release vintages |
| 12 | Regression | Control | PCE component first-print nowcast | BEA, BLS, ALFRED | PCE/CPI mapping |
| 13 | Regression | Control | GDP revision magnitude | BEA, ALFRED | Revision stage and annualization |
| 14 | Ranking | Control | Treasury maturity yield change | FRED, Fed, Treasury | Whole-curve coherence |
| 15 | Regression | Control | Auction indirect-bidder share | Treasury, FRED | Ratio denominator and tenor |
| 16 | Regression | Novel | Weekly crude inventory change | EIA | Level versus change and product distractors |
| 17 | Regression | Novel | Weekly natural-gas storage change | EIA | Regional scope and sign |
| 18 | Ranking | Control | Next-report COT positioning change | CFTC | As-of versus publication date |
| 19 | Ranking | Novel | Forward FX realized volatility | FRED, Fed | Quote convention and nonstationarity |
| 20 | Ranking | Novel | Cross-asset forward-return quintile | FRED, Fed, EIA, CFTC | Relative forecast and regime shifts |

Materialization status: question 18 has a cutoff-safe time-forward event with explicit and
transformed schemas, complete references and a recorded production-control baseline. Questions
01-17 and 19-20 remain specifications.

## Build waves

Wave 1 is selected for source diversity, target-type coverage and practical outcome construction:

- classification: 05, 08, 10;
- regression: 02, 13, 15, 16;
- ranking: 09, 18, 19.

Wave 2 adds the remaining ten after the generators, provenance records and scorer integration have
been proven on Wave 1. A wave is an implementation order only; it is not a development/test split.

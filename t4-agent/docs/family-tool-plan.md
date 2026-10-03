# Track 4 family tool plan

> Historical planning note. The implementation now follows `family-model-contracts-zh.md`; the heavier parameter schemas below are retained only as research context and must not be treated as required runtime inputs.

This note maps each public Track 4 family to a parameter-extraction schema and deterministic tool. The goal is not to hard-code public answers. The goal is to hard-code the calculation contract so the model extracts facts and the workflow computes labels, forecasts, ranks, intervals, and citation-safe answers.

Official scope: public Track 4 families are examples, not a closed set. Hidden families may differ, so every family-specific tool needs a generic fallback.

## Storage Model

Keep four kinds of data separate.

```text
family_specs.py        routing, input whitelists, signals, numeric parameter contracts
calculators/*.py       one deterministic calculator per family
predict.py             shared prompt, grounding, and output orchestration
runs/<unit>/           ignored local traces: retrieved chunks, raw model JSON, params, tool output
```

Runtime corpus evidence is not a persistent knowledge base. It is indexed per unit from `/input/corpus`, with strict `doc_date <= cutoff_date` filtering before the model sees a chunk.

## Common Runtime Contract

Each row should follow this shape:

```text
1. route family
2. hard-scope documents by entity / series / tenor / market
3. retrieve evidence inside that scope
4. extract parameters as EvidenceFacts
5. reject ungrounded facts before calculation
6. run deterministic tool and record used_fact_ids
7. build citations from the facts actually used
8. validate entity scope, spans, calculation and schema
9. build answer.json and an ignored local trace
```

The model should not directly decide final labels when a formula is available. It should extract parameters, roles, and uncertainty.

## 1. EPS Beat Consensus

Public target: `eps_outcome`, classification labels `beat`, `miss`, `inline`.

Problem: predict target-quarter diluted EPS relative to analyst consensus and threshold.

Row inputs:

- `consensus_eps`
- `threshold_pct`
- `beat_condition`, `miss_condition`, `inline_condition`
- company fields

Extract:

```json
{
  "forecast_eps": "number",
  "historical_eps": "number or null",
  "historical_eps_period": "string or null",
  "revenue_guidance": "string or null",
  "margin_guidance": "string or null",
  "expense_tax_share_count_notes": "string or null",
  "evidence": []
}
```

Tool:

```text
beat_threshold = consensus_eps * (1 + threshold_pct)
miss_threshold = consensus_eps * (1 - threshold_pct)
label = beat if forecast_eps > beat_threshold
label = miss if forecast_eps < miss_threshold
else inline
```

Guardrails:

- Do not copy historical EPS, such as prior quarter EPS, into target-quarter `forecast_eps`.
- If extracted EPS is far above consensus and the cited quote is historical, replace with a conservative consensus-near forecast.
- Cite guidance, outlook, margin, revenue, or target-period setup; avoid citing only prior reported EPS as support for the target EPS.

Fallback:

- `forecast_eps = consensus_eps`
- label = `inline`
- interval around consensus using threshold-scaled width.

Useful background:

- Earnings surprise is measured against analyst forecasts or historical seasonal-random-walk expectations.
- Analyst consensus is the average forecast across analysts and commonly anchors beat/miss reactions.

## 2. EPS YoY Direction

Public target: `eps_yoy_direction`, classification labels `up`, `down`.

Problem: predict whether target-quarter diluted EPS is above or below same quarter prior year.

Row inputs:

- `prior_year_q_eps`
- `quarter_reported`
- `prior_year_quarter`
- `expected_report_date`

Extract:

```json
{
  "forecast_eps": "number",
  "prior_year_q_eps": "number",
  "historical_eps_period": "string or null",
  "guidance_or_operating_trend": "string or null",
  "one_time_items": "string or null",
  "evidence": []
}
```

Tool:

```text
label = up if forecast_eps > prior_year_q_eps else down
point_forecast = forecast_eps
```

Guardrails:

- Do not compare target quarter against immediately prior quarter unless the prompt asks for QoQ.
- If `prior_year_q_eps` is near zero or negative, avoid percentage reasoning and use dollar EPS direction.

Fallback:

- If evidence is positive and prior-year EPS is not large, small `up`; otherwise carry forward and choose based on revenue/margin tone.

## 3. EPS Growth Regression, Including Banks

Public target: `eps_yoy_growth_pct`, regression.

Problem: predict YoY EPS growth percentage.

Row inputs:

- `prior_year_q_eps`
- `quarter_reported`
- bank/company metadata

Extract:

```json
{
  "forecast_eps": "number",
  "prior_year_q_eps": "number",
  "nim_trend": "string or null",
  "provision_trend": "string or null",
  "loan_deposit_trend": "string or null",
  "fee_revenue_trend": "string or null",
  "expense_trend": "string or null",
  "evidence": []
}
```

Tool:

```text
eps_yoy_growth_pct = (forecast_eps - prior_year_q_eps) / abs(prior_year_q_eps) * 100
```

Bank-specific parameters:

- net interest income / margin
- provision for credit losses
- loan growth
- deposit cost
- trading/investment banking fees
- expenses and buybacks

Guardrails:

- For banks, EPS is driven by NII/NIM, provisions, fees, expenses, and share count; revenue alone is weak evidence.
- If prior-year EPS is close to zero, cap or widen interval because percentage growth can explode.

Fallback:

- `forecast_eps = prior_year_q_eps`
- growth = `0`
- wide interval.

## 4. Credit Event

Public target: `credit_event_12m`, classification labels `credit_event`, `no_event`.

Problem: predict bankruptcy, default, or rating-based credit event within 12 months.

Row inputs:

- company name
- industry
- CIK when available

Extract:

```json
{
  "liquidity_signal": "healthy|strained|severe|unknown",
  "debt_maturity_signal": "benign|wall_near|unknown",
  "covenant_or_default_language": "none|waiver|breach|default|unknown",
  "going_concern_language": "none|present|unknown",
  "bankruptcy_language": "none|risk|filed_post_cutoff_unavailable|unknown",
  "rating_or_downgrade_signal": "positive|stable|negative|unknown",
  "risk_score": "0..1",
  "evidence": []
}
```

Tool:

```text
risk_score = weighted score from liquidity, maturity wall, covenant/default, going-concern, rating trend
label = credit_event if risk_score >= threshold else no_event
```

Guardrails:

- A risk factor boilerplate is not enough.
- A waiver is not the same as an actual default.
- Going-concern language is strong but should be distinguished from management risk disclosures.

Fallback:

- Use `no_event` unless severe liquidity/default language is present; credit events are sparse.

Useful background:

- Altman Z-score style models use profitability, leverage, liquidity, solvency, and activity ratios to flag distress.
- If structured financial ratios are absent, use text proxies for the same dimensions.

## 5. Post-Earnings Reaction

Public target: `earnings_reaction`, classification labels `positive_reaction`, `negative_reaction`, `flat`.

Problem: predict one-day abnormal return around the earnings release versus benchmark threshold.

Row inputs:

- `benchmark`
- `event_window`
- `flat_threshold_abn_pct`
- pre-earnings price

Extract:

```json
{
  "expected_eps_surprise": "positive|negative|neutral|unknown",
  "expected_revenue_surprise": "positive|negative|neutral|unknown",
  "guidance_tone": "positive|negative|neutral|unknown",
  "valuation_setup": "crowded_positive|depressed|neutral|unknown",
  "risk_to_expectations": "string",
  "abnormal_return_forecast_pct": "number",
  "evidence": []
}
```

Tool:

```text
label = positive_reaction if abnormal_return_forecast_pct > flat_threshold_abn_pct
label = negative_reaction if abnormal_return_forecast_pct < -flat_threshold_abn_pct
else flat
```

Guardrails:

- Forecast market-adjusted reaction, not raw stock return.
- Good earnings can still produce negative reaction if guidance or setup disappoints.
- Cite pre-release expectations/guidance/setup, not post-release price moves.

Fallback:

- `flat`, abnormal return `0`.

Useful background:

- Earnings surprise and post-earnings announcement drift literature focuses on surprise relative to expectations and abnormal returns.

## 6. Rate Curve Cross-Section

Public target: `yield_change_bps_intermeeting`, regression.

Problem: predict yield change in basis points from cutoff close to resolution close for each maturity.

Row inputs:

- `maturity_years`
- `start_yield_pct`
- `series_fred`
- `as_of`

Extract:

```json
{
  "policy_path_signal": "hawkish|dovish|neutral",
  "inflation_signal": "higher|lower|mixed|unknown",
  "labor_growth_signal": "strong|weak|mixed|unknown",
  "term_premium_signal": "up|down|neutral|unknown",
  "maturity_bucket": "front|belly|long",
  "yield_change_bps": "number",
  "evidence": []
}
```

Tool:

```text
front_end_beta > belly_beta > long_end_policy_beta
yield_change_bps = policy_component + inflation_component + growth_component + term_premium_component
```

Guardrails:

- Forecast change in bps, not final yield level.
- Short maturities respond more to policy path; long maturities also to inflation expectations, growth, and term premium.
- Use FOMC and pre-cutoff snapshot evidence only.

Fallback:

- `0 bps`, wider interval for long horizons or volatile contexts.

Useful background:

- Fed policy communications, inflation, labor conditions, and market policy-path repricing are standard drivers of Treasury yields.

## 7. CPI Component Nowcast

Public target: `cpi_component_mom_first_print`, regression.

Problem: forecast seasonally adjusted MoM percent change for named CPI-U component.

Row inputs:

- `latest_published_mom_pct`
- `latest_published_ref_month`
- `ref_month`
- `series_fred`
- component name

Extract:

```json
{
  "latest_mom": "number",
  "component_driver": "string",
  "energy_food_shelter_used_cars_signal": "string or null",
  "forecast_mom_pct": "number",
  "evidence": []
}
```

Tool:

```text
forecast_mom_pct = latest_mom + component_adjustment
```

Guardrails:

- Component-specific evidence matters. Headline CPI evidence alone may not support a component forecast.
- Forecast first print for the reference month, not a later revision.
- Keep units as percent MoM, not index level.

Fallback:

- carry forward `latest_published_mom_pct`.

Useful background:

- CPI nowcasting commonly combines latest inflation data with component drivers and high-frequency indicators.

## 8. Macro Revision Direction

Public target: `next_estimate_revision_direction`, classification labels `up`, `down`.

Problem: predict whether the next estimate for a reference month revises up or down.

Row inputs:

- `latest_precutoff_estimate`
- `latest_precutoff_vintage`
- `ref_month`
- `resolving_release_date`
- `series_name`, `agency`, `units`

Extract:

```json
{
  "latest_estimate": "number",
  "revision_context": "string",
  "related_series_signal": "up|down|mixed|unknown",
  "survey_or_source_data_signal": "up|down|mixed|unknown",
  "revision_direction": "up|down",
  "evidence": []
}
```

Tool:

```text
label = extracted revision_direction
```

Guardrails:

- Predict revision of an old reference month, not new-month activity.
- Agency revision methods matter when evidence mentions benchmarking or source-data updates.

Fallback:

- If no directional evidence, choose toward mean reversion or small agency-specific prior; keep confidence low.

Useful background:

- Census and BEA statistical releases are revised as more complete source data and benchmark corrections arrive.

## 9. Auction Demand

Public target: `bid_to_cover_ratio`, regression.

Problem: forecast Treasury coupon auction bid-to-cover ratio.

Row inputs:

- `tenor`
- `auction_date`
- `new_or_reopening`
- `offering_amount_usd_bn`
- `size_announced_precutoff`

Extract:

```json
{
  "tenor": "string",
  "offering_size": "number",
  "rate_level_signal": "attractive|unattractive|neutral|unknown",
  "recent_auction_demand_signal": "strong|weak|neutral|unknown",
  "supply_pressure_signal": "high|low|neutral|unknown",
  "bid_to_cover_forecast": "number",
  "evidence": []
}
```

Tool:

```text
bid_to_cover = tenor_baseline + demand_adjustment - supply_size_adjustment
```

Guardrails:

- Forecast bid-to-cover ratio, not auction yield or tail.
- Higher bid-to-cover generally means stronger demand.
- Direct/indirect/dealer takedown and tail are related but not identical to bid-to-cover.

Fallback:

- tenor baseline around recent normal, e.g. roughly 2.3-2.7 depending on tenor; use 2.5 generic if no data.

Useful background:

- Bid-to-cover is bids received divided by bids accepted and is a standard Treasury auction demand measure.

## 10. Positioning Shift Ranking

Public target: `net_positioning_change_pct_oi_rank`, ranking.

Problem: rank markets by change in net noncommercial positioning as percent of open interest.

Row inputs:

- `net_noncommercial_20241022`
- `open_interest_20241022`
- `net_pct_oi_20241022`
- `trailing_4wk_net_change_pct_oi`
- `asset_class`

Extract:

```json
{
  "current_net_pct_oi": "number",
  "trailing_change_pct_oi": "number",
  "expected_change_pct_oi": "number",
  "crowding_or_reversal_signal": "string",
  "evidence": []
}
```

Tool:

```text
point_forecast = expected_change_pct_oi
rank = sort rows by point_forecast descending
```

Guardrails:

- The scored value is `point_forecast`, not the integer `rank`.
- Use change as percent of open interest, not raw contracts.
- Ranking must be cross-row; do not let the model assign per-row ranks independently.

Fallback:

- use `trailing_4wk_net_change_pct_oi` as point forecast.

Useful background:

- CFTC COT reports break down Tuesday open interest and week-to-week changes by trader categories. The public row fields already provide key positioning quantities.

## Generic Fallback

Use when no family route matches.

Extract:

```json
{
  "target_units": "string",
  "baseline_value": "number or null",
  "directional_signal": "up|down|positive|negative|neutral|unknown",
  "point_forecast": "number or null",
  "label": "string or null",
  "evidence": []
}
```

Tool:

- Use legal labels only.
- Use numeric `point_forecast` for regression and ranking.
- Use row-provided latest/prior value as fallback baseline.
- Always produce interval and claims.

## Source Notes

- Official public families and schema: `track4-analysis-public/docs/CATEGORIES.md`, `README.md`, and public `units/*/task.json`.
- EPS and earnings surprise methods: analyst consensus, seasonal random walk, SUE, and cross-sectional earnings forecasts.
- Credit distress tools: Altman Z-score family and liquidity/leverage/default textual proxies.
- Rates: policy path, inflation, labor market, and term-premium interpretation of yield moves.
- CPI: nowcasting component inflation from recent CPI and component-specific drivers.
- Macro revisions: agency revisions based on more complete source data and benchmark corrections.
- Auction demand: bid-to-cover ratio as bids received over bids accepted.
- Positioning: CFTC COT report open interest and trader category position changes.

## External Method References

- Earnings surprise and post-earnings reaction: earnings surprise is commonly measured against the latest analyst consensus, and PEAD research studies abnormal returns after earnings surprises. Useful references: ScienceDirect on consensus-based earnings surprise, JSTOR on PEAD, and RePEc PEAD studies.
- Rates: Federal Reserve and SF Fed term-structure work supports decomposing yield moves into policy-rate expectations, inflation/growth expectations, and term premium.
- Credit distress: Altman Z-score style distress models use profitability, leverage, liquidity, solvency, and activity variables. In this competition, when full ratios are missing, extract text proxies for those same dimensions.
- CPI nowcasting: Cleveland Fed inflation nowcasts illustrate the standard idea of combining recent inflation prints with high-frequency inputs such as energy prices.
- Macro revisions: BEA/Census/BLS releases revise estimates as more complete source data, benchmarking, and seasonal-adjustment information arrive.
- Auction demand: bid-to-cover is demand divided by the amount accepted or sold; use it as the direct target and keep yield/tail/takedown as supporting signals. Useful references: U.S. Treasury Fiscal Data and standard auction explanations.
- Positioning: CFTC COT reports include open interest, non-commercial holdings, week-to-week changes, and percent of open interest, matching the public ranking-family fields.

Reference links checked during planning:

- ScienceDirect, "The value of publicly available predicted earnings surprises": https://www.sciencedirect.com/
- JSTOR, "Arbitrage Risk and Post-Earnings-Announcement Drift": https://www.jstor.org/
- Federal Reserve, "Monetary Policy and the Yield Curve": https://www.federalreserve.gov/
- SF Fed, "Treasury Yield Premiums": https://www.frbsf.org/
- Cleveland Fed inflation research and nowcasting materials: https://www.clevelandfed.org/
- BEA annual update and revisions notes: https://www.bea.gov/
- U.S. Treasury Fiscal Data auction results fields: https://fiscaldata.treasury.gov/
- CFTC Commitments of Traders reports: https://www.cftc.gov/

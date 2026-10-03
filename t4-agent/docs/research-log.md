## 2026-10-03: complete 20-question proxy catalog — accepted as evaluation infrastructure

Hypothesis: twenty real-source, cutoff-safe question families with paired explicit/transformed
schemas can run end-to-end without model access or hidden-outcome leakage.

Result: all 20 questions materialize into 40 valid units spanning six classification, eight
regression and six ranking targets. Each pair preserves entity outcomes while changing field names,
units or roster order. All 40 declared naive answers score at the neutral 0.5 anchor; all 20 current
zero-model controls completed and produced separate reports. SEC company facts cover proxy-01–08,
dimensioned filing facts cover proxy-09, and official macro/market sources cover proxy-10–20.

During validation, a ranking edge case was fixed: a perfect declared naive previously mapped to
0.85 composite rather than the required neutral 0.5. Production forecasting logic was unchanged.
The catalog is accepted for architecture and regression testing; one historical event per family
remains insufficient evidence for a forecasting change.

Reports: `evaluation/reports/proxy-01-control-v1.json` through proxy-20's family-specific report.
Model API calls: 0. Local LLM/NLI runs: 0.

Release record: commit `a27b8591ab078a68329ee9a8ece721302a4a052c` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `37120097633` passed tests, the pinned toolkit pack
smoke, Linux/amd64 image build/push, and `analyze --help`. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:66d8e3cc53dfd6ab8e9fdb6c7aeef9d677b9f70b5cd8e34245796445fbacdc57`.
Anonymous manifest and config requests returned HTTP 200; the interface label is 2.0. No formal
competition submission was performed.

# Research log

## 2026-10-03: forward FX volatility proxy-19 benchmark — accepted, robustness hypothesis rejected

Proxy-19 adds a market-price ranking task for ten Federal Reserve H.10 bilateral USD exchange-rate
series. The cutoff is 2023-09-29. Each entity exposes 81 common eligible observations; the hidden
outcome is annualized log-return volatility over the next 20 common observations through
2023-10-30. The declared naive ranks currencies by trailing-20-day realized volatility and uses a
cutoff-only rolling-volatility error band.

The transformed unit reverses the roster, replaces published quotes with reciprocals, renames
fields and stores volatility features as fractions. Reciprocal quotes preserve log-return
volatility, so both units have identical economic outcomes. Every downloaded source CSV has a
recorded SHA-256 and no post-cutoff observation appears in a task or corpus document.

The current agent completed all twenty rows without model access. Explicit composite before claim
penalty was 0.4964; transformed was 0.3691, a 0.1273 decline that fails the preregistered 0.10
schema-stability gate. The transformed ranking remained informative (raw Spearman 0.8424), but its
interval score deteriorated because the generic fallback used the wrong scale. The benchmark is
accepted and production remains unchanged; the failed hypothesis identifies cross-schema interval
normalization as a general weakness.

Report: `evaluation/reports/proxy-19-fx-control-v1.json`.

Release record: commit `b58c14a5be2875ffd85073fba649986fa5c398c5` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `37116828084` passed 164 tests, the pinned toolkit
2.6 packer smoke, the Linux/amd64 build and the container command smoke. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:9bac7fb188c57b7cd78931b64b84536b1b2833fb72ba6fd7f47c000794f8ff64`.
Anonymous manifest and config requests returned HTTP 200; the OCI digest matched, and the interface
label is `2.0`. No formal competition submission was performed.

## 2026-10-03: payroll first-print proxy-10 classification benchmark — accepted

Proxy-10 adds the first runnable pure-label classification question to the expanded benchmark. It
uses eleven BLS payroll series as exposed through two frozen ALFRED vintages: the 2023-08-31 input
vintage ends in July, while the 2023-09-01 vintage supplies the initially published August level
only to the hidden outcome. Each row's reference is the mean of its latest three cutoff-vintage
monthly changes. The symmetric classification band is the larger of 5 thousand jobs and half the
population standard deviation of its latest six changes.

The outcome has three positive, three inline and five negative surprises. The explicit and
transformed units preserve those labels while reversing the roster, renaming the target and fields,
and converting thousands of persons to persons. The card declares `interval_leg = false`, matching
the official 5.2.2 pure-label rule. The local scorer now implements the same label-accuracy anchor:
the always-inline naive has accuracy 3/11 and scores 0.5.

All 35 snapshot and generated-unit files were byte-identical after a second build. The validator
accepted ten units and five pairs with zero errors; both control answers passed toolkit 2.6's
analysis schema. Python 3.11.7 passed 161 tests. The existing agent completed all 22 rows without a
model call but returned inline throughout, so both variants matched the naive at composite 0.5000.
The transformed result did not fall below explicit, accepting the benchmark-infrastructure
hypothesis. This is evidence of schema stability only; it exposes that the current control has no
useful payroll-surprise classification skill. Production logic remains unchanged.

Report: `evaluation/reports/proxy-10-payroll-control-v1.json`.

Release record: commit `848ca08803024a4eb5dfb434e723fb757b449c24` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `37104010339` passed 161 tests, passed the pinned
toolkit 2.6 submission-packer smoke, built Linux/amd64, and passed the container command smoke. The
immutable image is `ghcr.io/yif-design/agenthon2026-t4@sha256:b13c14014481052050ede1e8a6d18d7a49fb3c254a553ad419d690ba437f1681`.
Anonymous manifest and config requests returned HTTP 200; the OCI digest matched, and the config
carries `qfbench2.interface_version=2.0`. No formal competition submission was performed.

## 2026-10-03: natural-gas storage proxy-17 benchmark — accepted

Proxy-17 forecasts the next weekly storage change for the Lower 48 and five EIA regions. Its
snapshot records the official history, revisions workbook and target release, including explicit
no-revision and no-reclassification flags. The visible inputs contain 52 recent weeks and five
same-ISO-week seasonal observations; the target week is confined to the hidden outcome. Explicit
and transformed variants reverse the roster, rename fields and convert billion to million cubic
feet.

The benchmark pair built reproducibly and passed its cutoff, roster and variant checks. The current
agent used generic fallback for all twelve rows. It trailed the declared seasonal naive on both
variants: explicit composite 0.3633 and transformed 0.2179 before claim penalty. This accepts the
new benchmark infrastructure without selecting a production forecasting change and gives the
expanded suite a second independent energy inventory target.

Report: `evaluation/reports/proxy-17-gas-control-v1.json`.

## 2026-10-03: fixed recent-six corpus prior — rejected, production unchanged

The first cross-family prior screen isolated forecasting from target resolution. Evaluation-only
adapters supplied each entity's correctly resolved, cutoff-safe target history; the candidate then
used one fixed rule everywhere: the mean of the latest six observations and a 90% interval of plus
or minus 1.65 population standard deviations over the same window. No target outcome selected the
window, statistic or multiplier, and explicit/transformed variants received identical forecasts by
entity.

Across Proxy-15 and Proxy-16, the mean pre-claim composite increased from 0.3308 to 0.4601. The
Proxy-15 family mean rose from 0.2828 to 0.5000 because the candidate removed the transformed
schema's unrelated-scalar failure. Proxy-16 also improved from 0.3788 to 0.4202, but both energy
cases remained below the preregistered 0.45 per-case floor. The recent-six point MAE was 1.4289
million barrels versus 1.0379 for the declared same-week seasonal naive. The overall and both
family-average gates passed; the per-case quality gate failed, so the fixed prior is rejected and
was not integrated into production.

The result narrows the next hypothesis. A resolved history is materially better than arbitrary
entity scalars, but a universal recent-window mean discards useful calendar structure. Do not tune
the window on these outcomes or add an EIA special case. A future candidate needs a cutoff-only
selection rule across persistence, recent means, trend and seasonal candidates, and more than one
seasonal event before production adoption.

The report was byte-identical across two runs (`22fe67c415937a5ecffa6bf88811b7412af005803f54ac59d1274a5de98cf671`).
All four candidate answers passed the official toolkit 2.6 analysis schema. Python 3.11.7 passed
156 tests, and the proxy validator accepted six units and three schema pairs with zero errors. No
model API or NLI ran.

Official Track 4 main remains `1c744e1d6725340643a533f436517d72b53ca0e1`, shared main remains
`bd01548e34d21fd660d88fd06157078fb25ece4e`, and toolkit v2.6.0/scorer 5.2.2 are unchanged. Open
issues 18-20 still concern deployed-run diagnostics and scoring-version clarification, with no new
published rule that changes this screen. The public `wangzgui/agenthon-t4-baseline-2026` repository
also remains at `a32950da279905956269c1a60a9141988849e99d`; no competitor code was copied.

Report: `evaluation/reports/corpus-recent6-prior-screen-v1.json`.

## 2026-10-03: EIA crude-inventory proxy-16 confirmation benchmark — accepted

The benchmark previously had only one regression family, so the rejected Proxy-15 semantic matcher
could not distinguish a general target/prior weakness from a Treasury-specific result. Proxy-16 now
forecasts the next first-release weekly commercial crude-stock change for the U.S. total and PADD
1-5 at the 2026-09-23 cutoff. It provides explicit and transformed schemas, hidden outcomes, a
five-year same-ISO-week seasonal naive, and one corpus document per entity.

The source was tightened during the round. Current EIA history pages were initially sufficient to
reconstruct the event, but they are not proof of the value visible at every earlier cutoff. The
accepted snapshot instead uses 57 dated official `table4.csv` archives: 52 consecutive visible
weeks, four extra 2021-2024 seasonal weeks, and the target release. EIA's published `Difference`
field preserves the unrounded weekly change and avoids 0.001 million-barrel errors from subtracting
displayed levels. Every archive URL, release date, size and SHA-256 is retained.

All 25 generated snapshot/unit files were byte-identical after a second build. The benchmark
validator accepted six units and three variant pairs with zero errors; both Proxy-16 answers passed
the official toolkit 2.6 analysis schema. The declared naive answer scores exactly 0.5 on predictive
and interval quality. Python 3.11.7 passed 156 tests. No local or remote model ran.

The production control completed all twelve schema rows with zero model calls, but trailed the
seasonal naive: explicit composite before claim penalty was 0.3562 (MAE 1.6753) and transformed was
0.4015 (MAE 1.4857), versus naive MAE 1.0379. Both used generic fallback, and their different
outputs expose schema dependence. The benchmark infrastructure is accepted; production forecasting
logic is unchanged. Proxy-16 supplies the second regression domain needed for a separately
preregistered comparison of persistence, recent mean, trend and seasonal priors.

Official Track 4 main remains `1c744e1d6725340643a533f436517d72b53ca0e1`, shared main remains
`bd01548e34d21fd660d88fd06157078fb25ece4e`, toolkit `v2.6.0` resolves to
`683e70c9c44eca947699a72bea79147a5d4d8c7a`, and scorer 5.2.2 is unchanged. The public
`wangzgui/agenthon-t4-baseline-2026` repository advanced to `a32950d`; its own active-baseline file
still names S1.6 with reported Development score 0.4793, while S1.9 remains an unpromoted candidate
after a failed submission and a reproduced malformed-House-field crash. Its conservative typed
review admission and batch exception isolation support our existing fail-closed direction, but do
not justify copying a candidate without held-out evidence.

Report: `evaluation/reports/proxy-16-energy-control-v1.json`.

Release record for the accepted benchmark infrastructure: commit
`2534a9cbde1b061cb9e5a146af22c74b0aa0dab2` was pushed to `codex/t4-agent-skeleton`. GitHub Actions
run `37096947579` passed 156 tests on Python 3.13.15, passed the pinned toolkit 2.6 submission-packer
smoke, built and pushed Linux/amd64, and passed `analyze --help`. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:ec09dd73a7f31bcd3ca5cb415c4daf67a8d34719578ff4bf119652799d6212e1`.
Anonymous manifest and config requests returned HTTP 200; the OCI digest matched exactly and the
config carries `qfbench2.interface_version=2.0`. The development submission template now points to
that digest. No formal competition submission was performed.

## 2026-10-03: target-semantic dated-table alias — rejected and rolled back

Proxy-15 showed that an unknown regression target renamed from indirect-bidder share to
`remote_allotment_fraction_pct` fell through to an unrelated entity scalar. A deterministic
candidate compiled the target name, definition and unit into normalized tokens. Exact table-column
matches remained first; an alias was accepted only when its unit matched, it had at least three
semantic overlaps including one distinctive token, and the best score was unique. The candidate
contained no auction field names and made no model call.

The focused safety suite passed 52 tests. On the transformed Proxy-15 unit the selected method
changed from `generic_baseline` to `generic_dated_table_baseline`, MAE fell from 131.8565 to 16.8629,
and composite before claim penalty rose from 0.0655 to 0.2911. This proves the target contract found
the intended percentage series and eliminated the 36/120/360 tenor-month forecasts.

The result still failed the preregistered adoption rule: transformed composite had to reach 0.45
and finish within 0.05 of the explicit unit's 0.5000, but remained 0.2089 behind. The generic table
calculator persisted the latest observation, while the stronger control used a recent-window mean.
Because the first score gate failed, Proxy-18, the public 11-unit byte comparison and the full suite
were not run. Production code and candidate tests were rolled back. A future round must evaluate
the table statistic across more than one proxy family before combining it with semantic matching.

Report: `evaluation/reports/target-semantic-table-alias-proxy15-v1.json`.

## 2026-10-03: toolkit 2.6.0 compatibility and C5 descriptor repair — accepted

Official state advanced to shared toolkit `v2.6.0` at
`bd01548e34d21fd660d88fd06157078fb25ece4e` and Track 4 main
`1c744e1d6725340643a533f436517d72b53ca0e1`. The release describes organizer-side trust-purpose,
`not_reached`, unit-handle and Final leakage-scan changes and explicitly says 2.5.1 submissions
remain valid. Direct downloads at both pins show byte-identical Track 4 scorer 5.2.2,
`analysis.schema.json` and `submission.schema.json` content.

The preregistered assumption that no local change was required nevertheless failed. Running the
official v2.6.0 packer with a synthetic non-secret team key rejected the tracked template because
its `image` was a string. The unchanged C5 schema requires an object containing `registry`,
`repository` and `digest`, so this was a pre-existing local template defect rather than a 2.6.0
breaking change. After the minimal shape repair, the same pack command succeeded, generated
`team_id` and `descriptor_digest`, and produced a ZIP containing exactly `submission.json` and
`team-claim.json`; no key field appeared in either artifact. No real team key was read and no
competition submission was made.

The image workflow now repeats this smoke on remote Python 3.13 with the pinned v2.6.0 package and
a visibly synthetic key before building the container. This closes the gap where unit tests and an
image command smoke could pass while the submission descriptor remained unpackable.

The same audit incorporated official Track 4 Issues 19 and 20. Development displays
`-0.27 + 1.27 * analysis_score`; reasons are Final-only and do not appear on the Development board.
Issue 20 confirms that a missing `qfbench2.interface_version=2.0` label can stop scoring after all
units run, that on-demand image pull time counts against a unit, and that the House route was active
for all ten diagnosed units. The current image is anonymously readable, Linux/amd64, correctly
labelled and about 44.2 MiB compressed. Production prediction code and the image were unchanged.

Report: `evaluation/reports/toolkit-260-submission-compatibility-v1.json`.

## 2026-10-03: Treasury auction proxy-15 schema invariance — rejected

The second runnable proxy question forecasts indirect-bidder acceptance share for the 3-, 10-, and
30-year Treasury auctions announced on 2023-08-02. Both explicit and transformed units share the
same cutoff-safe twelve-auction histories, hidden outcomes, recent-six naive answers and reversed
but equivalent rosters. The source snapshot and all unit manifests rebuild deterministically.

The predeclared hypothesis required the transformed composite to finish no more than 0.05 below the
explicit unit. The explicit specialist route scored 0.5000 before claim penalty, effectively equal
to the naive recent-six mean. The transformed generic route scored 0.0655 because it selected
`security_bucket_months` as the forecast quantity, producing 36, 120 and 360 percentage-point
forecasts. The 0.4345 decline rejects the hypothesis and identifies a target-aware numeric-field
selection weakness. The benchmark infrastructure and failed result are retained; production logic
is unchanged. No model API or local model ran. Report:
`evaluation/reports/proxy-15-auction-control-v1.json`.

## 2026-09-29: generic fraction-to-percent scaling — rejected

The generic selector recognizes percent, basis-point and USD identifiers but does not normalize
explicit `_fraction` or `_decimal` encodings. A no-model transformed-schema candidate multiplied
those fields by 100 for percent targets and divided explicit percent fields by 100 for fraction or
decimal targets. It never inferred scale from value magnitude and left bare ratios and unspecified
units untouched.

The candidate exactly restored the native percent-encoded CPI and COT benchmark metrics, passed all
seven bidirectional conversion and isolation controls, and left auction, macro-revision and FOMC
results exactly unchanged. It still failed the real-outcome adoption gate: on the fraction-encoded
CPI test, MAE rose from 1.2856 without conversion to 1.4923 after correct conversion; on COT it rose
from 4.9979 to 6.9628 while rank correlation was unchanged. The near-zero wrong-scale values happened
to outperform full persistence because recent changes are weak forecasts of future changes.

Production was not modified. The result shows that unit normalization cannot be separated from the
generic change-baseline model and should not be adopted only for semantic neatness. No model API or
local NLI ran. Script: `evaluation/experiments/generic_fraction_scale_screen.py`. Report:
`evaluation/reports/generic-fraction-scale-screen-v1.json`.

## 2026-09-29: quote-local citation context — rejected before production

The official shared and Track 4 main commits, toolkit `v2.4.4` and open Track 4 Issues 1, 2, 13,
14 and 16 were unchanged. The public website now displayed Development leaderboard results, but no
runtime or scoring rule changed. A refreshed GitHub search found the same two licensed Track 4
participant implementations. The MIT-licensed `wangzgui/agenthon-t4-baseline-2026` added a bounded
window around model-verified quotes at commit `420bee09`: 120 characters before and 240 after.

Production already preserves each compact fact citation and appends up to three exact, scoped BM25
chunks. A read-only screen therefore asked whether the public method supplied entity identity and
target terms absent from both the fact and those existing contexts. Across 80 saved production fact
citations, 31 expanded windows were fully contained in an existing context. Forty-nine crossed an
existing context boundary, but only 11 supplied both term classes; all 11 belonged to CPI regression
and only ten entities. The pre-registered requirement of at least two families and two target types
failed.

No production code, prompt, prediction or citation changed. No model API or local NLI ran. The
screen and rejected result are in `evaluation/experiments/citation_local_context_screen.py` and
`evaluation/reports/citation-local-context-screen-v1.json`.

References:

- <https://github.com/wangzgui/agenthon-t4-baseline-2026/commit/420bee094775f30e43fd18e10982402c91d90e23>
- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/Agenthon-2026/Agenthon2026-public>

## 2026-09-29: CPI core and food twelve-month mean — accepted

The Cleveland Fed Inflation Nowcasting FAQ specifies a twelve-month moving average for its core and
food CPI monthly forecasts. That externally fixed rule was compared with production's 70% latest
change plus 30% recent-three median on a newly built, cutoff-safe ALFRED confirmation panel. The
builder was parameterized for arbitrary month ranges; rebuilding 2015-2023 reproduced all 1,188
existing rows and the raw-cache hash exactly before 2024-2025 was read.

On 24 core/food rows in 2024, the twelve-month mean reduced MAE from 0.1052 to 0.0914 and RMSE from
0.1318 to 0.1144 while retaining 100% direction accuracy. On 18 complete-history rows in 2025, MAE
fell from 0.1787 to 0.1147, RMSE from 0.2108 to 0.1457 and direction accuracy rose from 88.9% to
94.4%. The two December 2025 rows were excluded by the predeclared exact-twelve-history rule after
the canceled October release interrupted the monthly-change chain.

Production applies the mean only to `CPI_CORE` and `CPI_FOOD`, only with exactly twelve values, and
only for cutoffs on or after 2026-02-01. The new path gives exact component headers priority so
`Food` cannot bind to `All items less food and energy`; the legacy path is unchanged. Python 3.13
passed 124 tests. A clean archive of baseline `03c1f21` and the candidate produced byte-identical
offline answers for all 11 public units and 78 rows. Those bytes are identical to the previously
source-pinned 11/11 smoke-admissible baseline, so heavy local NLI was not repeated. No model API or
local language model ran. Report: `evaluation/reports/cpi-core-food-mean12-confirmation-v1.json`.

References:

- <https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting>
- <https://alfred.stlouisfed.org/>

## 2026-09-29: context formatting recovery — rejected

A saved `nemotron-3-super-120b-a12b` public run contained only three rejected facts. Two were context
quotes where the model changed formatting: it inserted dollar signs into an EPS table or removed
bullet glyphs and whitespace from a debt passage. A context-only candidate removed `$`, `•` and
whitespace for matching, required at least 40 normalized characters and exactly one occurrence, then
restored the original corpus slice. Signal and numeric-parameter validation stayed strict.

The candidate recovered both contexts across the credit and EPS YoY families, restored exact source
spans, retained the rejected EPS signal, and passed four substantive-edit, ambiguity, short-quote
and wrong-document controls. It nevertheless failed the pre-registered cross-target gate: both
published units declare classification targets, so the evidence covered only one target type rather
than classification plus regression. Production code and tests were rolled back. The reproducible
screen and rejected result remain in
`evaluation/experiments/context_formatting_recovery_screen.py` and
`evaluation/reports/context-formatting-recovery-screen-v1.json`. No model API or local NLI ran.

## 2026-09-28: generic explicit-unit compatibility — accepted

The official state check remained unchanged: shared main `95a0de3`, Track 4 main `7b2bce1`, toolkit
tag `v2.4.4` (annotated object `1bc80b5`, peeled commit `68bc878`) and open Track 4 Issues 1, 2, 13,
14 and 16. A fresh GitHub repository search returned no additional public Agenthon Track 4 agent
implementation beyond the official repository, so no participant code was copied.

The generic scalar selector previously removed `pct` and `bps` from semantic target matching but did
not preserve them as units. A transformed unknown schema could therefore match
`future_curve_response_bps` to `current_curve_response_pct` on the shared word `curve` and use a
percent level as a basis-point change. The accepted guard rejects a field only when both identifiers
explicitly declare incompatible percent, basis-point or USD units. It does not infer missing units.

Five cutoff-safe real-outcome datasets formed the A/B screen. On 156 FOMC test rows, blocking the
percent-to-basis-point mismatch reduced MAE from 14.5180 to 14.2244 bps and RMSE from 20.5140 to
20.0424. CPI (264 rows), COT (96 groups / 960 rows), 2024 Treasury auctions (70 rows) and macro
revision (460 rows) were exactly unchanged. Five synthetic controls covered both mismatch
directions, compatible percent and basis-point fields, and unspecified units.

Python 3.13 passed 122 tests. A clean archive of baseline `9ad1b7a` and the candidate produced
byte-identical offline answers for all 11 public units and 78 rows with no validation errors; a
fresh source-pinned toolkit/Track 4 smoke run admitted 11/11. Temporary pytest and smoke dependencies
were installed under `/tmp` with pip caching disabled and removed after each run; no project virtual
environment, local language model or model API was used. Reports:
`evaluation/reports/generic-unit-compatibility-screen-v1.json` and
`evaluation/reports/generic-unit-compatibility-v1.json`.

References:

- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/Agenthon-2026/Agenthon2026-public/releases/tag/v2.4.4>

## 2026-09-28: free development model and quota policy

Official documentation is sufficient for initial model selection, so no multi-model token benchmark
was run. The House model thinks by default and permits per-request disabling. The existing controlled
House-family experiment remains the decision evidence for production: thinking did not change the
final label, increased completion tokens from 213 to 2,143, and failed to reach parseable JSON under
the 700-token extraction cap. Production therefore keeps thinking off unless a task-specific A/B
shows a scored benefit.

Google documents Gemini 2.5 Flash-Lite as non-thinking by default and offers free-tier input/output;
it is now the default quota-conscious development extractor. Gemma 4 26B A4B is free through the
Gemini API and activates 3.8B of 25.2B parameters, making it useful for weak-model stress tests, but
its parameter efficiency does not imply lower token consumption. OpenRouter remains the closest
exact-family analogue, but its Free plan currently advertises only 50 requests/day. It is reserved
for preregistered House-behavior comparisons, while deterministic replays and Gemini Flash-Lite cover
routine development. Details and source links are in `docs/model-api-notes.md`; registries now record
both providers without storing credentials.

## 2026-09-26

### Official findings

- House identity is Nemotron 3 Super 120B A12B rather than the previously assumed 7B class.
- The model thinks by default; disabling thinking is supported but is a strategy choice.
- The 262,144 value is tokenizer metadata, not a promised serving context limit.
- The old cumulative token allowance is withdrawn. The operative budget is 25 admitted requests
  and 4,000 output tokens per request.
- Track 4 allows disclosed non-neural predictors and calibration artifacts, but no second language
  model or adapter in the submission image.

### Public implementation review

The GitHub search found one other clearly Track-4-specific participant repository:
<https://github.com/garroshub/agenthon2026-t4>, inspected at
`75efbb0ada0fff404a6df721dad6179790de24a2`. It has no repository license, so no code was copied.

Ideas independently worth testing against primary data:

- Direct House forecasts over batches rather than signal-only extraction
- Family-specific deterministic adapters for auction and EPS growth
- Cutoff-safe historical calibration for rate, EPS and classification intervals
- Wider probability support for credit-event intervals
- Reducing House calls through larger batches

The official strong-RAG scaffold independently recommends direct row-level prediction plus a
calibration head. Its claimed quality remains a specification pending staging validation.

### First model experiment

OpenRouter's exact public model-family endpoint was free on the research date. The first call failed
because the production client correctly denied provider data collection; a public-corpus-only,
explicit opt-in was added for development. A second incompatibility consumed the completion budget
as reasoning with no final content; mapping the local `T4_ENABLE_THINKING` setting to OpenRouter's
`reasoning.enabled` fixed it.

The complete thinking-off signal-extraction run improved mean predictive quality from 0.3122 to
0.3804 and mean pre-gate composite from 0.1058 to 0.1581 at zero cost. Credit-event accuracy rose
from 0.50 to 0.75 and EPS-YoY accuracy from 0.50 to 1.00. FOMC and post-earnings remained weak.

### FOMC interval calibration v1 — rejected

The experiment used official U.S. Treasury daily par-yield CSVs from 2000 through 2021. It fitted
35-trading-day absolute-move quantiles through 2016 and selected the quantile closest to 90% coverage
on 2017–2021. The selected 80th-percentile half-widths were 36–43 basis points depending on tenor,
with 91.2% development coverage. Neither the calibration script nor selection step read the 2022 or
2024 retired public outcomes.

After locking the artifact (`06bf01b45a28e4f77fc27218b7e8a9a7065d60af50ac6d31a9128c8898ddb20f`),
the one-time holdout check found 0% coverage for both the current +/-75 bp intervals and the candidate
intervals. Mean calibration loss stayed at 0.9, so the candidate was rejected. The failure indicates
that the current FOMC point model misses post-decision curve direction and magnitude; narrowing a
historical interval cannot repair it. The holdout report SHA-256 is
`cb2247567bdf13cf60b62c02eac637c692b6df64c32853fd6e8f671a6af04e4e`.

Next experiment: apply probability-domain interval bounds to credit-event forecasts. This is a
semantic invariant of the requested output, rather than a coefficient fitted to the retired cases.

### Credit probability support v1 — accepted

Credit-event point forecasts are probabilities, and there is no cutoff-safe population calibration
sample in the current bundle. Using the fixed probability support `[0, 1]` preserves point forecasts,
labels, retrieval, and citations. On the 11-unit diagnostic set, mean predictive quality stayed at
0.3804, mean coverage rose from 0.5606 to 0.6061, and mean pre-gate composite rose from 0.1581 to
0.1662. The full 30-test suite passed and the CLI produced all eight credit rows with the new legal
interval. The change is accepted, with the public-set and missing-NLI limitations recorded in the
experiment report.

### Thinking-on extraction v1 — rejected as the default

The exact public Nemotron endpoint was tested on the EPS teaching unit with identical retrieval,
prompt, temperature and seed. At the production extraction allowance of 700 output tokens, two
attempts exhausted the allowance without one parseable JSON object and opened the circuit breaker.
At the official maximum of 4,000 output tokens, one attempt returned valid JSON after 2,143 completion
tokens and about 23 seconds. Thinking-off returned valid JSON in 213 completion tokens. Thinking
changed the extracted signal from neutral to +1, but both paths produced the same final `1.50` /
`inline` forecast, so there was no measured output benefit to justify roughly ten times the completion
tokens. Thinking remains an opt-in experiment for tasks where it can change the scored answer.

### Submission-image checkpoint

GitHub Actions run <https://github.com/Yif-design/Agenthon2026/actions/runs/36243893020> passed unit
tests, linux/amd64 image build and push, and the container command smoke test. Immutable image:
`ghcr.io/yif-design/agenthon2026-t4@sha256:09ddf7a8cc9d027263255d26a1f2fa74256eb59768165d3c781b1dbd9a261d9b`.

### FOMC point models v1 — rejected

The research baseline follows the Federal Reserve's finding that Treasury yields are close to
non-stationary and that yield-only models rarely beat a no-change random walk consistently:
<https://www.federalreserve.gov/pubs/ifdp/2010/993/ifdp993.htm>. The level/slope/curvature candidate
follows the dynamic Nelson-Siegel interpretation described by Diebold and Li:
<https://www.nber.org/papers/w10048>.

A new dataset combines 152 official Federal Reserve policy statements with official Treasury daily
curves. A per-tenor curve-and-policy ridge selected on 2016–2018 improved development MAE to 13.91
bps, but deteriorated to 19.18 bps on the untouched 2019–2021 test, 34.8% worse than the 14.22 bps
zero-change baseline. It was rejected. The existing policy-decay rule scored 14.58 bps on test;
zero-change was slightly better on test but slightly worse on development. On the retired public
diagnostic pair, the two rules had identical average MAE and identical official-quality proxy scores.
Evidence was therefore insufficient to replace the current production point model with zero-change.
The structured report SHA-256 is
`8112b2acbc33dc265184915f23b23e8a757e51449da75c423cfe7872a1d7bfc5`.

### Post-earnings interval calibration v1 — accepted

The SEC API was inaccessible from the development host, so announcement dates came from Quant500's
CC0 dataset (<https://quant500.com/data>), which preserves SEC accessions, source links, session and
data-quality flags. Yahoo adjusted closes reproduce the retired 2024 AAPL/AMZN/META abnormal returns
within 0.00015 percentage points, validating the event-window implementation.

A deterministic 100-company selection yielded 2,092 usable after-close events across 88 symbols.
The 2018–2020 training quantiles were selected only on 2021 development coverage. The selected 8.2915
percentage-point half-width covered 88.95% of development and 81.60% of the untouched 2022–2023 test,
versus 36.38% for the production 2.5-point half-width. The production constant was rounded to 8.3.
On the 11-unit diagnostic set, mean quality stayed 0.3804, mean coverage rose from 0.6061 to 0.6364,
and mean pre-gate composite rose from 0.1662 to 0.1753. Point forecasts, labels and citations did not
change. The report SHA-256 is
`5122d9ae5be1ea53ce17fd57e0d4e735c2f86fed3c6f1e99d517de87387b21d7`.

Label experiments were not accepted. Always-positive and prior-reaction baselines changed relative
performance between development and test, and the current flat label remained poor. Research shows
that announcement returns depend on information absent from this task's prior-filing-only corpus,
including expectations and within-quarter signals; see <https://www.nber.org/papers/w22366>.

## 2026-09-27

### Macro-first architecture audit

The official Track 4 README was rechecked at public commit
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`. It explicitly describes the eleven published units as
format exemplars and says the larger hidden set contains many families without a published
counterpart. It also recommends starting with a text-blind tabular baseline before adding text.
Toolkit `v2.4.4`, 25 admitted requests per unit, 4,000 output tokens per request, no cumulative
token allowance, 600 seconds and restricted network remain current. No newer toolkit tag or Track 4
code commit was present on 2026-09-27.

An L1-L5 audit therefore selected the missing direct-vs-signal-vs-hybrid comparison ahead of more
auction-specific work. The new development-only `architecture_ab.py` uses the same task, cutoff,
scoped BM25 evidence, model, seed and temperature for a direct forecast. Invalid rows fall back to
production, and the pre-registered hybrid is a fixed 50/50 point blend. Public reconstructed
outcomes are only a feasibility screen; production adoption requires a new, previously unused,
time-forward holdout after a promising screen.

The complete screen used eleven task-level free Nemotron calls, 139,272 prompt tokens and 12,927
completion tokens at zero reported cost. Only 52 of 78 direct rows passed numeric, label and exact
quote validation; 26 used the production fallback. Against the current calculator replay, direct
reduced mean predictive quality from 0.3864 to 0.2576 and pre-gate composite from 0.1878 to 0.0012.
The fixed hybrid produced quality 0.2804, coverage 0.7221 and composite 0.1311. Both outputs passed
11/11 smoke units, which confirms that formal validity did not imply useful forecasts. The
complete-roster direct call and fixed hybrid were rejected. A smaller-batch direct experiment
remains distinct because the current run omitted most macro-revision rows and collapsed COT scores
to a tie. Report SHA-256:
`b41944bbdfbfec7f6a73cb945f62f2afc2841256d461acd282535b4fe81cc963`.

The follow-up used direct batches of at most three entities on macro revision, bank EPS growth and
COT, covering classification, regression and ranking. Eleven calls used 63,191 prompt and 5,766
completion tokens at zero reported cost. Valid exact-quote rows improved from 10/30 in the
equivalent complete-roster outputs to 27/30. Despite the reliability gain, representative mean
quality fell from 0.5002 for production to 0.2701 for direct and 0.3833 for hybrid. Mean pre-gate
composite fell from 0.3460 to -0.0251 and 0.2642. Both candidates still passed 11/11 smoke when
combined with unchanged production answers. The candidate was rejected, and direct batch-size
tuning stops under the macro-first rule. Report SHA-256:
`52171827d212c7254c51523facd978e5481ee45a0f24ee5df30b526cb63b65c7`.

### CFTC positioning model v1 — accepted

The official CFTC public-reporting API supplied 4,690 legacy futures-only observations for the ten
task-aligned contracts. Aligning common weekly dates produced 445 five-week forecasting groups. The
experiment used 2015–2020 for training, 2021 for development selection, and read 2022–2023 only once
for the final test. Rebuilding from the cached primary response reproduced the tracked dataset and
report exactly after normalizing only the build date and output path.

The previous trailing-change/crowding-cap rule had negative mean Spearman correlation on development
and test. Development selected the simple forecast `-0.2 * current net_%OI`. On the untouched test,
mean Spearman improved from -0.0385 to 0.0379 and MAE improved from 6.5399 to 5.7595 percentage
points. A training quantile selected an 11.2821-point interval on development; the production value
is rounded to 11.3. Test coverage improved from 66.56% to 87.19%, reducing absolute calibration loss
from 0.2344 to 0.0281.

On the retired public diagnostic, COT quality improved from 0.6848 to 0.7515, MAE from 6.6471 to
5.4884, and coverage from 0.60 to 0.90. Across all 11 units, mean quality improved from 0.3804 to
0.3864, mean coverage from 0.6364 to 0.6636, and pre-gate composite from 0.1753 to 0.1878. The formal
CLI returned all ten roster rows with exact frozen-corpus spans and no model calls. The calculator
also now discovers the latest date-suffixed input field instead of depending on `20241022`. All 32
tests pass, and fresh Python 3.13 outputs for all 11 public units passed the official smoke verifier
with 78/78 roster rows. The comparison report SHA-256 is
`66b884aafef8390f5f29f9a3be2172979946380e0fc600a1f3be6cd0dc17b8e0`.

### CPI vintage point models v1 — rejected; interval floor — accepted

ALFRED real-time snapshots produced a complete 1,188-row panel for the eleven task components from
2015 through 2023. Each feature row uses the month-end vintage before release and each target uses the
following month-end vintage. The eleven December 2023 targets reproduce the archived BLS release
Table A after rounding to its one-decimal publication precision. Raw downloads remain outside Git.

On 2021 development, the lowest-MAE point candidate was simply the latest known monthly change. On
the untouched 2022–2023 test it worsened MAE from 1.4096 for the production blend to 1.4923 and RMSE
from 3.0702 to 3.3570 percentage points, so the point change was rejected. A separately selected
interval candidate kept the production point and 1.65 volatility multiplier but raised the minimum
half-width from 0.35 to 0.75. Test coverage improved from 85.23% to 89.02%; absolute error from the
90% target fell from 0.0477 to 0.00985 while mean full width rose from 4.12 to 4.48 points.

The interval-only change left the retired 11-unit diagnostic quality, coverage and composite exactly
unchanged at 0.3864, 0.6636 and 0.1878. The public CPI unit's missed rows were volatile components
whose intervals already exceeded the old floor. All 32 tests pass, and fresh Python 3.13 outputs for
all 11 public units passed the official smoke verifier with 78/78 rows. The report SHA-256 is
`3c69f3c7c2a04e01b58f5bfdc7cd939823513ea3e054f73701dc5998a5764aed`.

### Treasury auction recent-mean model v1 — accepted

The official Track 4 and toolkit sources were rechecked before this family cycle. Track 4 remained
at `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`, the shared toolkit main remained at
`95a0de3d9a814f3883c151b7efdbbcf579139244`, and installed `qfbench2-common` remained 2.4.4. No rule
change affected the 25-request, 4,000-output-token, 600-second or restricted-network boundaries.

The Treasury Fiscal Data Auctions Query supplied 1,124 nominal coupon auctions through the public
task cutoff. The first builder incorrectly rejected 602 records because the published BTC did not
exactly equal a naive `total_tendered / total_accepted` calculation. Treasury's BTC field is the
authoritative outcome and the totals contain category/add-on semantics, so the final builder keeps
the reported result and records the reconciliation difference only as a diagnostic. Seven target
tenors are present, date/CUSIP keys are unique, no announcement follows its auction date, and a
cached rebuild reproduced dataset SHA-256
`1dd97882feb1a754fa4ade81f06d77bca871d3c5dae2f8e2922dec8628bfbb1a`.

Development selected the last-six same-tenor mean over last value, mean/median alternatives,
recency weighting, reopening-conditioned history and the production mean-plus-clipped-trend rule.
It also selected 2.5 times recent population standard deviation from a fixed multiplier grid for a
90% interval. On the 168-row 2022-2023 test, MAE improved from 0.10969 to 0.10074 and calibration
error from 0.04881 to 0.01071. Because the point test had already been inspected before interval
calibration was added, the combined candidate was frozen and checked on a separate untouched
70-row January-October 2024 confirmation set. There MAE improved from 0.10250 to 0.08848, RMSE from
0.12634 to 0.11026 and calibration error from 0.07143 to 0.02857. The paired-bootstrap 95% interval
for mean absolute-error improvement was `[0.00326, 0.02486]`.

Production enables the selected rule only for cutoffs on or after 2022-01-01, after the development
period. Earlier tasks retain the preceding heuristic. A new unit test covers the point, interval,
citation window and cutoff gate. All 33 tests pass, and fresh model-free CLI outputs for all eleven
public units passed the official smoke verifier with 78/78 rows. The retired public aggregate
diagnostic remained quality 0.3864, coverage 0.6636 and composite 0.1878 because the auction unit
stayed at zero quality and 5/7 coverage. Report SHA-256:
`798568bae80f5c27b787a689b9ee3756cc85aad1e4b22d9128727339642f8df1`.

### Cross-family artifact availability gates v1 — accepted

The provenance audit found that accepted COT, CPI and post-earnings constants were documented but
were enabled solely by family routing. A hidden historical task with a cutoff before their 2021
development labels could therefore receive a parameter selected using future outcomes. Auction had
already added a local cutoff guard in the preceding cycle.

A shared fail-closed ISO-date helper now controls all four fitted family paths. Their current
availability date is 2022-01-01, immediately after the latest development observations. Earlier
cutoffs restore the preceding COT trailing-change/crowding rule, CPI interval floor and
post-earnings interval; auction retains its preceding mean-plus-trend fallback. Missing or malformed
cutoffs also disable fitted parameters. Each family records the decision and availability date in
its calculator trace. The COT dated-field selector now also rejects suffix dates after the task
cutoff instead of blindly taking the largest date.

The acceptance test regenerated all eleven public units before and after the change: all 78 answer
rows were byte-identical, and all eleven passed the official smoke verifier. Early-cutoff synthetic
checks exercised each fallback and a future-dated COT distractor, and the complete suite remained
at 33 passing tests. Predictive
metrics are intentionally unchanged; this is a cross-family embargo and reproducibility fix.

### Official ensemble-NLI audit and auction citation selection — accepted

The remote Track 4 repository remained at
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`. Its current `faithfulness/judge.py` SHA-256
`93757e18214a1057c2899f12baf4c67d827025fc69fabad032663822e256464a` exactly matched the local
judge used in this experiment. The remote README has newer policy wording than the local starter
snapshot: it pins toolkit `v2.4.4`, withdraws the old cumulative token allowance, removes BYO model
guidance and retains 25 admitted requests with at most 4,000 output tokens each. The project rules
document already reflected those operative constraints. Installed `qfbench2-common` was 2.4.4.

The local audit fixed both official NLI members to revisions
`bab4bc7178836f731dcfd18c06ca9def0a137712` and
`b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7`. The development runtime was Python 3.11.7,
torch 2.2.2 and transformers 4.46.3 on Intel CPU, so this is a production approximation rather
than a runtime-equivalence claim. A classification EPS unit and ranking COT unit passed at 1.0
faithfulness. The regression auction unit failed at 5/7 because the 10-Year and 7-Year citations
did not cross the 0.5 ensemble threshold.

Keeping every forecast, interval, cutoff and canonical hypothesis fixed, four exact-span variants
were scored with both models. Recent-six rows remained at 5/7. A concise `NOTES` sentence directly
reporting the same recent-six mean, recent rows plus that note, and the full same-tenor document each
reached 7/7. The concise variant reduced total cited text from 2,452 to 1,673 characters, increased
mean ensemble entailment from 0.5577 to 0.7091 and raised the weakest entity from 0.3786 to 0.5403.
Although rows plus note had the highest mean score, 0.7827, its weakest score was only 0.5064 and it
used 4,139 characters. The concise variant was adopted as the less noisy passing input.

Production uses the summary only when its reported recent-six average agrees within 0.001 with the
calculator's independent mean of the source rows. Missing, mismatched and pre-2022 summaries fall
back to the existing rows. The production span omitted only the experiment span's final newline;
both fixed tokenizers produced identical input IDs for all seven hypotheses, so the measured 7/7
scores apply exactly to the production model inputs. Forecasts and intervals were unchanged, all
eleven public outputs passed smoke, and the other ten outputs were byte-identical to the preceding
baseline. Full details and reproducibility limits are in `docs/nli-gate-audit.md`.

### Full public NLI audit and retrieved-context candidates — accepted

The remaining eight public units were run through both fixed NLI members. The first experimental
runner revision had retained only the best score per entity and therefore could not reconstruct the
official aggregation for multiple citations. It was corrected to record every distinct
premise/hypothesis pair by premise hash. The combiner now aligns those citations, averages member
scores per citation, and only then takes the entity maximum and applies the strict greater-than-0.5
threshold. A synthetic case where each member preferred a different citation verifies that the
incorrect max-before-average order fails. Legacy one-citation reports recombined identically.

After the auction fix, six of eleven public units passed NLI. Macro revisions scored 0.6667,
post-earnings 0.6667, credit event 0.2500, bank EPS growth 0.0000 and EPS YoY direction 0.3333.
Inspection showed a shared citation-construction defect: the system often submitted a compact
calculator fact or only the beginning of a retrieved chunk, while the relevant table header,
guidance, liquidity or earnings comparison remained later in the same cutoff-safe chunk.

An A/B kept all predictions and compact facts fixed and added the top retrieved chunk as another
exact citation. Macro revisions and EPS YoY rose to 1.0; bank EPS rose to 0.625, while post-earnings
and credit stayed below the gate. Extending the three remaining failures to top-three chunks raised
post-earnings to 1.0, credit to 0.875 and bank EPS to 0.875. This candidate adds no model requests,
prompt tokens or inference latency. The three measured answers were 4.9–12.7 KB, and all passed
smoke. The top-one-only variant was not adopted because three of five baseline failures remained.

Production now preserves up to three compact facts and appends at most three distinct retrieved
chunks after rechecking document scope, exact bounds and source equality. The CLI regenerated all
eleven units with unchanged labels and numerical predictions (absolute tolerance `1e-12`), and all
eleven passed smoke. Measured top-three spans were reproduced exactly; top-one passing answers and
the six already passing baselines are strict citation subsets. Because the official entity score is
the maximum of per-citation ensemble scores, their gate status cannot regress. The resulting proven
public gate count is 11/11 versus 6/11 before the shared candidate. Structured summary SHA-256:
`35bd886c2bbde61f080e8ef56f50dc4a3989ecc9aa39211f9ba8db145e4d44fe`.

### Generic target-aware numeric baseline — accepted

The official starter and Track 4 heads remained at
`95a0de3d9a814f3883c151b7efdbbcf579139244` and
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`; the installed official toolkit remained 2.4.4. A
public GitHub search found the official repository but no additional public contestant
implementation suitable for comparison. The official development guidance explicitly recommends a
text-blind tabular baseline as the prediction floor, which made the generic numeric fallback the
next shared layer to audit.

The legacy generic path took the median of every numeric entity field for regression and used input
row position for ranking whenever a fixed known field name was absent. A five-check synthetic audit
showed that it selected 200 instead of the target-related value 8, changed that result to 1,112 when
an irrelevant numeric row ID was added, reused a 4.5 yield level for a yield-delta target, and
changed ranking scores when the same entities were reordered. It passed only the single-numeric
fallback check.

The candidate token-matches numeric field names against the target, rejects unrelated numeric
metadata, uses zero when a change target has no matching change field, and retains the unambiguous
single-field fallback. It passed all five checks versus one for the baseline. This is a robustness
result, not predictive-accuracy evidence. Replaying all saved validated public signals produced
unchanged labels, points and intervals for 78/78 rows; all eleven outputs passed official smoke.
The complete suite passed 47 tests. Report SHA-256:
`11cce19c5ae589b856dbaa96154af53c9b7c93d822e576db6c6dbe07fa616381`.

### Generic grounded direct label v1 — deferred and current candidate rejected

The deterministic generic label mapper correctly handled 8 of 13 synthetic rows across five
unseen label vocabularies. A preliminary simplified one-call prompt mapped all 13 labels and copied
all 13 quotes with the free Nemotron analogue, so a production candidate asked the existing generic
classification extraction call for one allowed label with an exact quote. No additional request was
needed when a batch was complete, and invalid labels or quotes fell back to the old mapper.

Production-shaped runs were not stable: the first run produced 6/13 correct with only three
validated label facts after a malformed response opened the experimental circuit; fixed-seed runs
then produced 13/13 and 11/13. Inspection of the latter failure found that `action_flat` and
`action_down` both received the `action_up` document. The shared BM25 tokenizer had retained the
sentence-final period in tokens such as `action_flat.`, so the exact entity query token
`action_flat` did not match and every document scored zero. The retrieval fallback then selected
the first document.

The direct-label production code was fully rolled back. Retesting is deferred until punctuation
normalization is repaired and independently checked across public retrieval results. Structured
summary SHA-256: `9bd2e781ecd82b2c24a1365bf25d60620089022d0e53e3376ae9046532e1a688`.

### Punctuation-normalized lexical retrieval — accepted

The deferred generic-label audit exposed a shared L2 retrieval defect. The legacy token expression
retained sentence-final periods, so a query for `action_flat` did not match `action_flat.` in a
document. When every chunk scored zero, stable ordering silently selected the first allowed chunk.
Across thirteen unseen-label synthetic entities, legacy BM25 retrieved the correct top-one document
once; punctuation-normalized BM25 retrieved all thirteen. Tests also pin `$5.28`, `10%`,
`2024-10-31` and `year-over-year` so normalization does not split common financial tokens.

The public retrieval A/B changed the top three chunks for 25 of 78 rows across seven units. A strict
no-model replay using identical code and inputs except for the tokenizer changed zero labels, point
forecasts or intervals; it changed only those 25 citation lists. A free Nemotron analogue generated
all eleven production-shaped answers using 12 calls, 91,295 prompt tokens and 7,115 completion
tokens at zero reported cost. Three malformed JSON responses were contained by retry/fallback logic.
All eleven answers passed the official smoke verifier with all 78 roster rows.

Every affected unit was then scored with both fixed official NLI members at revisions
`bab4bc7178836f731dcfd18c06ca9def0a137712` and
`b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7`. The local official judge no longer accepts a
`revision` constructor argument, so the audit runner now resolves the requested revision to its
exact cached snapshot path and fails closed when that directory is absent. Citation-level ensemble
faithfulness was 1.0 for auction, EPS YoY, the 2024 FOMC curve and post-earnings; 0.9091 for CPI; and
0.875 for credit event and bank EPS. All seven crossed the 0.80 gate. The two CPU members took
1,490.6 and 2,855.0 seconds for 198 citation pairs each. The candidate was accepted. Structured
summary SHA-256: `50dea380b4370bd6c178b31ccb9c561d20921a7611a8f29f506184fe3a25f3ba`.

### Generic grounded direct label v2 retest — rejected

The grouped direct-label experiment was rerun only after the shared tokenizer repair had been
accepted. Both fixed-seed runs retrieved the correct entity document for all 13 synthetic rows, so
the earlier retrieval confound was removed. The deterministic mapper remained at 8/13. Seed 1234
reached 10/13 but validated only six exact label quotes after malformed JSON responses opened the
model circuit. Seed 5678 reached 13/13 with all thirteen quotes validated. The runs used five and
six free-provider calls and stayed below the official per-unit request cap.

The pre-registered rule required both seeds to reach at least 12/13 and validate every quote. It
failed, so no production direct-label code was introduced. Correct entity retrieval is necessary
but did not make grouped structured output stable enough for a hidden-schema fallback. A future
candidate needs an independent reliability mechanism, such as a smaller constrained response or a
request-budget-aware retry policy, rather than another label-prompt wording change. Structured
summary SHA-256: `46ef6da4770cbe3b665731ee2c9ae875a05235aadc9a5cfa859dc8494974e137`.

### Cross-batch model circuit threshold — accepted

A response-shape probe found that a healthy Nemotron analogue response placed complete JSON in
`message.content`; `reasoning` was empty and the existing parser succeeded. There was therefore no
evidence for reading a provider-specific alternate field or loosening JSON parsing. The shared
failure was circuit policy: exhausting two attempts for one malformed batch immediately disabled
all later, independently scoped batches in the unit.

The candidate retains two attempts per batch but opens the shared circuit after four consecutive
failures. A deterministic response sequence of malformed, malformed, valid now lets the first batch
fall back and the next batch succeed on call three; four persistent malformed responses still open
the circuit. Success resets the count. Authorization refusal, non-retriable client errors, the
18-call default cap, 25-call hard cap and model-phase deadline remain unchanged.

All 51 tests passed. Eleven fresh no-model public outputs were byte-identical to the tokenizer
baseline and all eleven passed smoke with 78 rows. A non-simultaneous free-provider replay improved
the synthetic unknown-label run from 6 to 12 validated quotes and from 10/13 to 13/13 labels while
using six instead of five calls. Provider nondeterminism prevents attributing that numerical change
solely to the circuit policy, so it is corroborating evidence only; the adoption claim is improved
partial completion under deterministic injected failures, not predictive accuracy. Structured
summary SHA-256: `232567285ec862ef357bab28de8734b9cdf205d1e8ff247b2af391b10aec1eb0`.

### Batch identity consistency — accepted

The shared batch unpacker supported response reordering by preferring `item_id` and falling back to
`entity_id`, but it did not compare the two when both were valid. A model row with `item_id=0` and
the second entity's ID could therefore be assigned to the first entity. Exact-quote scope usually
rejects a foreign document, but shared macro documents make that an incomplete defense.

The candidate rejects only rows whose valid identifiers resolve to different requested entities.
Consistently reordered rows still map correctly; a partial response preserves returned siblings and
falls back only missing entities. The change adds no requests, tokens or prompt text. All 53 tests
passed. Eleven fresh no-model public answers were byte-identical to the preceding baseline and all
eleven passed official smoke with 78 rows. The candidate was accepted as an evidence-isolation and
typed-intermediate reliability improvement; it makes no predictive-accuracy claim. Structured
summary SHA-256: `d632d73de1a900b431e664d37e78b4bd2586fed445a9c8a2e620e4bc384237f3`.

### EPS YoY interval calibration v1 — accepted

The preceding generic and shared-architecture audits were complete, so the next family cycle targeted
EPS YoY direction: its retired public labels were all correct, but only three of six numeric outcomes
fell inside the declared 90% intervals. The SEC Company Concept API supplied standard diluted-EPS
facts with explicit period, filing date and accession metadata. A deterministic builder kept only
approximately single-quarter 10-Q contexts, selected the earliest filing for repeated comparative
facts and required the prior filing to predate the target quarter. A pre-adoption audit found split
and retrospective recast artifacts, so the final builder also requires the target filing's prior
comparator to match the originally filed value within the larger of $0.01 or 1%. It removed 139
incomparable pairs and six without a comparator, leaving 2,321 rows across 88 companies through
2025. A cache-only rebuild was byte-identical at SHA-256
`d192f63d6008677a4cf69f2d4af0b5eae27125a256629e02849e0b9f223fa307`.

The split was fixed at 2015–2019 train, 2020–2021 development and a one-time 2022–2023 test. To avoid
assuming perfect model direction, interval selection centered each row on the production fallback
point used when no positive signal is accepted. Development selected half-width
`max(2.75, 1.15 * abs(prior EPS))`, with exactly 90.0% coverage. On the 444-row test,
coverage rose from 25.23% to 93.69%, cutting absolute calibration error from 64.77 to 3.69 percentage
points. The mean full width rose from 0.753 to 8.438 USD/share; this is material and recorded because the
official composite has no width penalty.

The split/recast audit was introduced after inspecting that 2022–2023 test, so the test is not
described as untouched. The extraction rule and candidate were frozen before reading a separate
457-row 2024–2025 confirmation set. Confirmation coverage rose from 24.95% to 95.84%, reducing
absolute calibration error from 65.05 to 5.84 percentage points; mean full width was 6.746
USD/share. No parameter changed after that read.

Only tasks at or after 2022-01-01 receive the fitted rule. Earlier cutoffs retain the preceding
interval. On the retired six-row public diagnostic, coverage moved from 50% to 100% and unit
composite from 0.58 to 0.67. Across all eleven units, mean pre-gate composite moved from 0.1878 to
0.1959. Exactly six `interval` objects changed; every point, label and claim was identical, so the
existing official two-member NLI evidence result remains applicable. All 54 tests passed, and fresh
model-free plus saved-signal outputs both passed official smoke for 11/11 units and 78/78 rows.
Structured comparison SHA-256: `147f34b16e9ff57809163c6330535afae498a5e2a8c2e7bab4e3b340275202ea`.

The direct GitHub HEAD check timed out during this cycle. The last verified official Track 4 and
shared-toolkit commits therefore remain the recorded snapshots; the installed official toolkit is
still `qfbench2-common==2.4.4`. Current official web pages showed no scoring or runtime-boundary
change relevant to this experiment.

### EPS YoY recent-delta point v1 — rejected

The accepted interval change left point accuracy untouched, so a second experiment asked whether the
most recent filed quarter's YoY EPS delta predicts the target quarter. The feature builder required
both the recent quarter and its comparable prior-year fact to be available before a seven-day
pre-target-filing proxy cutoff. This yielded 1,509 rows from the same SEC panel. Development selected
`prior target-quarter EPS + 0.25 * recent YoY delta` from four fixed damping coefficients.

The candidate improved the inspected 2022–2023 subset: MAE fell from 1.7148 to 1.5564 USD/share and
direction accuracy rose from 41.52% to 66.09%. It failed the locked 299-row 2024–2025 confirmation:
direction accuracy rose from 38.46% to 61.20%, but MAE worsened from 1.2519 to 1.3073 and RMSE from
5.9071 to 6.4416. The predeclared rule required both MAE and direction to improve, so no calculator
change was made. The result also shows that direction persistence alone is insufficient for numeric
EPS sizing. Structured report SHA-256:
`c1dd14c000ff5be8cc6ad192e2d2acece4a0a0dd4ffb32e5b943a3586598ef66`.

### FOMC cutoff reaction and momentum v1 — rejected

Official Federal Reserve research confirms that FOMC communication moves the Treasury curve, with
the strongest immediate trading response generally at shorter maturities, while New York Fed work
finds that long-horizon yield reactions can contain a distinct market-confidence shock. Those results
motivated a cutoff-safe test of the first complete post-decision close and trailing 10/20-trading-day
yield momentum. The candidate used only official Treasury closes available by the public tasks'
next-day cutoff pattern.

The fixed historical split contained 102 training-era events through 2015, 24 development events in
2016–2018 and 26 untouched test events in 2019–2021. Development selected a full reversal of the
cutoff-day yield move. It reduced development MAE from the better production baseline's 14.9375 to
14.6528 bps. On held-out test, however, candidate MAE was 14.4679 bps versus 14.2244 for the
zero-change baseline, a 1.71% regression. Direction accuracy improved from the better directional
baseline's 13.46% to 44.23%, but the predeclared rule required at least 2% MAE improvement as well.
The candidate was rejected and `rates.py` was unchanged. Structured report SHA-256:
`e7cc65f36c64f62a97b98fb1d9d83f460b4089b7fdc5cf9c0ad65436fee027e3`.

### FOMC policy-scaled interval v1 — rejected

The official Track 4 main snapshot remains `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`,
the shared-toolkit main snapshot remains `95a0de3d9a814f3883c151b7efdbbcf579139244`, and
installed `qfbench2-common==2.4.4` still matches the Track 4 pin. Current official pages showed no
change to the 25-request, 4,000-output-token, 600-second or restricted-network boundaries.

A new official-source panel adds 37 completed FOMC inter-meeting events from 2022 through the July
2026 meeting. The two retired public events were excluded from both selection and confirmation. On
30 development events in 2022-2025, the fixed 50 bps half-width covered 85.0% of 180 rows. A grid
selected `50 + 0.25 * abs(policy change bps)`, which covered 88.89% with mean full width 109.58 bps,
versus 100 bps for the baseline. The candidate was locked before reading five completed 2026 events.

All five 2026 confirmation meetings held the target range unchanged, so candidate and baseline were
identical: both covered 100% of 30 rows and had 0.10 calibration loss. The predeclared rule required
strictly lower confirmation loss. The candidate was therefore rejected and `rates.py` was not
changed. Dataset SHA-256: `d51d0b231c0df5312dae367e802aa445b06f921d13ba9e0a03e1b710162b4580`. Structured report SHA-256: `4d5d2abed8d7d445e643721fc3f16d1b6e0dd959053ac7f8e6c61ba620e83783`.

### Public Agenthon repositories and evidence-ID probe — deferred, candidate rejected

Two public participant implementations were inspected. `dungcao06/optivex-t4-agent` is MIT-licensed
and wraps the official strong-RAG baseline with a single-prompt “evidence council”: predictor,
evidence reviewer, calibration reviewer and admission guard. It still asks the model for final
per-entity forecasts and does not publish outcome-based calibration evidence. Our complete-roster
and batch-of-three direct/hybrid experiments already reduced predictive quality, so that prompt
architecture was documented but not repeated.

The MIT-licensed `youxuanxue/track4-analysis-public` fork contains a much larger evaluation harness
and a generic evidence-ID mechanism. Its PR 4 reports that a bundled change using Qwen2.5-7B,
strict JSON schema, evidence IDs and retrieval filters moved accepted model rows from 28/78 to
78/78 and reduced elapsed time from 1,200.06 to 500.44 seconds. The raw outputs are outside the
repository, the change bundles several mechanisms, and the commit history includes public-unit
tuning and former output locks. We therefore treated it as a hypothesis source, not independent
proof, and copied no task-specific predictions or constants.

An evidence-ID-only toggle was implemented locally: the model selected `E1`, `E2`, and so on from
the already scoped retrieval packet, while code restored the exact document text and span. Forty-two
focused tests passed, including fail-closed unknown IDs. A free exact-family Nemotron probe completed
one paired EPS case: both paths stayed neutral with the same final prediction, while completion
tokens fell from 213 to 156. In credit, the legacy path had one malformed JSON response and one
exact-quote rejection. The candidate's completed subset had no quote rejection, but two of its
three calls received HTTP 429 after the provider's free daily allowance was exhausted. Both rates
runs then received 429. These are asymmetric samples and cannot satisfy the preregistered cross-type
rule.

The candidate was rolled back and is not part of production. The structured report is
`evaluation/reports/public-repo-evidence-id-probe-v1.json`. No local language model was downloaded
or run; after the user's compute preference was clarified, the temporary inference-binary download
was deleted. Future model experiments use remote free capacity or the official House API unless the
user explicitly changes that preference.

References: <https://github.com/dungcao06/optivex-t4-agent>,
<https://github.com/youxuanxue/track4-analysis-public>, and
<https://github.com/youxuanxue/track4-analysis-public/pull/4>.

The official Track 4 main commit remains `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`.
New issue 16 documents a separate macOS image-layer failure: `com.apple.provenance` in a layer can
make organizer Linux workers fail to unpack an image. Our GHCR workflow builds on `ubuntu-latest`
from a fresh checkout and does not create a macOS tar layer, so no pipeline change was needed.

### Safe `corpus_ref` subtree scope — accepted

The official snapshot and open issues were checked again on 2026-09-28 and were unchanged. Track 4
`docs/CATEGORIES.md` says some families give each entity its own subtree, and the strong-baseline
documentation says retrieval should use `corpus_ref` to scope each row. The public authoring guide
and all eleven public units use a flat corpus, so this hidden-shape requirement had not been tested.
Our index used a root-only `glob("*.json")` and ignored `corpus_ref` entirely.

The candidate recursively indexes cutoff-safe JSON documents, records their paths relative to the
mounted corpus, and intersects every existing family scope with a validated `corpus_ref`. Root
references retain shared-corpus behavior. Subtree matching uses complete path components, so
`entity-a` cannot match `entity-a-old`; parent traversal, absolute or backslash paths and duplicate
document IDs fail closed.

In the synthetic A/B, the old index loaded zero documents from three nested entity directories;
the candidate loaded all three pre-cutoff documents and exposed exactly one to the requested
entity, while excluding a prefix collision and a post-cutoff distractor. Four of four unsafe path
cases were rejected. All 61 tests passed. Across the eleven public units, both implementations
exited successfully and all eleven candidate answers were byte-identical to the current committed
baseline. Those exact files therefore retain the baseline's already recorded 11/11 smoke result.
The current shell lacks the Python 3.13 `qfbench2-smoke` executable, so no fresh smoke run is
claimed. The candidate was accepted as a shared retrieval and evidence-isolation fix; it makes no
public predictive-quality claim. Structured report:
`evaluation/reports/corpus-ref-scope-v1.json`.

References: <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/CATEGORIES.md>,
<https://github.com/Agenthon-2026/track4-analysis-public/blob/main/baselines/README.md>, and
<https://github.com/Agenthon-2026/track4-analysis-public/blob/main/docs/AUTHORING-GUIDE.md>.

### Generic scalar feature visibility — accepted

The official Track 4 description says entity tables can mix numeric, categorical and text columns,
and warns that most hidden families have no public counterpart. Our known-family projections
correctly used explicit white lists, but the generic projection preserved only identity and numeric
fields. An unknown task's rating bucket, regime, status flag or short text feature was therefore
absent from both the House-model packet and lexical retrieval query.

The candidate preserves all JSON scalar types for generic rows while leaving every known-family
white list unchanged. It excludes nested values and `corpus_ref`, rejects non-finite numbers, and
bounds the packet at 64 scalar fields, 1,000 characters per string and 6,000 string characters in
total. Identity fields are prioritized. The same bounded projection supplies the generic BM25
query, so a previously unknown categorical value can select its matching evidence.

A deterministic three-case audit covered unseen classification, regression and ranking schemas.
The old packet exposed 0/3 custom categorical fields and selected the correct top document in 1/3
cases; the candidate exposed 3/3 and retrieved 3/3. Boolean features were preserved, a 1,200-character
field was clipped to 1,000, nested values were excluded and an 80-text-field adversary stopped at
the 6,000-character total. All 65 tests passed. Final no-model A/B answers were byte-identical for
11/11 public units, so their existing schema, smoke and NLI evidence remains unchanged. No model
request or prompt instruction was added.

This is an input-reachability and retrieval improvement, not a predictive-accuracy claim. The
candidate was accepted because it aligns the generic path with the official mixed-column contract
and passes all boundedness and non-regression gates. Reports:
`evaluation/reports/generic-scalar-projection-v1.json` and
`evaluation/reports/generic-scalar-public-ab-v1.json`.

Reference: <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/README.md>.

### Generic typed label-role mapping — accepted

The official Track 4 and shared-toolkit snapshots remained unchanged. A newly indexed MIT-licensed
participant repository, `wangzgui/agenthon-t4-baseline-2026`, adapts the official strong-RAG
scaffold: it asks the model to return one allowed label and falls back to the first label when the
response is invalid. `dungcao06/optivex-t4-agent` follows the same direct-output shape. We already
tested and rejected a separate direct-label call twice because malformed JSON and provider
instability produced 6–13 valid rows out of 13. The public implementations were therefore used as
architecture comparisons, not copied.

The alternative candidate retains the validated generic `directional_signal` and interprets label
semantics deterministically from the task schema. It recognizes unambiguous role words and
event-target negation, then scans a bounded 8,000-character prompt for explicit clauses pairing a
label with rise, stable or fall semantics. If no unique role is established, the preceding allowed
label fallback remains. No prompt sent to the House model changed and no request was added.

On the five-schema/13-row set from the rejected direct-label experiments, the prior mapper scored
8/13 and the candidate 13/13. A separate synthetic confirmation set used eight rows across three
opaque schemas (`zeta/eta/theta`, color labels and `class_a/class_b`) whose meaning appeared only in
the prompt; the candidate scored 8/8. All 102 permutations of allowed-label order preserved the
expected result, and an ambiguous prompt returned an allowed deterministic fallback. These are
schema robustness checks, not real hidden outcomes.

All 69 tests passed. Fresh no-model public answers were byte-identical for 11/11 units, preserving
their existing schema, smoke and local official-NLI evidence. The candidate was accepted as a
typed-intermediate reliability improvement. It cannot help when the direction extractor itself is
wrong or the task describes label semantics indirectly. Reports:
`evaluation/reports/generic-label-role-mapping-v1.json` and
`evaluation/reports/generic-label-role-public-ab-v1.json`.

References: <https://github.com/wangzgui/agenthon-t4-baseline-2026> and
<https://github.com/dungcao06/optivex-t4-agent>.

### Anchored family routing — accepted

The official repositories and `v2.4.4` tag remained unchanged. Official documentation again states
that most hidden families have no public counterpart. The official minimal baseline handles only a
narrow EPS rule, while the newly inspected MIT `wangzgui/agenthon-t4-baseline-2026` and the earlier
MIT Optivex agent send the task directly to a strong-RAG model and provide no reusable specialist
router. No external routing code was copied.

Our router previously used raw substring tests. A seven-case collision audit showed seven false
specialist routes: `inventory_position_rank`, `auction_price_change`,
`analyst_revision_probability`, `cotton_yield_rank`, `credit_eventual_return`,
`rate_curveball_score` and `positioning_of_inventory` all bypassed generic handling. That could
drop unknown fields, select an unrelated corpus scope and execute the wrong calculator.

The candidate matches complete token sequences in `family` and `target.name`. Ten unique public
family/target pairs and ten anchored variants retained their expected specialist, while all seven
collisions moved to generic. All 71 tests passed. A fresh final-candidate A/B produced byte-identical
answers on 11/11 public units, so existing smoke and local official-NLI evidence is unchanged. No
model request, prompt or formula changed.

The candidate was accepted as an unknown-family isolation improvement. It deliberately prefers a
generic fallback when a genuinely related hidden task uses an unpublished synonym; the limitation
is recorded rather than offset with more loose keywords. Reports:
`evaluation/reports/router-signature-collision-v1.json` and
`evaluation/reports/router-signature-public-ab-v1.json`.

References: <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/README.md>,
<https://github.com/wangzgui/agenthon-t4-baseline-2026>, and
<https://github.com/dungcao06/optivex-t4-agent>.

### Strict model-intermediate scalar types — accepted

The official Track 4 and shared-toolkit main commits, the `v2.4.4` toolkit tag and the five open
Track 4 issues were unchanged on 2026-09-28. The submission guide still requires a complete output
for every unit and counts malformed or incomplete output as a participant failure. No new rule or
House development endpoint was published.

A typed-intermediate audit found three related Python coercion failures. JSON `true` was interpreted
as the integer signal level `+2`; JSON `true` and `false` could bind batch rows to item IDs 1 and 0;
and the strings `NaN` and `Infinity` passed numeric parameter parsing. A non-finite numeric signal
could also raise while being rounded. These values violate the prompt's integer and finite-number
contracts and can turn malformed small-model output into a directional forecast, a cross-entity
assignment or a non-finite calculator input.

The accepted candidate treats boolean and non-finite signal levels as neutral, requires item IDs to
be integers but not booleans, and rejects non-finite numeric parameters. It preserves finite numeric
strings, named signal levels, integer clamping, valid reordered batches and entity-ID fallback.
Five fault-injection checks changed from unsafe acceptance or exception risk to fail-closed behavior.
All 75 tests passed. Fresh candidate answers were byte-identical to the baseline for 11/11 public
units and all 78 rows; all 11 passed the packaged analysis schema and the non-rankable official
smoke verifier. The change adds no prompt tokens or model calls and makes no predictive-accuracy
claim. Report: `evaluation/reports/typed-intermediate-scalar-validation-v1.json`.

References: <https://www.agenthon.net/guides/submission-format/>,
<https://github.com/Agenthon-2026/track4-analysis-public>, and
<https://github.com/Agenthon-2026/Agenthon2026-public>.

### Strict presence-aware batch identities — accepted

The preceding consistency check rejected two valid identifiers when they pointed to different
entities, but it still accepted a row when one identifier was valid and the other was present but
foreign, mistyped or out of range. For example, `{item_id: 0, entity_id: "FOREIGN"}` was assigned
to item 0 because the unknown entity ID was silently ignored. This can cross entity boundaries when
several entities share a macro or industry document.

The candidate validates every identity field that the model actually returned. Any provided
`item_id` must be a non-boolean integer in the current batch, and any provided `entity_id` must be a
string in the current batch. If both are valid they must agree. If one field is absent, the other
valid field still recovers the row, preserving the existing partial-output fallback.

All four provided-invalid fault cases were accepted before and rejected after. Item-only and
entity-only recovery remained valid. Seventeen saved batch rows from the free Nemotron run across
credit, EPS YoY and post-earnings families remained 17/17 accepted because they contained correctly
typed, matching identifiers. All 77 tests passed; the 11 public answers and 78 rows were
byte-identical, schema-valid and 11/11 smoke-admissible. No model request or prompt token was added.

The official public baselines process one entity at a time. GitHub code search found no joint
`item_id`/`entity_id` mapper in the inspected official repository or the two previously reviewed
participant repositories, so no external implementation was copied. Report:
`evaluation/reports/strict-batch-identity-presence-v1.json`.

References: <https://github.com/Agenthon-2026/track4-analysis-public>,
<https://github.com/wangzgui/agenthon-t4-baseline-2026>, and
<https://github.com/dungcao06/optivex-t4-agent>.

### Pin the submission-image runner — accepted

The successful image workflow emitted GitHub's migration annotation: the `ubuntu-latest` label will
begin moving from Ubuntu 24.04 to Ubuntu 26.04 on 2026-10-19. GitHub's runner-image announcement
warns that workflows depending on system libraries, compilers or prebuilt binaries may be affected
and gives `ubuntu-24.04` as the rollback label. Agenthon's joint Final + Verification phase continues
through 2026-10-25, so the floating-label migration overlaps the period in which the final image may
need to be rebuilt and verified.

The candidate changes only the image workflow runner from `ubuntu-latest` to `ubuntu-24.04`. It does
not change the Dockerfile, agent code, predictions, model requests or formal image platform, which
remains Linux/amd64. Actions run `36359823626` confirmed `Image: ubuntu-24.04`, passed all 77 tests,
built and pushed the image, and started its `analyze --help` command. The resulting digest
`sha256:34f936e0704ac8119ecfab65abb342fa2ed871bf3491f5654b6466add5851c50` returned HTTP 200 through
an anonymous GHCR manifest request, whose registry digest matched exactly. The candidate was
accepted as a submission-stability improvement. Report:
`evaluation/reports/pinned-github-runner-v1.json`.

References: <https://github.com/actions/runner-images/issues/14748> and
<https://www.agenthon.net/guides/submission-format/>.

### Context-length errors remain batch-local — accepted

The official Track 4 and shared-toolkit commits, `v2.4.4` tag and open issues were unchanged. The
organizers still publish no authoritative House serving input ceiling. Reconstructing the current
production prompts for all public units produced 12 model requests ranging from 4,410 to 41,167
characters, with a 39,485.5-character median. The official strong-RAG baseline retrieves ten chunks
per entity, compared with our eight. These observations do not justify an arbitrary fixed character
cap that might remove task instructions or decisive evidence.

The audit instead exposed a concrete recovery failure. The LLM adapter treated every HTTP 400 as a
global, non-retriable configuration error. A single batch returning
`context_length_exceeded` therefore disabled every later batch, even when a later batch was shorter.
The candidate recognizes a bounded set of context-length and token-limit markers, does not retry the
same oversized request, and leaves the cross-batch circuit available for subsequent work.

In fault injection, the baseline made one network call, opened its circuit and suppressed the later
valid batch. The candidate let the first batch fall back and completed the later batch on the second
call. Unknown HTTP 400 responses and 401/403 authorization errors still fail closed immediately;
four consecutive context errors still open the shared circuit. All 80 tests passed. The 11 public
answers were byte-identical for all 78 rows, 11/11 schema-valid and 11/11 smoke-admissible. Normal
execution adds no request or prompt token. Report:
`evaluation/reports/context-length-local-recovery-v1.json`.

References: <https://github.com/Agenthon-2026/Agenthon2026-public>,
<https://github.com/Agenthon-2026/track4-analysis-public>, and
<https://github.com/Agenthon-2026/track4-analysis-public/tree/main/baselines/strong_rag_baseline>.

### Unambiguous JSON framing recovery — accepted

The shared model parser previously sliced from the first `{` to the last `}` and called
`json.loads` once. A single valid response therefore failed when thinking text contained an invalid
brace note before it or explanatory text contained one after it. Conversely, an array containing a
dictionary was silently accepted by extracting its nested object even though the required top level
was an object. The official strong-RAG exemplar uses a similarly greedy brace expression; GitHub
search found no reusable balanced parser in the two previously reviewed participant repositories.

The candidate walks complete JSON containers with `JSONDecoder.raw_decode`. A decoded container is
skipped as a unit, so nested dictionaries and braces inside strings are not mistaken for separate
answers. Exactly one top-level dictionary is accepted. Two valid dictionaries remain ambiguous and
are rejected; arrays, truncation and prose without an object are also rejected.

Both reproducible invalid-brace framing cases improved from 0/2 to 2/2 and the full LLM integration
accepted the recovered object in one request. Four strict rejection shapes remained fail-closed.
Historical reports contain 17 “model returned content without one JSON object” entries across eight
reports, but the raw unparsed text was not retained, so this is frequency evidence rather than a
claim that all 17 failures are fixed. All 83 tests passed; all 11 public answers were byte-identical,
schema-valid and smoke-admissible. Report:
`evaluation/reports/unambiguous-json-framing-v1.json`.

References: <https://github.com/Agenthon-2026/track4-analysis-public/tree/main/baselines/strong_rag_baseline>
and <https://docs.python.org/3/library/json.html#json.JSONDecoder.raw_decode>.

### Deadline-bounded `Retry-After` recovery — accepted

The official Track 4 and shared-toolkit main commits, the `v2.4.4` tag and the five open Track 4
issues were unchanged. Historical project reports contain five HTTP 429 responses from the free
Nemotron evidence-ID experiment. The model adapter nominally slept one second between attempts, but
the OpenRouter JSON-mode branch removed `response_format` and immediately continued, so a 429 was
retried with no wait and with an unrelated request-shape change.

RFC 9110 defines `Retry-After` as either non-negative delay seconds or an HTTP date, and RFC 6585
allows it on 429 responses. OpenRouter's own documentation describes 429 as rate limiting and tells
clients to wait before retrying. The candidate parses both standard forms. It waits only when the
server delay fits a configurable 30-second default ceiling and leaves one second inside the model
deadline. A longer delay falls back for that batch instead of violating the server's requested
minimum; a missing or malformed header retains the prior one-second bound. JSON mode remains on the
retry.

In deterministic A/B fault injection, both versions recovered on call two, but the baseline slept
zero seconds and sent JSON mode on only one of two attempts. The candidate slept the requested
three seconds and kept JSON mode on both attempts. Separate checks proved that a 60-second request
under a five-second cap and a five-second request with only two deadline seconds remaining both
made one call, slept zero seconds and fell back. No remote model was called.

All 87 tests passed. A clean `git archive HEAD` baseline and the candidate produced byte-identical
answers for all 11 public units and 78 rows on the same interpreter, and all 11 candidate answers
validated against `analysis.schema.json` fetched directly from toolkit tag `v2.4.4`. The local
shell is Python 3.11 while the official scorer requires Python 3.13, so no fresh local
`qfbench2-smoke` run is claimed; the candidate does not touch no-model output and preserves the
current baseline's prior 11/11 smoke evidence. Structured report:
`evaluation/reports/retry-after-rate-limit-v1.json`.

References: <https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after>,
<https://www.rfc-editor.org/rfc/rfc6585.html#section-4>, and
<https://openrouter.ai/docs/guides/overview/auth/byok>.

### Bank EPS delta damping — rejected

After the shared fault-recovery audit, the next family-level candidate tested whether the bank EPS
calculator should damp the most recently filed quarterly YoY EPS delta instead of carrying it
fully into the target quarter. Eight public-unit banks supplied 242 comparable SEC quarterly pairs;
158 also had a distinct, cutoff-safe recent-quarter feature. The time split contained 69 train, 28
development, 29 test and 32 locked 2024–2025 confirmation rows.

The candidate grid was `beta = 0, 0.1, 0.25, 0.5, 0.75, 1.0`, where production already uses 1.0.
Development selected 1.0 itself: its growth-percentage MAE was 80.90%, versus 81.20% at 0.75,
99.15% at 0.5 and worse values for stronger damping. Every positive beta had the same 75.0%
direction accuracy. Because the selected candidate was identical to production, the preregistered
requirement for a distinct candidate failed before confirmation could support a change.

No production code changed. The experiment is recorded so a future run does not repeat this beta
grid without a new feature or hypothesis. Script:
`evaluation/experiments/bank_eps_delta_probe.py`. Structured report:
`evaluation/reports/bank-eps-delta-damping-v1.json`.

Source: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>.

### Bank EPS interval calibration — statistically positive, production candidate rejected

The 2026-09-28 preflight found no change to either official main commit or the five open Track 4
issues; the current toolkit tag remains `v2.4.4`. The submission guide still requires an immutable
Linux/amd64 image digest and anonymous pullability, and confirms that hidden reference answers
remain private.

The same cutoff-safe 158-row bank panel tested the existing
`max(20, 0.75 × |point|)` 90% half-width against a fixed grid of seven floors and five point
multipliers. Development selected `max(100, 1.0 × |point|)`. It improved test calibration loss from
0.176 to 0.100 and locked 2024–2025 confirmation loss from 0.244 to 0.100. Confirmation coverage
moved from 65.6% to 100%, while mean full width rose from 49.1 to 200.1 growth-percentage points.

The statistical result alone does not satisfy the project acceptance rule. The saved official
two-model NLI audit passes the public bank unit at 7/8 entities, only one entity above the 0.8 gate.
Changing every interval changes every prediction-bound NLI hypothesis, so the saved result cannot
validate the candidate. A fresh official-model run is a heavy local NLI job, which the current goal
forbids without explicit user approval. The production candidate is therefore rejected/deferred;
`bank_eps.py` remains unchanged.

Script: `evaluation/experiments/bank_eps_interval_probe.py`. Report:
`evaluation/reports/bank-eps-interval-calibration-v1.json`.

### Optional usage telemetry isolation — accepted

The next L2 response-boundary audit compared the production client with the official strong-RAG
client. The official client reads the assistant message from `choices` and does not make prediction
acceptance depend on `usage`. The only other public Track 4 repository found in the current GitHub
search, `dungcao06/optivex-t4-agent`, delegates its HTTP path to that official scaffold. No code was
copied.

Our client instead converted usage fields before reading valid assistant content. In deterministic
fault injection, a valid JSON reply with string-valued `usage` failed twice and fell back; a valid
reply with `prompt_tokens: "unknown"` required a second call. The candidate treats usage as optional
telemetry. Both replies now succeed in one call, invalid counters contribute zero, and an otherwise
valid completion count is retained. Normal integer usage is unchanged.

On Python 3.13, a clean archive of commit `2b08c40` and the candidate produced byte-identical
answers for all 11 public units and 78 rows. Every candidate output passed the installed official
`qfbench2-common==2.4.4` smoke verifier. The full test suite passed without a remote model call.
Report: `evaluation/reports/optional-usage-telemetry-v1.json`.

References:

- <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/baselines/strong_rag_baseline/client.py>
- <https://github.com/dungcao06/optivex-t4-agent>

### Structural router usable-value guard — accepted

The first structural fallback candidate treated a field name as present even when every value was
`null`, blank or non-finite. On a renamed hidden task that could select a specialist whose required
inputs were unavailable and apply its narrower document scope. The accepted guard now requires a
usable value for every exact signature field in every entity, and a usable date-prefixed field per
required prefix and entity. Zero remains valid.

All 9/9 complete renamed structures retained their specialist route, while 9/9 new null, blank,
NaN, infinity and empty-prefix controls stayed generic. Python 3.13 passed 101 tests. A clean
archive of baseline `cde2950` and the candidate produced byte-identical answers for all 11 public
units and 78 rows with zero local validation errors. Those exact baseline bytes passed the toolkit
2.4.4 smoke verifier earlier in the same run, so the candidate preserves the 11/11 smoke result
without another scorer installation. No model request or prompt changed. Script:
`evaluation/experiments/structural_router_value_guard.py`. Report:
`evaluation/reports/structural-router-value-guard-v1.json`.

### Generic schema-name query expansion — rejected

A deterministic retrieval screen tested whether retaining exact JSON schema tokens while adding
camelCase, snake_case and hyphen-separated natural-language components was sufficient to recover
evidence for unseen task schemas. Four cases covered three field-name styles and a camelCase target
name. Each correct document used the expanded natural-language phrase; a distractor contained the
existing generic rubric terms.

The baseline and candidate both retrieved 0/4 correct top-one documents. Exact legacy tokens were
preserved in 4/4 cases and the 64-field stress query grew by 3.34x, within the pre-registered 4x
limit, but the eight broad generic rubric terms continued to dominate the BM25 score. The candidate
failed its primary 4/4 retrieval gate and was fully rolled back before public or model tests. A
separate experiment may test generic rubric selection or weighting; that behavior was not changed
after seeing this result. Script: `evaluation/experiments/generic_schema_query_expansion.py`.
Report: `evaluation/reports/generic-schema-query-expansion-v1.json`.

### Generic semantic-schema query priority — accepted

The follow-up isolated the root cause found by the rejected expansion-only screen. Exact schema
identifiers are still preserved, and semantic camelCase, snake_case or hyphenated identifiers add
at most eight natural-language components. When those terms exist and the router has no domain
rubric, the broad generic fallback terms are omitted. Opaque schemas such as `x1/y2/z3` retain the
legacy query byte-for-byte, including when they use `unseen_family` and `opaqueTarget` placeholders;
known-family queries also remain byte-for-byte unchanged.

The same four pre-registered retrieval cases improved from 0/4 correct top-one documents to 4/4.
Exact schema tokens remained present in all four, opaque and known queries were identical, and a
64-field stress query grew by 3.27x versus the 4x cap. Python 3.13 passed 104 tests. A clean archive
of baseline `64fe8e0` and the candidate produced byte-identical answers for all 11 public units and
78 rows with zero validation errors; those exact answer bytes retain the recorded 11/11 toolkit
2.4.4 smoke result. The query expansion is retrieval-only and adds no model prompt tokens or calls.
Script: `evaluation/experiments/generic_schema_query_priority.py`. Report:
`evaluation/reports/generic-schema-query-priority-v1.json`.

The official snapshot remained shared main `95a0de3`, Track 4 main `7b2bce1`, toolkit `v2.4.4`
and open Track 4 issues 1, 2, 13, 14 and 16. The currently updated public repositories remained
`wangzgui/agenthon-t4-baseline-2026` and `dungcao06/optivex-t4-agent`; neither supplied this bounded
generic query policy.

### Router-aligned query rubrics — accepted

After calculator routing and document scope were aligned, query rubric selection still used the
discarded loose substring rules. All seven existing collision cases therefore routed generic but
injected an unrelated specialist vocabulary: examples included COT terms for
`inventory_position_rank`, credit terms for `credit_eventual_return`, and FOMC terms for
`rate_curveball_score`.

The accepted candidate maps rubrics from the same `task_family_spec` result used by prediction and
scope. Specialist injection fell from 7/7 collision cases to 0/7. All 20 published and anchored
known queries remained byte-identical, and all 9 renamed complete structural signatures received
the rubric matching their recovered specialist. Python 3.13 passed 111 tests. A clean archive of
baseline `3a37e44` and the candidate produced byte-identical answers for all 11 public units and 78
rows with zero validation errors, preserving the recorded 11/11 toolkit 2.4.4 smoke result. No
model request or prompt token was added. Script:
`evaluation/experiments/query_rubric_router_alignment.py`. Report:
`evaluation/reports/query-rubric-router-alignment-v1.json`.

### BM25 query-term deduplication — rejected before code

The MIT-licensed public strong-RAG retriever from
`wangzgui/agenthon-t4-baseline-2026` scores a set of query terms, while production scores every
occurrence and therefore weights repeated schema/rubric words more heavily. A read-only screen
compared those semantics over all 78 public rows before changing production.

Fifty-two rows contained duplicate query terms. Deduplication changed 27/78 top-one retrievals and
46/78 top-three lists. That is broad citation churn, not a bounded engineering correction. No
independent relevance label or lightweight NLI metric proves the changed passages are better, and
fresh heavy local NLI is prohibited by the active goal. The candidate was rejected before code;
production retrieval and every answer remain unchanged. Script:
`evaluation/experiments/bm25_query_dedup_screen.py`. Report:
`evaluation/reports/bm25-query-dedup-screen-v1.json`.

### Node.js 24 GitHub Actions pinning — accepted

Run `36364759306` succeeded but GitHub reported that checkout, Python setup and all three Docker
actions still targeted retired Node.js 20 and were being forced onto Node.js 24. GitHub's migration
guidance tells workflow users to update to action versions that run on Node.js 24. Each action had
such a release, so the candidate replaced floating old major tags with the full commit SHA of the
current release and retained a version comment.

Candidate run `36368888920` passed all 88 tests, built and pushed the Linux/amd64 image, and passed
the container command-contract smoke. The Node.js 20 warning count fell from one to zero. The
resulting digest `sha256:42af4b17e5977b62cd789303bad1fe6afcb668a4d6717684213e7cb8eac9b846`
returned HTTP 200 through an anonymous GHCR manifest request and matched the registry digest. The
agent, Dockerfile and predictions did not change.

Report: `evaluation/reports/node24-actions-pinning-v1.json`.

Reference:
<https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/>.

### Full official request allowance for large rosters — accepted

The official runtime still allows 25 admitted generation requests per unit and has no cumulative
token allowance. Our client nevertheless defaulted to 18 calls after an earlier reliability pass;
the repository history contained no rule or experiment supporting that lower number. The official
strong-RAG baseline was also inspected: it retries per entity but has no participant-side global
request guard, so its implementation was not copied. Our existing shared `LLM` counter remains the
appropriate enforcement point.

With batch size three, deterministic response simulation showed that the 18-call default enhanced
only 54 of 60 or 75 rows on a clean route. One transient malformed reply reduced that to 51. Using
the existing hard maximum of 25 enhanced 60/60 rows after one retry and 75/75 on a clean route. A
78-row case made exactly 25 calls and fell back for the last three rows; no 26th network request was
made. Persistent malformed replies still opened the circuit after four calls under both caps.

On Python 3.13, a clean archive of commit `17d1d45` and the candidate produced byte-identical
answers for all 11 public units and 78 rows, and every candidate answer passed
`qfbench2-common==2.4.4` smoke. Both Python 3.11 and 3.13 test runs passed 89 tests. No remote or
local language model was run.

Script: `evaluation/experiments/request_budget_roster_probe.py`. Report:
`evaluation/reports/official-request-budget-roster-v1.json`.

References:

- <https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/DEVELOPMENT-RUNTIME.md#house-request-allowance>
- <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/baselines/strong_rag_baseline/config.py>

### Macro revision stage matching — rejected

The official state check on 2026-09-28 found Track 4 main at `7b2bce1`, shared toolkit main at
`95a0de3`, toolkit tag `v2.4.4`, and the same five open Track 4 issues (1, 2, 13, 14, 16). The
published runtime remains 25 admitted House requests, 4,000 output tokens per request, no cumulative
token allowance, 600 seconds, and restricted network. ALFRED's official API documentation confirms
that a vintage date represents a release date on which a series changed; the experiment used its
public archival graph CSV to avoid requiring a runtime API.

The tested hypothesis was that the next revision should use the median of historical changes at the
same revision age, rather than the current calculator's median over every revision stage. A
cutoff-safe panel of the six published macro series compared both rules on identical rows. The
candidate improved test accuracy from 0.5448 to 0.5597 and confirmation accuracy from 0.4778 to
0.5468, but development accuracy fell from 0.5122 to 0.4976. This violates the pre-registered rule
that direction accuracy be non-inferior on development, test, and confirmation. It is rejected;
`macro_revision.py` remains unchanged and the retired public outcome was not used to rescue it.

Scripts: `evaluation/experiments/build_macro_revision_panel.py` and
`evaluation/experiments/macro_revision_age_matched.py`. Report:
`evaluation/reports/macro-revision-age-matched-v1.json`.

References:

- <https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html>
- <https://fred.stlouisfed.org/docs/api/fred/overview.html>
- <https://github.com/Agenthon-2026/track4-analysis-public>

### Explicit-only development traces — accepted

The official state check on 2026-09-28 again found Track 4 main at `7b2bce1`, shared toolkit main at
`95a0de3`, toolkit tag `v2.4.4`, and the same five open Track 4 issues (1, 2, 13, 14, 16). The
official Development runtime caps the complete `/output` tree at 64 MiB and requires only the
declared answer artifact. Two current MIT-licensed public Track 4 implementations were also
inspected: `dungcao06/optivex-t4-agent` delegates to the official strong-RAG CLI, and
`wangzgui/agenthon-t4-baseline-2026` writes its answer path without a default row-trace tree. No
code was copied.

Our formal CLI previously wrote `trace/rows.json` beside every answer even when `--trace-dir` was
omitted. That file repeats retrieved passages and model data per entity and had no byte ceiling. A
2,000-row deterministic probe produced a 2,043,320-byte answer plus 8,807,323 bytes of trace, a
4.31x trace-to-answer ratio. The candidate makes the existing trace option literal: the formal
default writes only `answer.json`, while an explicit `--trace-dir` retains the complete prior trace
schema for development runs.

A clean archive of commit `ed2f345` and the candidate produced byte-identical answers for all 11
public units. Candidate outputs had no extra files, all 11 passed the toolkit 2.4.4 schema and smoke
checks, and the test suite passed 91 tests. The change makes no model request and changes no
prediction, citation, prompt or calculator. Report:
`evaluation/reports/explicit-trace-output-v1.json`.

References:

- <https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/DEVELOPMENT-RUNTIME.md#container-limits>
- <https://github.com/dungcao06/optivex-t4-agent>
- <https://github.com/wangzgui/agenthon-t4-baseline-2026>

### Router-aligned document scopes — accepted

The 2026-09-28 official check again found Track 4 main at `7b2bce1`, shared toolkit main at
`95a0de3`, toolkit tag `v2.4.4`, and open issues 1, 2, 13, 14 and 16. The official README continues
to warn that most hidden families have no published counterpart and that rows can share evidence.
The MIT-licensed official strong-RAG retriever uses one cutoff-safe BM25 index without reusable
family-substring document filters; it was inspected as a design comparison and no code was copied.

The earlier strict-router experiment fixed calculator selection, but `allowed_document_ids` still
used the discarded loose substring rules. Consequently `inventory_position_rank`,
`cotton_yield_rank` and `positioning_of_inventory` routed to the generic calculator while their
retrieval scope silently entered the COT specialist. In the pre-registered seven collision cases,
only 4/7 retained a shared document allowed by the entity's root `corpus_ref`.

The accepted candidate dispatches specialist scopes from the same anchored `family_spec` key used
by calculators. Shared-document preservation improved from 4/7 to 7/7, all 20 published and
anchored-variant routes remained correct, and the general CIK entity boundary was unchanged. A
clean archive of commit `87704b0` and the candidate produced byte-identical answers for all 11
public units and 78 rows; all 11 passed toolkit 2.4.4 schema and smoke checks. Python 3.11 and 3.13
both passed 98 tests. No model request, prompt or calculator changed.

Script: `evaluation/experiments/scope_router_alignment_audit.py`. Report:
`evaluation/reports/scope-router-alignment-v1.json`.

References:

- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/Agenthon-2026/track4-analysis-public/blob/main/baselines/strong_rag_baseline/retriever.py>

### Explicit-zero default handling — rejected before code

A shared-code screen checked whether three `number(...) or default` call sites produced a measurable
cross-target bug when an entity explicitly supplied numeric zero. EPS-consensus and post-earnings
strong positive signals already produced the correct positive class under a zero threshold, although
the fallback changed their forecast magnitude. Only a synthetic zero-year rate row changed the
existing maturity-decay result, from the default ten-year 9 bps to the short-end 15 bps.

That is one regression boundary case, not evidence of a cross-family improvement. No real-outcome
panel establishes that changing the two zero-threshold point magnitudes helps. The candidate was
therefore rejected before production code; the current calculators and all public outputs remain
unchanged. Report: `evaluation/reports/explicit-zero-default-screen-v1.json`.

Reference: <https://github.com/Agenthon-2026/track4-analysis-public>.

### Strict structural router fallback — accepted

The 2026-09-28 update check found Track 4 main still at `7b2bce1`, shared toolkit main at
`95a0de3`, toolkit tag `v2.4.4`, and the same open Track 4 issues 1, 2, 13, 14 and 16. Public
submissions from `harrisonmo/agenthon2026-submission`,
`wangzgui/agenthon-t4-baseline-2026` and `dungcao06/optivex-t4-agent` were inspected for routing
ideas. Their useful common pattern is a broad model/retrieval path; none supplied a reusable strict
hidden-family specialist router.

The accepted candidate keeps anchored name routing first. Only when that route is generic does it
compare the target type and the fields present across every roster entity with complete known
signatures. Exactly one match activates a specialist; partial, wrong-type, mixed-roster, ambiguous
and prior substring-collision cases remain generic. This recovered 9/9 renamed complete structures
versus 0/9 for the prior router, while all 27 negative controls stayed generic.

A clean archive of baseline commit `ae1e631` and the candidate produced byte-identical answers for
all 11 public units and 78 rows. All answers had zero local validation errors and passed the
`qfbench2-common==2.4.4` smoke verifier. Python 3.13 passed 100 tests. The change adds no prompt
content, token use or model request. Script:
`evaluation/experiments/structural_router_fallback.py`. Report:
`evaluation/reports/structural-router-fallback-v1.json`.

References:

- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/harrisonmo/agenthon2026-submission>
- <https://github.com/wangzgui/agenthon-t4-baseline-2026>
- <https://github.com/dungcao06/optivex-t4-agent>

### Post-earnings ticker prior — rejected

A new 696-event 2024–2025 confirmation panel tested whether same-company historical abnormal-return
priors could replace the zero/flat fallback. The candidate grid was selected on 2021 after training
on 2018–2020. It selected the mean of the ticker's four most recent historical reactions, converted
to the existing conservative +/-1.25-point forecast step. The previously inspected 2022–2023 rows
were diagnostic only. The accepted zero-centered `[-8.3, 8.3]` fallback interval was held fixed, so
the point candidate could not improve through interval calibration.

On untouched 2024 events, accuracy rose from 0.1813 to 0.3428, but MAE worsened from 5.2506 to
5.3321. On untouched 2025 events, accuracy rose from 0.1399 to 0.3353, but MAE worsened from 5.4683
to 5.5183. The pre-registered rule required both years to preserve or improve accuracy and MAE.
The candidate is rejected; no ticker artifact or production change was added, and no NLI run was
needed.

Scripts: `evaluation/experiments/build_postearn_confirmation.py` and
`evaluation/experiments/postearn_ticker_prior.py`. Report:
`evaluation/reports/postearn-ticker-prior-v1.json`.

### Post-earnings classification-only holdout — outcome passed, NLI pending

The prior rejection treated point MAE as a hard gate even though the official classification
predictive-quality metric reads label accuracy. To avoid changing a rule after seeing its holdout,
the already locked `ticker_recent4` candidate was evaluated on a new 261-event 2026 YTD panel. Its
fit remained frozen at 2018–2023. The candidate uses only `-1.25`, `0`, or `+1.25` as the point that
represents its class and leaves the accepted zero-centered `[-8.3, 8.3]` interval unchanged.

Accuracy rose from 0.1648 to 0.3755, a 0.2107 absolute gain. Coverage was byte-for-byte equivalent
at 0.7778. Diagnostic point MAE rose by 0.0096 percentage points, but classification scoring does
not read that quantity. The outcome gate therefore passes.

Production is still deferred. The public AAPL, AMZN and META rows remain flat under the fitted prior,
so saved public NLI results do not test a changed label. A remote official two-model run is not
available: the Hugging Face route requires a missing token and one fixed judge model is not deployed
there. Heavy local NLI is disallowed by the active goal. The candidate remains outside runtime until
prediction-bound faithfulness can be verified on changed-label cases.

Script: `evaluation/experiments/postearn_classification_holdout.py`. Report:
`evaluation/reports/postearn-classification-holdout-v2.json`.

### Bounded prompt terms for opaque generic schemas — accepted

The same update check found no official repository or toolkit change. The public
`wangzgui/agenthon-t4-baseline-2026` retriever uses an entity-focused query plus a generic suffix;
that approach still has no task-specific signal when family, target and input fields are opaque.

The accepted candidate uses filtered words from only the first 512 prompt characters when the
strict route is generic and every schema identifier is opaque. It requires at least two useful
terms, retains at most 24, and replaces the broad generic rubric only on that path. Three synthetic
classification, regression and ranking cases improved from 0/3 to 3/3 correct top-one retrieval.
Template-prompt and semantic-schema queries remained byte-identical, and the maximum-term control
retained exactly 24 words.

A clean archive of baseline commit `08eaaaf` and the candidate produced byte-identical answers for
all 11 public units and 78 rows. All outputs therefore retain the baseline's toolkit 2.4.4 schema
and smoke result. Python 3.13 passed 113 tests. The candidate adds no model request and does not add
words to the model packet. Script: `evaluation/experiments/generic_prompt_query_priority.py`.
Report: `evaluation/reports/generic-prompt-query-priority-v1.json`.

References:

- <https://github.com/Agenthon-2026/track4-analysis-public>
- <https://github.com/wangzgui/agenthon-t4-baseline-2026>

### Known-family temporal query values — rejected before code

A cross-family screen appended supplied period values such as `quarter_reported`, `as_of`,
`ref_month` and `auction_date` to known-family BM25 queries. The pre-registered gate required all
three synthetic families to move from 0/3 to 3/3 correct top-one retrieval, with no more than 7/78
public top-one and 15/78 top-three changes.

The candidate reached 3/3, but the baseline was already correct on one EPS case, so the required
0/3 starting condition failed. It also changed 11/78 public top-one citations, above the limit; nine
were CPI rows and two were auctions. Top-three changed on 12/78 rows. Those alternatives may be
period-relevant, but no independent NLI or relevance label proves them better. Production code was
therefore left unchanged. No model was called. Script:
`evaluation/experiments/known_family_temporal_query_screen.py`. Report:
`evaluation/reports/known-family-temporal-query-screen-v1.json`.

### BM25 exact-score recency tie-break — accepted

After the temporal-query candidate was rejected for excessive citation churn, a narrower shared
retrieval hypothesis tested recency only when BM25 relevance scores are exactly equal. Three EPS,
rates and auction controls began with an older alphabetically preferred document; all improved from
0/3 to 3/3 correct top-one retrieval. The read-only public screen changed no top-one or top-three
result across 78 rows.

The first implementation also applied document-ID ordering to equal-date zero-score fallbacks and
failed an existing corpus-order test. It was narrowed before adoption: positive equal scores prefer
newer dates and retain document ID/span as final keys, while zero-score fallbacks use a stable
recency sort so equal dates preserve corpus order. A relevance-score difference always wins over
recency.

Python 3.13 passed 116 tests. A clean archive of baseline commit `751d04d` and the candidate produced
byte-identical answers for all 11 public units and 78 rows, with zero validation-error units. Those
bytes retain the baseline toolkit 2.4.4 schema and smoke result. No model was called. Screen script:
`evaluation/experiments/bm25_recency_tiebreak_screen.py`. Reports:
`evaluation/reports/bm25-recency-tiebreak-screen-v1.json` and
`evaluation/reports/bm25-recency-tiebreak-v1.json`.

### Context-limited batch splitting — accepted

The earlier context-local error handling let later batches continue but still discarded every row
in the oversized batch. A no-model size screen recorded the actual production-shaped public prompts
with batch size three and one. Batch prompts ranged from 4,410 to 41,167 characters; single-row
prompts ranged from 4,410 to 16,211. At the 16k, 24k and 32k deterministic proxies, respectively
15, 17 and 15 entities sat in a batch that exceeded the proxy while their individual prompt fit.
No authoritative House character or token ceiling is inferred from these proxies.

The accepted recovery records whether the immediately preceding API failure was an explicit context
limit. Only a multi-row batch with that failure is retried as single rows. Ordinary failures do not
split, and a failed single row is not recursively retried. Fault injection improved recovery from
0/3 to 3/3 rows after one oversized batch, while the existing 25-request test still blocks call 26.
All attempts remain under the shared deadline and four-failure circuit.

Python 3.13 passed 119 tests. A clean archive of baseline commit `f948922` and the candidate produced
byte-identical offline answers for all 11 public units and 78 rows, with zero validation-error units;
the same bytes retain the baseline toolkit 2.4.4 schema and smoke result. No real model was called.
Screen: `evaluation/experiments/context_batch_split_size_screen.py`. Reports:
`evaluation/reports/context-batch-split-size-screen-v1.json` and
`evaluation/reports/context-batch-split-recovery-v1.json`.

### Prompt-local evidence IDs, second remote A/B — deferred and rejected

The official shared and Track 4 repositories, v2.4.4 tag and open Issues 1, 2, 13, 14 and 16 were
unchanged. The newest commit in `harrisonmo/agenthon2026-submission` only recorded a frozen CodaBench
submission and changed no agent code. The earlier evidence-ID candidate was revisited because its
first same-family Nemotron comparison ended at the free quota boundary rather than failing its
quality hypothesis.

The candidate let the model return an item-local `E1`, `E2`, ... identifier while deterministic
code restored the original scoped document and exact span. Valid, foreign, cross-scope and tampered
IDs plus the legacy quote path passed 124 deterministic tests before remote testing. The candidate
was kept behind an A/B switch and its final patch is stored outside production at
`evaluation/experiments/candidates/evidence-id-v2.patch`.

On `gemini-2.5-flash-lite`, the three complete paired cases (classification plus unknown ranking)
retained 4/4 non-context facts in both arms and had no quote rejection. Evidence IDs reduced prompt
characters from 131,897 to 126,044 and completion tokens from 2,741 to 2,023. The regression/rates
pair was asymmetric because the quote arm received a transient 503 while the ID arm succeeded, so
it was excluded from quality comparison.

The weak-model `gemma-4-26b-a4b-it` run produced no valid paired model rows: responses were either
unparseable or hit HTTP 429/500. The run also lacked Gemma's documented `minimal` thinking level;
Gemini 2.5's `thinkingBudget=0` is not the Gemma control. Because the predeclared gate required valid
Flash-Lite, weak-model and same-family Nemotron pairs across all target types, Nemotron was not
called and the candidate was restored out of production. All 24 remote requests used free Gemini
quota and no local model. Report: `evaluation/reports/evidence-id-remote-ab-v2.json`.

References:

- <https://github.com/youxuanxue/track4-analysis-public/pull/4>
- <https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api>

### Deferred context-recovery scheduling — accepted

The immediately preceding context-splitting change recovered an oversized batch but retried its rows
before later three-row batches. Under the official 25-request cap, that ordering can spend three
slots on three rows while preventing later calls that could each enhance three rows. A deterministic
budget screen compared immediate and deferred recovery without changing error classification.

For a 78-row roster whose first batch hit a context limit and whose later batches succeeded,
deferring single-row recovery increased enhanced coverage from 66 to 72 rows under the same 25
network calls. A nine-row first-failure case remained 9/9, a nine-row all-context case remained 9/9,
and the clean 78-row path remained 75 enhanced rows. Production now records context-limited batches,
runs every normal batch first, then spends any remaining slots on the queued rows.

Python 3.13 passed 121 tests, including a budgeted 78-row fault injection and a nine-row all-context
case. A clean archive of baseline commit `848f18d` and the candidate produced byte-identical offline
answers for all 11 public units and 78 rows, with zero validation-error units. Those bytes retain the
baseline toolkit 2.4.4 schema and smoke result. No model was called. Screen:
`evaluation/experiments/context_recovery_scheduling_screen.py`. Reports:
`evaluation/reports/context-recovery-scheduling-screen-v1.json` and
`evaluation/reports/context-recovery-scheduling-v1.json`.

### Generic explicit-change shrinkage — accepted

The rejected fraction-to-percent experiment exposed a broader error: the generic fallback carried
the latest observed change forward at full magnitude, and an incorrectly tiny fraction happened to
score better. A cross-domain development screen therefore tested one shared positive multiplier on
explicit change targets matched to explicit change fields. The fixed grid used CPI 2021, COT 2021
and macro-revision 2020 only; mean normalized MAE selected `0.5`.

With that factor locked, the test periods improved in all three domains: CPI MAE fell from 1.7357
to 1.5545, COT point MAE from 6.3386 to 5.1151, and macro-revision MAE from 885.1707 to 852.1180.
Independent confirmation again improved all three: 2024-2025 CPI fell from 0.7933 to 0.6672, 2023
COT from 7.7006 to 6.1510, and 2023 macro revisions from 561.8640 to 530.7229. COT Spearman stayed
exactly unchanged in both periods because a positive multiplier preserves ranks.

Production applies the factor only after the generic selector returns an explicit target-token
match and both target and chosen field contain a change token. Levels, classifications, missing
change fields, incompatible units and every known-family early return retain their previous paths.
Auction and FOMC controls were byte-identical, and seven synthetic guards passed.

Python 3.13 passed 125 tests. A clean archive of baseline `1b13a46` and the candidate produced
byte-identical answers for all 11 public units and 78 rows; all 11 also passed the local structural
validator. No model API or local model was used. The experiment is reproducible after adoption by
reconstructing the pinned pre-change baseline before applying each candidate multiplier. Script:
`evaluation/experiments/generic_change_shrinkage.py`. Report:
`evaluation/reports/generic-change-shrinkage-v1.json`.

### Generic explicit-change direction classification — rejected

The generic no-model classification path emits a neutral or first-label fallback even when an
unknown entity contains a target-matched numeric change. A bounded candidate used that change's
sign only when both target and field explicitly described change and the positive and negative
label roles were unambiguous.

Across CPI, COT and macro revisions, mean development accuracy rose from 0.5983 to 0.6150 and mean
test accuracy from 0.5751 to 0.5925. The independent confirmation gate reversed: mean accuracy fell
from 0.5545 to 0.5387. CPI declined from 0.7347 to 0.6980 and macro revisions from 0.4741 to 0.4569,
while COT improved only from 0.4545 to 0.4614. Test rows with exactly zero feature values also made
the binary fallback sensitive to label order.

All six safety controls passed, but confirmation degradation and label-order sensitivity each fail
the predeclared rule. Production classification remains unchanged. No model was called. Script:
`evaluation/experiments/generic_change_direction_classification.py`. Report:
`evaluation/reports/generic-change-direction-classification-v1.json`.

### Generic numeric interval scaling — accepted

The 2026-09-29 preflight found no official rule or source update: shared main remained `95a0de3`,
Track 4 main remained `7b2bce1`, and the latest formal toolkit tag remained `v2.4.4`. The public
website now displayed Development leaderboard scores, but no hidden outcomes. The known public
Wang, Optivex and Harrison implementations also had no newer code than the versions already
screened.

The published scorer penalizes the absolute difference between realized coverage and the requested
interval level and has no separate interval-width term. Current generic 90% intervals were
systematically narrow on the development split: CPI covered 71.2%, COT 81.6% and macro revisions
30.4%. A fixed grid multiplied only the final generic numeric half-width. Under the requirement that
no development domain worsen, the lowest mean calibration error selected `2.0`.

With that factor locked, test mean calibration error fell from 0.2997 to 0.2295. Independent
confirmation fell from 0.2873 to 0.1928. Every CPI, COT and macro-revision test and confirmation
cell was non-inferior. Auction coverage stayed at 1.0 in both arms, while the FOMC transformed-schema
control improved from 10.3% to 16.7% coverage. Point forecasts, labels, retrieval and citations do
not change; model-signal point adjustment retains its previous scale.

Python 3.13 passed 126 tests. A clean archive of baseline `cbe352f` and the candidate produced
byte-identical answers for all 11 public units and 78 rows, and all 11 passed local structural
validation. No model API or local model was used. Script:
`evaluation/experiments/generic_interval_scale.py`. Report:
`evaluation/reports/generic-interval-scale-v1.json`.

### Shared batch evidence catalog — rejected before production

The 2026-09-29 preflight found no newer official Track 4 package or toolkit release and no new code
in the public implementations already tracked. Official issue #8 documents optional House reasoning
controls, but the current client already follows the published endpoint, token and request limits;
the organizers do not guarantee that the backend honors those optional controls.

A cross-family prompt audit tested whether multi-entity batches repeat identical evidence excerpts.
If so, a top-level evidence catalog could reduce context without dropping information. The gate
required at least 10% evidence-character savings across at least two families before any prompt or
production change.

Across all six public multi-entity batches, 136 evidence occurrences contained 136 unique excerpts.
Exact deduplication saved 0 of 204,741 evidence characters (0%) and helped zero families. The
hypothesis therefore failed before code or a remote-model A/B. Production prompts are unchanged;
no model API or local model was used. Script:
`evaluation/experiments/batch_evidence_dedup_screen.py`. Report:
`evaluation/reports/batch-evidence-dedup-screen-v1.json`.

### Global evidence-prefix reduction — rejected before production

The next cross-family screen tested a simpler way to reduce the same large model prompts: lower the
global 1,400-character prefix sent for every retrieved excerpt. The screen replayed the exact quote
locations of 49 facts validated from the saved remote weak-model run, spanning six tasks and five
families. The gate required 100% fact retention across multiple families and at least 10% possible
evidence-text savings.

A 1,200-character cap could save at most 14.3%, but retained only 44/49 facts. A 1,300-character cap
retained 48/49, but its maximum possible saving was only 7.1%. Only the existing 1,400-character cap
retained all 49 facts, with no savings. A uniform shorter prefix therefore cannot meet both safety
and context-reduction requirements. Production remains unchanged, and no new model call or local
model was used. Script: `evaluation/experiments/evidence_prefix_limit_screen.py`. Report:
`evaluation/reports/evidence-prefix-limit-screen-v1.json`.

### Recent-regime static FOMC interval width — rejected

After two shared prompt candidates failed, the next loop moved to the weak rates family. A static
half-width grid used 2022–2023 non-public FOMC events for selection, 2024–2025 for test and 2026 for
confirmation. The two public event dates were excluded from all three periods and inspected only
after the width was locked.

Development selected a 70bp half-width instead of the production 50bp. On the test period, however,
coverage rose from 95.6% to 100%, moving farther from the requested 90%: calibration loss worsened
from 0.0556 to 0.10. Confirmation was unchanged at 0.10. Although the locked candidate improved the
two-public-task diagnostic from 0% to 16.7% coverage, it failed the independent test gate and was
rejected. Production points, intervals, evidence and citations remain unchanged. No model API or
local model was used. Script: `evaluation/experiments/fomc_static_width_screen.py`. Report:
`evaluation/reports/fomc-static-width-screen-v1.json`.

### Generic target-matched dated tables — accepted with direct-observation scope

The 2026-09-29 preflight confirmed that shared toolkit main remains `95a0de3`, Track 4 main remains
`7b2bce1`, and toolkit `v2.4.4` remains the latest formal tag. The operative official update is the
removal of bring-your-own models and adapters: remote free models remain development analogues,
while scored runs use the House route. No Track 4 input, scoring or request-limit change was found.

The public `youxuanxue/track4-analysis-public` implementation supplied a strict-table safety
pattern. `wangzgui/agenthon-t4-baseline-2026@5d972915` supplied a separate rolling-origin fitted-prior
idea; it has no published official hidden score and was not mixed into this round.

The candidate parses only contiguous pipe tables whose first column is a valid, unique, strictly
increasing date no later than the task cutoff. It requires one exact target or series column, an
explicit compatible unit, an entity-bound document when multiple documents are visible, and
complete finite decimal cells. It never crosses a blank or malformed row and uses only the latest
direct observation. The first version also derived changes and converted percent differences to
basis points. Although its arithmetic was correct, the remote official NLI ensemble gave that
synthetic case 0.0 faithfulness because the cited rows did not directly state the subtraction. That
scope was rejected and removed. A change target is now supported only when the corpus itself has an
exact matching change column in the target unit.

On frozen rolling historical panels, persistence reduced auction bid-to-cover MAE from 2.4201 to
0.1548 on the 2020-2021 test and from 2.5250 to 0.1221 on the 2022-2024 confirmation. Quarterly
diluted-EPS MAE fell from 2.8056 to 1.8391 on test and from 1.9478 to 1.3891 on confirmation. All 17
malformed-table and unit controls passed. A clean archive of baseline `e7bd672` and the enabled
candidate produced byte-identical no-model answers for all 11 public units and 78 rows with zero
local validation errors. The complete suite passed 134 tests.

GitHub Actions run `36556813650` evaluated the production answer path with both fixed official NLI
members. The five-entity direct-ratio unit and five-entity direct-basis-point-change unit each scored
1.0 roster faithfulness, above the 0.80 gate. The candidate is therefore enabled by default, with
`T4_ENABLE_DATED_TABLE_BASELINE=0` retained as an operational rollback. No model API or local
language model was used. Reports: `evaluation/reports/generic-dated-table-extractor-v1.json`,
`evaluation/reports/generic-dated-table-public-ab-v1.json`, and
`evaluation/reports/nli/dated-table-direct-ensemble.json`.

### Request-budget adaptive batching — accepted

The fixed width of three could enhance at most 75 model-required rows under the official 25-call
limit. This left three rows on deterministic fallback in a clean 78-row roster and six rows after
either one transient failure or one first-batch context overflow. The candidate keeps width three
whenever the remaining request slots can cover the roster. Otherwise it chooses the smallest width
that can cover the remaining candidates, capped at six; `T4_MODEL_BATCH_SIZE` still overrides it
and `T4_ENABLE_ADAPTIVE_BATCH=0` provides an operational rollback.

Deterministic fault injection improved clean 78-row coverage from 75 to 78, and both transient-first
and first-context-overflow coverage from 72 to 78. Clean 100- and 150-row rosters reached complete
coverage, while the 60-row, 75-row, nine-row all-context and persistent-failure controls were
unchanged. No case issued call 26. A one-call width-four OpenRouter replay with the free Nemotron 3
Super analogue returned all four exact identities for 997 prompt and 527 completion tokens at zero
cost; width three required two calls and 1,450 prompt plus 498 completion tokens. A prior Google
Gemini 2.5 Flash Lite attempt was unavailable after two HTTP 503 responses and one timeout and was
not counted as a candidate failure.

GitHub Actions run `36564155953` then evaluated a 78-row production-path fixture with both pinned
official NLI members. Each member and the ensemble scored 1.0 faithfulness, and both existing
dated-table cases stayed at 1.0. The candidate is enabled by default. The public no-model A/B stayed
byte-identical for all 11 units and 78 rows. No local language model was run. Reports:
`evaluation/reports/adaptive-batch-screen-v1.json`,
`evaluation/reports/adaptive-batch-remote-ab-v1.json`,
`evaluation/reports/adaptive-batch-public-ab-v1.json`, and
`evaluation/reports/nli/adaptive-batch-ensemble.json`.

## 2026-09-30: post-earnings ticker prior citation preflight — rejected before runtime

The previously locked same-ticker recent-four prior improved classification accuracy from 0.1648
to 0.3755 on the untouched 261-event 2026 YTD confirmation panel while preserving the fixed
interval coverage. It remained deferred only because prediction-bound faithfulness had not been
tested. The new remote official NLI workflow removed the compute blocker, but a static provenance
audit found a more fundamental input mismatch.

The fitted abnormal-return history is a permitted local numerical artifact for forecasting, but it
is not part of an evaluated unit's frozen corpus and therefore cannot be cited. The published
post-earnings unit supplies six cutoff-safe SEC filings and no prior abnormal-return series in task
fields or corpus documents. Because the official judge constructs its hypothesis from the submitted
label, point and interval, prose cannot make the prior-selected direction faithful. Creating a
synthetic NLI unit that inserts the fitted history would test evidence unavailable to the actual
runtime and was deliberately not done.

The candidate is rejected before production despite its outcome gain. No prediction, citation, API
call or image changed. A different corpus-conditioned mechanism may be reconsidered only for units
that explicitly supply cutoff-safe reaction history or a direct forward statement supporting the
same canonical direction. Report:
`evaluation/reports/postearn-prior-citation-preflight-v1.json`.

## 2026-09-30: generic cross-sectional peer statistics — rejected before prompt change

The next L3 screen tested whether peer median, MAD, robust z-score and percentile supplied useful
full-roster context beyond each entity's visible scalar. CPI components were grouped by reference
month as a transformed unknown binary-classification proxy; ten COT markets were grouped by week
as an unknown-ranking proxy. Development, time-forward test and untouched confirmation periods
were kept separate. A simple peer-centered direction served only as an information screen, not as
a proposed production forecast rule.

All rows were computable and no group had zero MAD. Nevertheless, CPI test accuracy fell from
0.7576 for the raw sign to 0.5076 for the peer-centered sign, and confirmation fell from 0.6980 to
0.5061; macro-F1 also declined in both periods. Within every COT group, percentile and robust z-score
were monotonic transforms of the raw value, so their rank order and mean Spearman were exactly
unchanged in all splits.

The pre-registered cross-target gate failed. No prompt, production code, API call, prediction,
citation or image changed. Script: `evaluation/experiments/cross_section_stats_screen.py`. Report:
`evaluation/reports/cross-section-stats-screen-v1.json`.

## 2026-09-30: fixed-role multi-query RRF — rejected before production

A retrieval benchmark used 22 non-context weak-model facts whose quotes had already passed exact
span, entity scope and cutoff validation. The labels covered EPS YoY, credit, post-earnings and
rates. The current single BM25 query was compared with five-query reciprocal-rank fusion at fixed
`k=60`: the baseline query plus target observation, historical/previous, expectations/consensus and
guidance/outlook/risk roles.

The first screen accidentally admitted the retriever's zero-score recency fallbacks as votes from
empty role queries. Excluding those non-matches was a correctness repair; query text, fusion
constant and adoption thresholds stayed locked. The corrected result was identical. Overall hit@3
fell from 0.8182 to 0.6364, hit@8 from 1.0 to 0.6818 and MRR from 0.7045 to 0.4535. EPS, credit and
post-earnings regressed, rates was unchanged and no family improved. Retrieved characters fell only
0.3%, while the top-eight sets accumulated 70 symmetric-difference positions.

The candidate failed every relevance gate and never entered production or NLI. No model API or
local model ran. Script: `evaluation/experiments/multi_query_rrf_screen.py`. Report:
`evaluation/reports/multi-query-rrf-screen-v1.json`.

## 2026-09-30: metadata-driven TargetSpec — rejected before production

An inventory compared all 11 published task targets with the official alignment contract and the
production validator. The output contract is already covered locally: exact roster, classification
label vocabulary, required regression/ranking point, finite numerics, exact interval level and
ordering, and complete optional rank permutation. Production additionally requires the point to
lie inside its interval.

No published target object carries `unit`, `units`, `minimum`, `maximum`, `min`, `max` or `domain`.
The explicit-unit rate and explicit-bound rate are both 0/11 across classification, regression and
ranking. A single authoritative metadata-driven TargetSpec therefore cannot be constructed from the
actual task schema. Inferring every quantity from free-form prompt prose could mis-clamp returns,
percent probabilities, ratios or basis-point changes and has no labeled paraphrase benchmark.

The candidate was rejected before code. Existing explicit field-name unit guards, strict table
units and family calculators remain unchanged. No model or NLI ran. Script:
`evaluation/experiments/target_contract_inventory.py`. Report:
`evaluation/reports/target-contract-inventory-v1.json`.

## 2026-09-30: shared macro model context — already satisfied or not applicable

The rates, CPI and macro-revision paths were audited before introducing a second shared-context
representation. Both published FOMC curve units already make exactly one task-level model request
for all six tenors. CPI and macro revision make zero model requests because their cutoff-safe
tables are consumed by deterministic calculators. Consequently, their repeated BM25 chunks never
consume House model input tokens.

The audit still measured retrieval overlap. Exact duplicate chunk characters were 90.9% for CPI,
83.3% for both rate units and 59.3% for macro revision. This does not expose a model-context saving:
the rate prompt is already shared, while the other two families have no model prompt. All entity
queries were distinct, and their result sets remain useful for entity-specific fallback context and
citations. Replacing them with one common retrieval would therefore change evidence selection to
save only inexpensive local BM25 work.

The candidate was rejected as already satisfied or not applicable under the pre-registered gate,
which required at least two model-required macro families with multiple prompts and at least 10%
exact duplicated prompt evidence. No production code, prediction, citation, model call or NLI
changed. Script: `evaluation/experiments/shared_macro_context_audit.py`. Report:
`evaluation/reports/shared-macro-context-audit-v1.json`.

## 2026-09-30: real-outcome generic classification benchmark and opaque label synonym — rejected

A new benchmark sampled balanced positive and negative time-forward outcomes from the frozen CPI,
COT and macro-revision panels. Each split contains six rows per domain, and each row is evaluated
under semantic `up/down` labels and prompt-defined opaque `class_a/class_b` labels. The model sees
one cutoff-safe lagged feature; the future outcome is available only to the scorer. Metrics include
accuracy, macro-F1, hard-label Brier, quote validation, label-schema consistency and API usage.

Three free Google lightweight-model attempts were incomplete and are retained rather than silently
discarded. Gemini 2.5 Flash Lite had nine failed batches, Gemini 3.1 Flash Lite had two, and Gemini
3.5 Flash Lite had one malformed-JSON batch. Their aggregate scorecards are marked invalid. The
completed 3.5 rows nevertheless exposed one deterministic mapper defect: for the same validated
direction signal, the current parser understood `higher/lower` but did not understand prompt clauses
using `above/below`. A saved-signal screen excluded the unresolved batch and found that adding those
two synonyms would raise opaque-label test accuracy from 0.5000 to 0.6111 and macro-F1 from 0.3333
to 0.5786. Confirmation accuracy rose to 0.5556 and macro-F1 to 0.5500, with no domain regression.
The public 11-unit no-model A/B remained byte-identical and 138 tests passed after the candidate was
reverted.

The outcome gate was not sufficient for adoption. The official canonical classification hypothesis
contains the submitted opaque token, for example `class_b`, but omits the task-prompt definition
that says `class_b means below zero`. None of the 36 runtime evidence documents contains either
opaque label definition; they contain only lagged numbers. Consequently, the cited premise cannot
entail the changed opaque prediction. A remote NLI run would test a statically invalid premise and
was deliberately skipped. Production role keywords and tests were restored to baseline.

Scripts: `evaluation/experiments/generic_classification_benchmark.py`,
`evaluation/experiments/generic_above_below_role_screen.py`, and
`evaluation/experiments/generic_opaque_label_nli_preflight.py`. Reports:
`evaluation/reports/generic-classification-benchmark-v1.json`,
`evaluation/reports/generic-above-below-role-screen-v1.json`, and
`evaluation/reports/generic-opaque-label-nli-preflight-v1.json`.

## 2026-09-30: horizon-aligned FOMC reversal — rejected

The existing rates screens had already rejected curve ridge, policy-augmented ridge, cutoff-day
reaction and 10/20-trading-day momentum. A final point-model screen tested whether the prompt's
explicit "already priced" regime was better represented by reversing a pre-cutoff move over 35,
45 or 60 trading days, closer to the intermeeting forecast horizon. Development selected a 35-day
move multiplied by -0.25.

The locked candidate improved direction accuracy but failed the magnitude gates. Relative to the
best of zero change and policy decay, test MAE worsened by 21.46% and the untouched 2022–2026
confirmation MAE worsened by 12.29%. The worst tenor regressed by 4.22 bps on test and 4.05 bps on
confirmation, both above the pre-registered 2 bps ceiling. The public 2022 and 2024 events were
excluded from selection, test and confirmation and retained only as diagnostics.

The candidate was rejected before corpus parsing, citation construction or NLI. No production
code, model request, prediction, citation or image changed. Script:
`evaluation/experiments/fomc_long_reversal_screen.py`. Report:
`evaluation/reports/fomc-long-reversal-screen-v1.json`.

## 2026-09-30: bank EPS interval calibration — accepted

The previously deferred bank EPS rule was reopened after a remote official NLI path became
available. The point model remains seasonal EPS-delta persistence. Only the 90% interval changes
from `max(20, 0.75 * abs(point))` to `max(100, abs(point))` percentage points.

On the frozen SEC time-forward panel, test calibration loss fell from 0.1759 to 0.1000 and locked
confirmation fell from 0.2438 to 0.1000. Mean full width increased materially, but the official
Track 4 scorer at `7b2bce1` explicitly has no width, sharpness or Winkler term; it scores
`abs(coverage - 0.90)`. The retired public bank unit moved from 7/8 to 8/8 coverage and therefore
worsened its own calibration loss from 0.025 to 0.10. That development-influenced unit was retained
as a transparent diagnostic rather than used to overturn both time-forward splits.

GitHub Actions run `36605861989` evaluated the changed canonical hypotheses with both fixed
official NLI members. Single-member roster faithfulness was 0.875 and 1.0; the ensemble was 0.875,
above the 0.80 gate. The 11-unit A/B changed exactly the eight bank interval objects, preserved all
other answer fields, and produced zero validation errors. Python 3.11.7 passed 139 tests. The rule
is enabled by default; `T4_ENABLE_BANK_EPS_INTERVAL=0` is the rollback. No House request, external
generation model or local language model was used.

Reports: `evaluation/reports/bank-eps-interval-calibration-v1.json`,
`evaluation/reports/bank-eps-interval-public-ab-v1.json`, and
`evaluation/reports/nli/bank-eps-interval-{cross,moritz,ensemble}.json`.

The adopted production commit is `af25dc76e2e5acf4f1f937b95e5abbfaf4aeec89`. GitHub Actions run
`36694555608` passed the Python 3.13 suite, built and pushed a Linux/amd64 OCI image, and smoke-tested
the `analyze` command. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:19ce8df06d5c9dfbadf1fe2465500d55a68c06b9851a7ea02292421e33fd903a`.
An unauthenticated GHCR token and manifest request returned HTTP 200; the config reports Linux,
amd64 and `qfbench2.interface_version=2.0`. No formal competition submission was performed.

## 2026-10-01: scorer 5.2.2 bank EPS interval rescore — wide rule reverted

The official preflight found a scoring-contract change rather than a small documentation update.
Track 4 main is now `ede7381d8c1ba9d8c84068f9d142f5e093a33892` (scorer 5.2.2), shared main is
`8c0b3f7bf031b595c2e45c2e488cdd33fbf0c7fd`, and the latest toolkit tag is `v2.5.1`.
The current composite compares prediction error and mean interval score against each unit's declared
naive answer. Interval width is charged directly; coverage is diagnostic. The former roster-level
0.80 NLI gate is also replaced by a per-claim soft penalty, with deterministic claim rules running
in Development and contradiction NLI added in Final.

This change invalidated the metric used to accept the bank EPS 100-point floor. All eight SEC
Company Concept files were downloaded again into a temporary cache; every SHA-256 matched the
recorded source, and the experiment reproduced 158 rows split 69/28/29/32 across
train/development/test/confirmation.

Using the official 90% mean interval score, where lower is better:

| Rule | Development | Test | Confirmation |
|---|---:|---:|---:|
| restored legacy `max(20, 0.75 × abs(point))` | 729.43 | 133.17 | 126.42 |
| current wide `max(100, abs(point))` | 592.36 | 200.00 | 200.08 |
| development-selected grid rule `max(100, 0.75 × abs(point))` | 573.88 | 200.00 | 200.00 |

The grid candidate failed both preregistered held-out conditions: it did not strictly improve the
current rule on test and confirmation, and it was worse than legacy on both. More importantly, the
adopted wide rule itself increased interval score versus legacy by 66.83 on test and 73.66 on
confirmation. Production therefore restores the legacy half-width and removes the obsolete feature
flag. The point model, labels, ranks, retrieval and citations are unchanged.

A commit-level A/B over the 11 published units and 78 rows changed exactly the eight bank interval
objects, preserved all non-interval fields, and produced zero validation errors. The pinned 5.2.2
schema accepted all 11 answers. Its deterministic claim rail checked 286 claims with zero basic
findings and zero deterministic false reasons. The judge-tokenizer-specific 400-token cap was not
checked; every claim is short, but that is recorded as an unchecked condition rather than a pass.
No local or remote language model and no NLI model ran. The complete Python suite passed 138 tests.

Reports:

- `evaluation/reports/bank-eps-interval-official-522-rescore-v1.json`
- `evaluation/reports/bank-eps-interval-official-522-public-ab-v1.json`
- `evaluation/reports/bank-eps-interval-official-522-claim-rail-v1.json`

The earlier calibration report and NLI reports remain historical evidence for the scorer version
that produced them; the calibration report now points to this superseding rescore. The next interval
round should screen the other coverage-selected family rules under mean interval score before
changing another production family.

A same-day public-repository check found no indexed implementation of `mean_interval_score` or a
5.2.2 interval rescore in the four previously tracked participant repositories. The most recently
updated reference, `wangzgui/agenthon-t4-baseline-2026` at commit `1fe5fa4`, does acknowledge scorer
5.2.2 and reports participant-supplied S1.6 score 0.4793, but S1.7 has no official score. Its new
ideas are checked source arithmetic, residual-band guards and optional bounded
`submitted_reasons`; its own research note says full-pipeline calibration remains future work.
Those mechanisms are useful candidates for later independent tests, not evidence against the bank
interval rollback. No code was copied. All four checked repositories declare MIT licenses.

Production commit `2274c25467a4ef3852a862587d03b50069d98bb8` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `36841579367` passed the Python 3.13 suite, built and
pushed Linux/amd64, pulled the published image, and passed `analyze --help`. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:7d3205a2046d67b358f9a4019a445bc9ab70631106730ce45a2a1bce48235a85`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the config reports Linux,
amd64 and `qfbench2.interface_version=2.0`. The development submission template now points to that
digest. No formal competition submission was performed.

## 2026-10-01: scorer 5.2.2 cross-family interval rescore — two rollback candidates

The shared official repository advanced to `84221f1b553475b1283cb653145051e916377dd0`.
The update removes review/manual-review promises and documents the existing 5.2.x Final
contradiction rule: two NLI models are averaged and a three-way contradiction probability above
0.9 marks the claim false. Track 4 remains at
`ede7381d8c1ba9d8c84068f9d142f5e093a33892`, scorer 5.2.2, and toolkit tag `v2.5.1`; there is no
new scoring behavior to implement.

The next preregistered screen held every point forecast fixed and rescored the accepted family
intervals against their immediate predecessors with the official 90% interval score. A family was
flagged only if its current rule had a strictly higher mean score on both forward test and
confirmation. Results were:

| Family | Test current / predecessor | Confirmation current / predecessor | Decision |
|---|---:|---:|---|
| EPS YoY | 16.63 / 36.60 | 9.57 / 18.94 | retain |
| CPI | 9.84 / 9.64 | 3.97 / 3.66 | rollback candidate |
| COT | 31.56 / 34.52 | 41.59 / 47.56 | retain |
| Treasury auction | 0.603 / 0.585 | 0.470 / 0.463 | rollback candidate |
| Post-earnings | 37.05 / 68.31 | 39.53 / 71.85 | retain |

The generic final-width multiplier of 2.0 also beat its 1.0 predecessor in CPI, COT and macro
revision on both periods. An unchanged 50-basis-point FOMC control reproduced exactly. The
hypothesis was supported: CPI and auction coverage-selected intervals are worse under the current
official loss. The screen makes no production change. CPI is selected for the next isolated round
because its confirmation deterioration is larger; auction remains queued. No model API or local
language model was used.

Script: `evaluation/experiments/official_522_interval_rescore_screen.py`. Report:
`evaluation/reports/official-522-interval-rescore-screen-v1.json`.

## 2026-10-01: scorer 5.2.2 CPI interval rescore — 0.35 floor restored

The first isolated rollback candidate restores the CPI component interval floor from 0.75 to 0.35
percentage points while retaining the 1.65 historical-volatility multiplier and every point,
component override, retrieval and citation rule. With the point forecast fixed, official mean
interval score fell from 9.8414 to 9.6351 across 264 rows in 2022–2023 and from 3.9671 to 3.6630
across 245 rows in the locked 2024–2025 confirmation. Both preregistered outcome gates therefore
passed.

The 11-unit, 78-row public A/B changed seven CPI interval objects and no other field. All outputs
had zero local validation errors. The pinned scorer 5.2.2 schema accepted 11/11 units; its claim
rail inspected 286 claims with zero basic findings and zero deterministic false reasons. The judge
tokenizer-specific 400-token cap remains unchecked. Contradiction NLI was not repeated because all
claims and citations are byte-identical. Python 3.11.7 passed 138 tests. No model API, local
language model or NLI model was used.

Reports:

- `evaluation/reports/cpi-interval-official-522-revert-v1.json`
- `evaluation/reports/cpi-interval-official-522-public-ab-v1.json`
- `evaluation/reports/cpi-interval-official-522-claim-rail-v1.json`

The CPI rollback is accepted. The Treasury-auction interval remains the next independent candidate;
its point-model evidence must stay separate from its interval-width comparison.

Production commit `a2d93761e9bf5c5cb7255560791498fe24bd0371` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `36843546337` passed the Python 3.13 suite, built and
pushed Linux/amd64, pulled the published image, and passed `analyze --help`. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:ab4cdc59ee4b5b87a99bce52fe75f716668595b697843f4cf19f22c3cb5da58b`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the digest matched exactly and
the config reports Linux, amd64 and `qfbench2.interface_version=2.0`. The development submission
template now points to that digest. No formal competition submission was performed.

## 2026-10-01: method-aware context evidence for submitted reasons — accepted

The first submitted-reason formatter preferred non-context facts but otherwise used the first valid
context span. Fresh traces found 15 computed-input reasons and 16 context-only reasons among the 31
public reasons. Several context-only premises were filing headers, table-of-contents fragments or
generic accounting text even when a more relevant exact span was already in the row's cutoff-safe,
entity-scoped retrieved chunks.

The candidate scores bounded exact windows with a fixed vocabulary for the selected deterministic
method, penalizes common filing noise, and replaces the prior span only with a four-point relevance
gain. It performs no new retrieval or model call. The final public A/B changes four premises and
their reason citations: BBBY liquidity/going-concern/default evidence, AMD period-matched EPS data,
DOW period-matched net-income/EPS calculations and AAPL operating-result data. All 15
computed-input controls remain unchanged. Removing `submitted_reasons` makes all 11 candidate
answers identical to the baseline; reason IDs, mechanisms, implications, scopes and order are also
unchanged. `T4_ENABLE_REASON_RELEVANCE=0` is the isolated rollback.

A broader six-replacement screen was not adopted. One blind, thinking-disabled
`gemini-2.5-flash-lite` call used 4,081 prompt and 928 completion tokens and returned five candidate
preferences, five baseline preferences and two ties across grounding and link. It preferred the
new BBBY, AMD and AAPL premises, but preferred the old BBY and AMZN premises and rejected an early
DOW anti-dilution fragment. The final selector therefore rewards credit-rating evidence, penalizes
anti-dilution fragments and requires the larger gain. DOW then moved to a different exact numeric
EPS table; it was not re-judged to avoid a second quota call. The proxy is diagnostic only and
cannot observe hidden target reasons.

The pinned official repositories remained at Track 4
`ede7381d8c1ba9d8c84068f9d142f5e093a33892` and shared
`84221f1b553475b1283cb653145051e916377dd0`. The final outputs pass 11/11 scorer 5.2.2 schemas,
31/31 reasons are judged, and 286 unchanged claims have zero basic or deterministic findings; the
reason rail also has zero findings. Python 3.11.7 passed 144 tests. No local LLM or NLI ran.

Public-repository research found no `submitted_reasons` implementation in the inspected MIT-licensed
`dungcao06/optivex-t4-agent` main branch. The MIT-licensed
`wangzgui/agenthon-t4-baseline-2026` uses exact bounded quotes and distinct mechanisms, while its own
notes state that causal and hidden target-reason quality remain unmeasured. These ideas support the
exact-span and mechanism-distinctness constraints but do not provide an independent score.

Reports:

- `evaluation/reports/reason-evidence-relevance-screen-v1.json`
- `evaluation/reports/reason-evidence-relevance-public-ab-v1.json`
- `evaluation/reports/reason-evidence-relevance-official-522-rail-v1.json`
- `evaluation/reports/reason-evidence-relevance-quality-proxy-broad-v1.json`
- `evaluation/reports/reason-evidence-relevance-final-v1.json`

## 2026-10-01: bounded submitted reasons — accepted

Scorer 5.2.2 adds a separate Final-only reasoning bonus of up to 0.25. The current agent omitted
`submitted_reasons`, guaranteeing a zero contribution. Official rules floor weak or refused
reasoning at zero without reducing analysis, while malformed schema can still invalidate a unit.
The candidate therefore builds at most three reasons only from already validated `RowResult` facts,
a fixed description of the deterministic calculator method and the final normalized label or
point. It omits the field whenever a published answer, reason, evidence or citation cap cannot be
proven. `T4_ENABLE_SUBMITTED_REASONS=0` is the rollback.

All 11 public units produced reasons: 31 across 78 rows. Removing only the new top-level field made
every candidate answer byte-identical to the production baseline. The pinned 5.2.2 schema accepted
11/11, the official submitted-reason rail reported zero findings, and the unchanged 286 claims
retained zero basic and deterministic false findings. Python 3.11.7 passed 141 tests.

One quota-conscious call to `gemini-2.5-flash-lite` reviewed all 11 public candidates under a
conservative rendering of the official four components. It used 22,147 prompt and 1,215 completion
tokens with thinking disabled and returned no contradictions. It rated all four components 1.0 for
every unit. That uniform result is optimistic and is treated only as a non-official consistency
proxy, not a score claim. Production reasons equal the proxy inputs in ten units; COT removes rank
from the implication because the official reasoning judge does not read rank. Premises, mechanisms,
point implications and citations are unchanged. No local language model or NLI model ran.

Reports:

- `evaluation/reports/bounded-submitted-reasons-v1.json`
- `evaluation/reports/submitted-reasons-static-screen-v1.json`
- `evaluation/reports/submitted-reasons-quality-proxy-v1.json`
- `evaluation/reports/submitted-reasons-public-ab-v1.json`
- `evaluation/reports/submitted-reasons-official-522-production-rail-v1.json`

The candidate is accepted because every fatal structural condition is proven, all analysis fields
are invariant, and the official formula makes its remaining quality uncertainty one-sided: useful
reasons can add a bonus, while valid but unhelpful reasons add zero.

## 2026-10-01: scorer 5.2.2 Treasury-auction interval rescore — 1.65 restored

The second isolated rollback candidate keeps the accepted recent-six same-tenor mean point forecast
and changes only the 90% interval multiplier from 2.5 to 1.65. The 0.15 ratio floor is unchanged.
Official mean interval score fell from 0.6028 to 0.5853 across 168 rows in 2022–2023 and from 0.4697
to 0.4629 across 70 rows in the untouched January–October 2024 confirmation. The improvement is
small but strictly positive on both preregistered periods.

The 11-unit, 78-row public A/B changed six auction interval objects and no other field. All outputs
had zero local validation errors. The pinned scorer 5.2.2 schema accepted 11/11 units; its claim
rail inspected 286 claims with zero basic findings and zero deterministic false reasons. The judge
tokenizer-specific 400-token cap remains unchecked. Contradiction NLI was not repeated because all
claims and citations are byte-identical. Python 3.11.7 passed 138 tests. No model API, local
language model or NLI model was used.

Reports:

- `evaluation/reports/auction-interval-official-522-revert-v1.json`
- `evaluation/reports/auction-interval-official-522-public-ab-v1.json`
- `evaluation/reports/auction-interval-official-522-claim-rail-v1.json`

The interval rollback is accepted. The recent-six mean point rule and verified concise citation
remain unchanged; the retired coverage-calibration evidence remains historical provenance.

Production commit `183d5808a070ecfd22fd4b120e8f977bf67f1ee3` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `36844089943` passed the Python 3.13 suite, built and
pushed Linux/amd64, pulled the published image, and passed `analyze --help`. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:13f970a7d96b5ce5e8edb56d1e0176805c4c593b208af593b0d2e7883eeda841`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the digest matched exactly and
the config reports Linux, amd64 and `qfbench2.interface_version=2.0`. The development submission
template now points to that digest. No formal competition submission was performed.

Production commit `d7a731f7b4e64816fd387a79280f7ade4aa8e65b` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `36845475381` passed 141 tests on Python 3.13, built
and pushed Linux/amd64, pulled the published image, and passed `analyze --help`. The immutable image
is `ghcr.io/yif-design/agenthon2026-t4@sha256:af2d58bae3f54a1963bace977f80001f9ecff087f9cc65271b92edb6ed02b081`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the digest matched exactly and
the config reports Linux, amd64 and `qfbench2.interface_version=2.0`. The development submission
template now points to that digest. No formal competition submission was performed.

Production commit `0020e289516dfa6c7bd0200c7746e575d0afc4d9` was pushed to
`codex/t4-agent-skeleton`. GitHub Actions run `36850192475` passed 144 tests on Python 3.13, built
and pushed Linux/amd64, pulled the published image, and passed `analyze --help`. The immutable image
is `ghcr.io/yif-design/agenthon2026-t4@sha256:9138e521f7a312a45471489050997693f5cb28fd87539a0852519df9466e6b31`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the digest matched exactly, the
manifest is OCI, and the config reports Linux, amd64 and `qfbench2.interface_version=2.0`. The
development submission template now points to that digest. No formal competition submission was
performed.

## 2026-10-03: first runnable proxy benchmark slice — infrastructure accepted, degradation hypothesis rejected

The twenty-question catalog previously contained no runnable units. Proxy-18 now has an explicit
and a transformed schema for one 2023 CFTC next-report positioning event, with a tracked public
source snapshot, cutoff-safe corpus, hidden local outcome, declared naive answer, provenance,
manifest hashes and deterministic validators. Rebuilding twice produced identical hashes. The
current model-free production control ran on both ten-entity ranking units without a model API.

Under the scorer 5.2.2 predictive and interval formulas before claim penalty, the explicit route
used `net_position_mean_reversion`, obtained Spearman 0.3333 and composite 0.5561. The transformed
route used `generic_baseline`, obtained Spearman 0.3818 and composite 0.5950. All ten transformed
rows recorded model-unavailable fallback because the generic route normally requests a signal, but
still produced complete answers. The transformed numeric feature is fraction-scaled while the
target is percentage points; ranking is scale-invariant, whereas its interval score is not.

The preregistered hypothesis that schema transformation would cause a material score decline is
rejected for this event. The different route and unit handling show a real schema dependency, but
the score increased rather than decreased. No production logic changed. This single event proves
the generator, leakage checks, schema-pair invariants and control runner; it is too small to claim
schema robustness or select an architecture. The next benchmark round should materialize another
Wave 1 target type before revisiting production.

The official remote repositories remain at Track 4 `ede7381d8c1ba9d8c84068f9d142f5e093a33892`,
shared main `84221f1b553475b1283cb653145051e916377dd0` and toolkit `v2.5.1`. The ignored local
`starter-repos/track4-analysis-public` snapshot still contains scorer 3.1.0 and must not be used as
the current authority. Python 3.11.7 passed 149 tests. No local or remote LLM and no NLI ran.

Report: `evaluation/reports/proxy-18-cot-control-v1.json`.

Release record for the accepted benchmark infrastructure: commit
`33ec1e7daa5774bbe8d4d0ba65cee8447b6cc97a` was pushed to `codex/t4-agent-skeleton`. GitHub Actions
run `37091935219` passed the Python 3.13 test suite, built and pushed Linux/amd64, and passed the
container `analyze --help` smoke. The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:f0d58b7b69906449034a09273ad545d6df3d42286ac4dffbde7ca6815948408f`.
Anonymous GHCR manifest and config requests both returned HTTP 200; the resolved digest matched,
the manifest is OCI, and the config reports Linux, amd64 and `qfbench2.interface_version=2.0`.
The development submission template now points to that digest. No formal competition submission
was performed.

Release record for the toolkit 2.6 compatibility repair: commit
`133ede423d1ad475d613d6dcced0dfb0589d77ff` was pushed to `codex/t4-agent-skeleton`. GitHub Actions
run `37094824716` passed 154 tests on Python 3.13.15, installed the pinned v2.6.0 toolkit, packed and
inspected the synthetic submission ZIP, built and pushed Linux/amd64, and passed `analyze --help`.
The immutable image is
`ghcr.io/yif-design/agenthon2026-t4@sha256:deac243e887c194e43819ef272b4b6d671fa8fa5684ca93b161c3f684eea670d`.
Anonymous manifest and config requests returned HTTP 200; the OCI image is Linux/amd64, about 44.2
MiB compressed, and carries `qfbench2.interface_version=2.0`. No formal submission was performed.

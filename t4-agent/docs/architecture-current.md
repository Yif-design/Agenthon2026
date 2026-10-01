# Current Track 4 architecture

Last updated: 2026-10-01

The submitted path is a baseline-first bounded workflow:

1. Load the task and cutoff-filter the frozen corpus.
2. Route the target to an isolated family specification.
3. Disable any fitted family parameter whose recorded availability date is later than the task
   cutoff, then hard-scope documents by entity, series, tenor or shared macro source.
4. Retrieve evidence with BM25 and extract explicit numerical parameters deterministically.
5. Compute and atomically write a complete model-free baseline answer.
6. For families that need text judgement, use batches of three when they fit the remaining request
   budget; otherwise raise the width only as far as needed, capped at six, and ask the
   House-compatible model for five-level signals, explicit numbers and exact quotes.
7. Reject model facts with a foreign document, non-exact quote or invalid value.
8. Re-run the deterministic family calculator with accepted signals and parameters.
9. Normalize rankings, validate the complete answer, and atomically replace the baseline only when
   the enhanced answer is valid.

The formal CLI writes only the required answer by default. Full route, row and usage traces repeat
retrieved corpus passages for every entity and are therefore emitted only when development code
explicitly passes `--trace-dir`. This keeps optional diagnostics out of the competition's 64 MiB
complete-output-tree allowance without changing predictions or local trace content.

Batch responses are mapped back to the requested roster by both integer `item_id` and string
`entity_id`. Reordered rows are accepted. If both identifiers resolve but disagree, that model row
is rejected so it cannot cross entity boundaries. Every identity field that is present must have
the correct type and resolve inside the current batch; a foreign entity ID cannot be hidden by a
valid item ID, and an invalid item ID cannot be hidden by a valid entity ID. If one field is absent,
the other valid field can still recover the row. A missing row falls back independently without
discarding valid sibling rows.

The model boundary enforces JSON scalar types before any calculator runs. Python booleans are not
accepted as integer item IDs or five-level signals, and non-finite values such as `NaN` and
`Infinity` are not accepted as numeric parameters. An invalid signal becomes neutral, an invalid
parameter remains missing, and an invalid batch identity falls back per entity. Finite numeric
strings, named signal levels and correctly typed reordered batches keep their prior behavior.

This design uses at most the official 25 requests, a 420-second model phase, 40-second request
timeouts and a circuit breaker. Batches stay at three entities whenever the remaining requests can
cover the roster. When they cannot, the width rises to the smallest required integer, capped at six.
A clean 78-row route therefore uses 20 width-four requests and enhances all 78 rows; a clean route
can cover up to 150 rows before deterministic fallback is required. Each batch gets two attempts by default. The
cross-batch circuit opens after four consecutive failures, so one malformed batch falls back
without suppressing every later independent batch; a successful response resets the count. Authorization failures,
non-retriable client errors, the request cap and the deadline still stop immediately. A failed API,
invalid JSON or trace-write failure leaves the already-written baseline answer intact.

An HTTP 400 that explicitly identifies a context-length or token-limit overflow is local to that
batch: retrying the same prompt is skipped. A multi-entity batch is then attempted once per entity
with the shorter single-row prompt, but only after every normal batch has received its higher-yield
request opportunity. A single-row failure is not recursively retried. This preserves up to three
rows per normal request before spending remaining slots one row at a time. Every recovery attempt
remains inside the same 25-request cap, four-failure circuit and model-phase deadline. An unknown
HTTP 400 remains globally non-retriable. This reacts to the serving route's actual limit without
inventing an unpublished character or token ceiling.

An HTTP 429 is retried only after the server's `Retry-After` delay when that delay fits both the
30-second retry ceiling and the remaining model-phase deadline. Both RFC forms, integer seconds and
an HTTP date, are accepted. A longer requested delay falls back for that batch instead of retrying
early, and an absent or malformed header retains the one-second bounded retry. Rate limiting does
not remove JSON mode from the retry. The normal path, request cap and two-attempt default are
unchanged.

The assistant message and optional usage telemetry are independent at the response boundary. A
valid assistant JSON object remains usable when `usage` is absent, is not an object, or contains an
invalid counter. Valid non-negative counters are accumulated; booleans, negative values,
non-numeric values and non-finite costs are ignored. Malformed `choices` or assistant content still
uses the normal retry and fallback path. This prevents nonessential accounting metadata from
discarding a prediction or consuming another request.

Assistant text is decoded as a sequence of complete JSON containers rather than sliced from the
first opening brace to the last closing brace. One dictionary surrounded by markdown, thinking text
or invalid brace notes is accepted. Two independently valid dictionaries, a top-level array,
truncated JSON or plain text remain invalid and follow the existing retry/fallback path. Nested
dictionaries and braces inside JSON strings are handled by the standard decoder.

## Why this remains the baseline

The bounded signal interface provides exact evidence validation, deterministic replay, low request
count and a reliable offline fallback. It also isolates retrieval errors from reasoning and
calculation errors.

It is not a permanent restriction. The official House model is Nemotron 3 Super 120B A12B, which
is materially stronger than the 7B model originally assumed. Direct prediction, model-generated
parameters, tool selection, thinking-enabled prompts and hybrid forecasts must be compared against
this baseline on cutoff-safe held-out outcomes before adoption.

## Current measured result

The table below is retained as a historical practice-set diagnostic from the pre-5.2 scorer. Its
coverage-gap composite is not the current official score and must not select new intervals. Scorer
5.2.2 compares point error and mean interval score with each unit's declared naive answer; those
quantities require the organizer's outcome and naive-answer artifacts.

On the 11 retired public practice units with 78 independently reconstructed outcomes:

| Configuration | Calls | Input tokens | Output tokens | Cost | Legacy predictive quality | Mean coverage | Legacy pre-gate composite |
|---|---:|---:|---:|---:|---:|---:|---:|
| Model-free | 0 | 0 | 0 | 0 | 0.3122 | 0.5454 | 0.1058 |
| Nemotron 3 Super free, thinking off | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.5606 | 0.1581 |
| Same saved signals, accepted credit probability support | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6061 | 0.1662 |
| Same signals, plus accepted post-earnings interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6364 | 0.1753 |
| Same signals, plus accepted COT mean reversion and interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus accepted CPI interval floor | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus accepted auction point and interval model | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus EPS YoY interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.7091 | 0.1959 |
| Same signals, plus bank EPS interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.7204 | 0.1939 |

These are diagnostic practice results, not a private leaderboard score. The local official
two-model ensemble path now covers all eleven public units. Six passed before the shared context
candidate and all eleven have a proven passing lower bound after it. Local runtime differences and
the public-only scope remain; see `docs/nli-gate-audit.md`.

For positioning rankings, the deterministic calculator now forecasts five-week change as `-0.2`
times current noncommercial net positioning as a percent of open interest. It accepts an exact
`net_pct_oi` field or selects the latest `net_pct_oi_YYYYMMDD` field, so hidden units are not tied to
the retired example date. Its 90% interval has a fixed 11.3 percentage-point half-width calibrated
only from the historical training/development period.

For CPI components, the existing point formula remains unchanged. The 90% interval uses the larger
of 1.65 times the nine-month historical standard deviation and a 0.35 percentage-point half-width.
The earlier 0.75 floor was selected under the retired coverage-gap metric and reverted after it
worsened scorer 5.2.2 mean interval score on both forward periods.
That historical selection used real-time ALFRED vintages and improved coverage calibration, which
is retained as provenance rather than treated as evidence under the current width-sensitive loss.

For EPS YoY direction tasks with cutoffs on or after 2022-01-01, the point and label still come from
the bounded direction signal and the same five-percent step. Only the interval changes: its
half-width is the larger of 2.75 USD/share and 115% of absolute prior-year-quarter EPS. SEC first-filed
10-Q facts selected this rule on 2020–2021. It produced 93.7% coverage on the inspected 2022–2023
test and 95.8% on the locked 2024–2025 confirmation, versus 25.2% and 24.9% for the previous
interval. Earlier cutoffs retain the prior 15%-of-EPS half-width. The retired public six-row
diagnostic moved from 50% to 100% coverage; points, labels and claims are unchanged.

For bank EPS growth, the seasonal-delta point forecast is unchanged. The 90% interval half-width is
`max(20 percentage points, 0.75 * abs(point forecast))`. A rule with a 100-point floor was briefly
adopted under the retired coverage-gap scorer. Scorer 5.2.2 instead charges both interval width and
miss distance. On the frozen SEC panel, the wide rule's mean interval score was 200.00 versus
133.17 for the restored rule on the 2022-2023 test and 200.08 versus 126.42 on the locked 2024-2025
confirmation split. The wide rule was therefore reverted. Point, label, retrieval and citations did
not change.

For Treasury auctions with cutoffs on or after 2022-01-01, the calculator uses the mean of the last
six same-tenor bid-to-cover ratios. Its 90% half-width is the larger of 0.15 and 1.65 times their
population standard deviation. A Treasury history panel selected the point rule and formerly
selected a 2.5 interval multiplier under the retired coverage-gap metric. Scorer 5.2.2 made the
width cost explicit, so isolated forward tests restored the preceding 1.65 multiplier. Earlier task
cutoffs retain the preceding trend-adjusted point heuristic so later point-selection data cannot
leak backward.

Auction citations now prefer a concise corpus sentence that explicitly reports the recent-six
average only after the calculator independently reproduces that value from the raw rows. A missing
or mismatched summary falls back to the six source rows, and pre-artifact cutoffs always retain the
row citation because their forecast includes the old trend adjustment. On the public auction unit,
this changed official ensemble-NLI faithfulness from 5/7 to 7/7 without changing forecasts or
intervals.

Auction, COT, CPI, EPS YoY and post-earnings calibration now share a fail-closed artifact-availability date
check. If a task predates the data used to select a fitted constant, its family calculator reverts
to the preceding deterministic rule. This does not change any current public output; it prevents a
historical hidden unit from receiving a parameter selected with later outcomes.
Date-suffixed COT entity fields are filtered against the same task cutoff before the latest value is
selected.

For task cutoffs on or after 2026-02-01, CPI core and food use the arithmetic mean of exactly twelve
cutoff-safe monthly component changes. The point rule is limited to those two named series, uses an
exact header match before substring fallback, and retains the preceding latest/median blend when the
history is incomplete. A locked 2024-2025 ALFRED confirmation improved both MAE and RMSE in each
year without reducing direction accuracy. Earlier tasks and all other CPI components are unchanged.

Every prediction preserves up to three compact calculator/model facts and can additionally cite up
to three distinct full BM25 chunks. These context candidates come only from the same cutoff-safe,
entity-scoped retrieval result already used for reasoning. Their exact source slice is rechecked
before output. This fixed cases where a short fact or the beginning of a relevant chunk omitted the
table header or later passage needed by the former prediction-bound NLI diagnostic. It changes no
forecast. The saved 6/11 to 11/11 result is historical evidence under the pre-5.2 gate; current
faithfulness is claim-level.

Unknown regression and ranking targets use a target-aware numeric baseline instead of the median of
every number in an entity row or the row's input position. Field names are matched against the
target name, with unrelated identifiers, dates, market-cap fields and other numeric metadata kept
out of the fallback. A change/delta/growth target with no matching change field uses a neutral zero
rather than reusing a level field. If exactly one non-metadata numeric field is available, it remains
the fallback. When both the target and a candidate field explicitly declare units, incompatible
percent, basis-point or USD units prevent that field from being selected. Missing units are not
inferred. This avoids treating a current curve level in percent as a future curve response in basis
points while preserving compatible and unspecified schemas. The selected field and reason are
retained in the deterministic derivation trace.

Unknown regression and ranking tasks also inspect cutoff-safe dated pipe tables when the entity
schema has no sufficient direct baseline. The parser requires increasing unique dates, one exact
target or series column, a matching explicit unit, finite complete values, and entity-bound documents
when more than one document is visible. It uses only the latest directly stated observation. It does
not derive changes, convert units, cross malformed rows, or infer a column synonym. This path passed
two independent time-forward outcome panels and a remote two-model NLI diagnostic under the
pre-5.2 scorer; setting
`T4_ENABLE_DATED_TABLE_BASELINE=0` disables it for rollback.

For unknown families only, the model packet and BM25 query also retain official scalar table
features whose names could not be known in advance: finite numbers, booleans, categorical strings
and short text. Known families keep their explicit field white lists. The generic packet excludes
`corpus_ref` and nested structures, limits field names to 128 characters, each string to 1,000
characters, all strings together to 6,000 characters and the row to 64 scalar fields. Identity
fields are selected first. This lets hidden schemas use categorical and text columns without making
prompt growth unbounded.

Generic BM25 queries preserve each exact schema identifier and additionally split semantic
camelCase, snake_case and hyphenated names into at most eight natural-language components. When at
least one such semantic identifier exists and no domain rubric applies, those components replace
the broad `results/outlook/growth/...` fallback terms that otherwise dominate lexical scoring. An
opaque schema such as `unseen_family + opaqueTarget + x1` keeps the original fallback rubric
byte-for-byte: common placeholder words including `unseen`, `unknown`, `generic`, `opaque`, `task`,
`family`, `target`, `metric` and `forecast` do not qualify as semantic components. Known-family
queries remain unchanged. The model packet itself is not expanded, so this adds no prompt tokens.

When every generic schema name is opaque, retrieval can instead use task-specific words from the
first 512 prompt characters. Boilerplate, target-type words and duplicates are removed, at least
two useful terms are required, and at most 24 terms are retained. A useful prompt term set replaces
the same broad generic rubric; a template prompt with no task meaning keeps the previous query
byte-for-byte. Known families and generic tasks with semantic schema terms do not enter this path.
The words affect only BM25 retrieval and are not copied into the model packet.

Unknown classification targets keep the same five-level `directional_signal`, then use a bounded
typed-schema mapper to assign allowed labels to positive, neutral and negative roles. It first uses
unambiguous label tokens and event-target negation, then reads at most 8,000 characters of the task
prompt for explicit rules such as “zeta when throughput climbs.” If no unique role is supported, it
falls back to the preceding deterministic allowed-label rule. The mapper neither asks the model for
a final label nor adds a request; known-family label calculators remain isolated.

Family routing uses complete token signatures from `family` and `target.name`, such as
`credit event`, `rate curve`, `bid to cover` and `net positioning change`. A lone ambiguous token or
a substring inside another word does not activate a specialist. This prevents targets such as
`inventory_position_rank`, `credit_eventual_return` or `cotton_yield_rank` from losing their unknown
fields and entering an unrelated calculator. Published signatures and anchored family variants keep
their specialist routes; unmatched tasks use the generic path.

If name routing remains generic, the router makes one second, stricter check against the task's
target type and the fields shared by every roster entity. A specialist is selected only when one
and only one complete known field signature matches. Every required exact or date-prefixed field
must also have a usable value in every entity: `null`, blank strings, non-finite numbers and nested
containers do not count. Partial rows, mixed rosters, wrong target types and signatures matching
more than one specialist remain generic. This recovers renamed versions of known task structures
without allowing a coincidental empty field or substring to choose a domain calculator. Retrieval
scope consumes the same resolved route as prediction.

Family-specific document scopes are dispatched from that same routed family key. An unknown target
whose name incidentally contains `position`, `cot`, `auction`, `revision` or `rate` therefore keeps
every document allowed by its `corpus_ref`; it cannot enter a specialist calculator through one
route while silently losing shared evidence through a second, looser scope rule. CIK scoping remains
a family-independent entity boundary, and known specialists retain their existing series, tenor and
macro-source filters.

Retrieval rubric selection also consumes this routed family key. Incidental strings such as
`inventory_position_rank`, `credit_eventual_return` and `rate_curveball_score` cannot inject COT,
credit or FOMC vocabulary into an otherwise generic query. Published and anchored routes preserve
their previous query bytes, while a renamed task recovered by the strict structural fallback gets
the same specialist rubric as its calculator and document scope.

BM25 tokenization removes sentence-edge punctuation while preserving financial forms such as
`$5.28`, `10%`, `2024-10-31` and `year-over-year`. This makes a query token such as `action_flat`
match the same identifier at the end of a sentence instead of assigning every zero-score query the
first allowed chunk. The same tokenizer instance is used for documents and queries. The change is
shared by known and unknown families and does not alter document scope, cutoff filtering or the
deterministic calculators.

BM25 relevance remains the primary ordering key. When two positive scores are exactly equal, the
newer cutoff-safe `doc_date` wins before the existing document-ID and span tie-breaks. When every
score is zero, documents are stably ordered by recency, so equal or missing dates retain corpus
order. This removes accidental alphabetical or path-order preference for older evidence without
allowing recency to override any relevance-score difference.

The corpus index supports both the flat public layout and entity subdirectories. It recursively
loads cutoff-safe JSON documents, retains each document's path relative to the mounted corpus root,
and resolves an entity's `corpus_ref` against that path before applying family-specific scope rules.
`corpus/` continues to mean the full shared corpus; `corpus/entity-a/` matches only that directory,
not a similarly named `entity-a-old/` directory. Absolute paths, parent traversal, backslash paths
and duplicate `doc_id` values fail closed. This adds no model request or prompt content.

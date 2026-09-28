# Current Track 4 architecture

Last updated: 2026-09-28

The submitted path is a baseline-first bounded workflow:

1. Load the task and cutoff-filter the frozen corpus.
2. Route the target to an isolated family specification.
3. Disable any fitted family parameter whose recorded availability date is later than the task
   cutoff, then hard-scope documents by entity, series, tenor or shared macro source.
4. Retrieve evidence with BM25 and extract explicit numerical parameters deterministically.
5. Compute and atomically write a complete model-free baseline answer.
6. For families that need text judgement, batch up to three entities and ask the House-compatible
   model for five-level signals, explicit numbers and exact quotes.
7. Reject model facts with a foreign document, non-exact quote or invalid value.
8. Re-run the deterministic family calculator with accepted signals and parameters.
9. Normalize rankings, validate the complete answer, and atomically replace the baseline only when
   the enhanced answer is valid.

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
timeouts and a circuit breaker. With three entities per batch, a clean route can enhance up to 75
rows instead of imposing fallback after row 54. Each batch gets two attempts by default. The
cross-batch circuit opens after four consecutive failures, so one malformed batch falls back
without suppressing every later independent batch; a successful response resets the count. Authorization failures,
non-retriable client errors, the request cap and the deadline still stop immediately. A failed API,
invalid JSON or trace-write failure leaves the already-written baseline answer intact.

An HTTP 400 that explicitly identifies a context-length or token-limit overflow is local to that
batch: retrying the same prompt is skipped, but a later shorter batch may still run. An unknown HTTP
400 remains globally non-retriable, and four consecutive explicit context failures still open the
shared circuit. This reacts to the serving route's actual limit without inventing an unpublished
character or token ceiling.

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

On the 11 retired public practice units with 78 independently reconstructed outcomes:

| Configuration | Calls | Input tokens | Output tokens | Cost | Mean predictive quality | Mean coverage | Mean pre-gate composite |
|---|---:|---:|---:|---:|---:|---:|---:|
| Model-free | 0 | 0 | 0 | 0 | 0.3122 | 0.5454 | 0.1058 |
| Nemotron 3 Super free, thinking off | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.5606 | 0.1581 |
| Same saved signals, accepted credit probability support | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6061 | 0.1662 |
| Same signals, plus accepted post-earnings interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3804 | 0.6364 | 0.1753 |
| Same signals, plus accepted COT mean reversion and interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus accepted CPI interval floor | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus accepted auction point and interval model | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.6636 | 0.1878 |
| Same signals, plus EPS YoY interval calibration | 9 | 83,198 | 5,951 | 0 | 0.3864 | 0.7091 | 0.1959 |

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
of 1.65 times the nine-month historical standard deviation and a 0.75 percentage-point half-width.
The higher floor was selected on real-time ALFRED vintages and improved time-forward calibration;
it did not happen to change coverage on the single retired public CPI unit.

For EPS YoY direction tasks with cutoffs on or after 2022-01-01, the point and label still come from
the bounded direction signal and the same five-percent step. Only the interval changes: its
half-width is the larger of 2.75 USD/share and 115% of absolute prior-year-quarter EPS. SEC first-filed
10-Q facts selected this rule on 2020–2021. It produced 93.7% coverage on the inspected 2022–2023
test and 95.8% on the locked 2024–2025 confirmation, versus 25.2% and 24.9% for the previous
interval. Earlier cutoffs retain the prior 15%-of-EPS half-width. The retired public six-row
diagnostic moved from 50% to 100% coverage; points, labels and claims are unchanged.

For Treasury auctions with cutoffs on or after 2022-01-01, the calculator uses the mean of the last
six same-tenor bid-to-cover ratios. Its 90% half-width is the larger of 0.15 and 2.5 times their
population standard deviation. A Treasury history panel selected both choices on 2020-2021 and
confirmed them on 2022-2023 and an untouched January-October 2024 period. Earlier task cutoffs use
the preceding heuristic so the later selection data cannot leak backward. This improved historical
accuracy and calibration but did not change the retired public aggregate diagnostic because that
single auction unit remains at the scorer's zero-skill floor and its coverage stayed 5/7.

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

Every prediction preserves up to three compact calculator/model facts and can additionally cite up
to three distinct full BM25 chunks. These context candidates come only from the same cutoff-safe,
entity-scoped retrieval result already used for reasoning. Their exact source slice is rechecked
before output. This fixes cases where a short fact or the beginning of a relevant chunk omitted the
table header or later passage needed by the prediction-bound NLI hypothesis. It changes no forecast
and raised local public NLI gate passage from 6/11 to 11/11.

Unknown regression and ranking targets use a target-aware numeric baseline instead of the median of
every number in an entity row or the row's input position. Field names are matched against the
target name, with unrelated identifiers, dates, market-cap fields and other numeric metadata kept
out of the fallback. A change/delta/growth target with no matching change field uses a neutral zero
rather than reusing a level field. If exactly one non-metadata numeric field is available, it remains
the fallback. The selected field and reason are retained in the deterministic derivation trace.

For unknown families only, the model packet and BM25 query also retain official scalar table
features whose names could not be known in advance: finite numbers, booleans, categorical strings
and short text. Known families keep their explicit field white lists. The generic packet excludes
`corpus_ref` and nested structures, limits field names to 128 characters, each string to 1,000
characters, all strings together to 6,000 characters and the row to 64 scalar fields. Identity
fields are selected first. This lets hidden schemas use categorical and text columns without making
prompt growth unbounded.

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

BM25 tokenization removes sentence-edge punctuation while preserving financial forms such as
`$5.28`, `10%`, `2024-10-31` and `year-over-year`. This makes a query token such as `action_flat`
match the same identifier at the end of a sentence instead of assigning every zero-score query the
first allowed chunk. The same tokenizer instance is used for documents and queries. The change is
shared by known and unknown families and does not alter document scope, cutoff filtering or the
deterministic calculators.

The corpus index supports both the flat public layout and entity subdirectories. It recursively
loads cutoff-safe JSON documents, retains each document's path relative to the mounted corpus root,
and resolves an entity's `corpus_ref` against that path before applying family-specific scope rules.
`corpus/` continues to mean the full shared corpus; `corpus/entity-a/` matches only that directory,
not a similarly named `entity-a-old/` directory. Absolute paths, parent traversal, backslash paths
and duplicate `doc_id` values fail closed. This adds no model request or prompt content.

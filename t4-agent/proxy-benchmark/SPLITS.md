# Split and leakage policy

## Chronological roles

- `development`: origins whose outcomes may be inspected for implementation and model selection.
- `time_forward_test`: later origins frozen before candidate comparison.
- `confirmation`: a still later period opened once for an adoption decision.
- `future_holdout`: reserved origins not materialized until a later benchmark revision.

Exact years depend on source coverage. A recommended starting layout is development through 2019,
time-forward test in 2021-2023, and confirmation in 2024-2025, leaving a purge gap where release
latency or revisions make it necessary.

The first materialized events, proxy-15 at the 2023-08-02 cutoff and proxy-18 at the 2023-09-29
cutoff, are assigned to `time_forward_test`. Each event's explicit and transformed variants remain
in the same split. They are useful for plumbing and schema-invariance checks, but do not by
themselves satisfy the benchmark's development, confirmation or leave-one-family-out requirements.

## Leave-one-family-out

All origins and both schema variants of the held-out family stay out of prompt design, parameter
selection and calibration. Related near-neighbor controls must be declared before the run. Results
are reported per held-out family and macro-averaged so a large roster cannot dominate.

## Event grouping

Rows produced by the same release, filing date, FOMC event, auction cycle or weekly report belong to
one event group and cannot be split across development and evaluation. Multiple schema variants of
the same economic question always share the same split.

## Availability

For every visible field record both the economic observation date and the first public availability
timestamp. A revised historical value is eligible only from the revision's release time. The hidden
outcome is kept in `reference/` and is never copied into visible features, corpus text, retrieval
metadata, prompts or shipped artifacts.

## Schema variants

Each question must produce:

- `explicit`: descriptive field names and explicit units;
- `transformed`: reordered roster and fields, renamed identifiers, alternative unit encoding, and
  at least one irrelevant scalar or text field.

Transformations must be invertible for the benchmark builder and must not change the target or leak
the outcome.

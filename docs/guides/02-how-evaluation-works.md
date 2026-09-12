# How Evaluation Works (Design Spec)

Source: https://www.agenthon.net/guides/design-spec/ (saved 2026-09-05)

Every track in Agenthon 2026 is judged the same way. Your submission runs under controlled conditions, the run is checked for admissibility, and only then does it earn a score. The full rules, metrics, and thresholds are published before the Development phase opens, so this page describes the shape of the process rather than its final parameters. If a term is unfamiliar, the [glossary](https://www.agenthon.net/guides/glossary/) defines it in plain English.

## What a submission is

An official submission is a container image: a self-contained package holding your code and everything it needs to run. Each image implements a single command, and which command depends on the track — `solve` for T1 Coding, `forecast` for T2 Forecasting, `simulate` for T3 Simulation, and `analyze` for T4 Explainability.

Official runs happen in a sandbox, offline.

## Admissibility comes first

A run is scored only if it was a valid run. That ordering is deliberate: it is there to keep a submission from winning on a technicality, such as producing fast output that ignores the rules or output that no longer means what the task asked for. Checks fall into four categories, applied in order.

- **g0 integrity** — what ran is what you submitted, on the data the task intended.
- **g1 schema** — the output has the form the track requires. Malformed output is a failure, not a low score.
- **g2 cutoff and resources** — the run respected the task's data cutoff and stayed inside its resource limits.
- **g3 domain semantics** — the output makes sense as finance, not merely as data of the right shape.

Fail any gate and the run goes unscored. There's no partial credit for an inadmissible run. Each failure is recorded with a label naming the category, and those labels accumulate into the cross-track failure map: a public picture of where finance agents actually break.

## Scoring admissible runs

Each track has a headline metric, listed with the tracks on the [home page](https://www.agenthon.net/#tracks). The metric is computed over admissible runs only, and the leaderboard reports it with a confidence interval. Think of it as an error bar: it shows how much the number could move if the evaluation had drawn a slightly different set of tasks.

## Keeping results honest

Leakage and cheating are handled by design, not by trust. Tasks carry data cutoffs, so that a submission is judged on what it could have known at the time rather than on the answer it is asked to predict. Held-out material stays sealed. Competition material can carry hidden markers, so material that was copied rather than solved becomes detectable. Leading submissions may be rerun before results are final.

The organizers don't publish every check in detail, since describing them precisely would make them easier to game.

**Where to go next.** The [overview](https://www.agenthon.net/guides/executive-summary/) covers the competition's structure and its public and private repositories, and the [repo guide](https://www.agenthon.net/guides/team-guide/) walks through what you get to work with.

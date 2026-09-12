# Competition Overview (Executive Summary)

Source: https://www.agenthon.net/guides/executive-summary/ (saved 2026-09-05)

Agenthon 2026 is a NeurIPS 2026 Competition Track on verifiable AI for quantitative finance. It asks one question: can an AI agent do real finance work, and can an automated evaluation confirm the answer is right rather than merely plausible? The full rules, metrics, and thresholds are published before the Development phase opens, so read this page as a description of the competition's shape rather than its final parameters.

## What Agenthon 2026 is

Agenthon extends the Alphathon program into its first NeurIPS edition. It keeps Alphathon's four-track structure and its hard finance setting, and adds what a research competition needs to be trusted: sealed held-out data, automated leakage controls, reproducible reruns, and public leaderboards. Leakage means answer material reaching a submission it shouldn't reach, through the data it is given or the data it was trained on.

Every submission makes a claim: this code is correct, this forecast is honest about its uncertainty, this market simulation behaves like the real thing, this prediction rests on the evidence it cites. Agenthon tests the claim before it scores it.

## The four tracks

The four tracks run in parallel and share one evaluation spine. Each has its own verb, headline metric, and domain check.

| Track | Verb | Metric | Gate |
| --- | --- | --- | --- |
| T1 Coding | solve | pass@1 / pass@3 | pytest + financial invariants |
| T2 Forecasting | forecast | CRPS composite | as-of cutoff + calibration |
| T3 Simulation | simulate | events/sec | semantic regression |
| T4 Explainability | analyze | quality + coverage | faithfulness + embargo |

The [glossary](https://www.agenthon.net/guides/glossary/) defines the metric and gate terms used here.

**T1 Coding** — You build an agent that solves quantitative-finance coding tasks. Its work is checked by ordinary unit tests and by financial invariants, the identities a correct answer has to satisfy however the code was written.

**T2 Forecasting** — You build an agent that forecasts financial time series from numeric data plus a time-stamped text corpus. The track measures information uplift: how much the text, and reasoning over it, beats strong text-blind baselines.

**T3 Simulation** — You submit an ABIDES-compatible market simulator that runs faster. Speed counts only if the simulator preserves matching-engine semantics and still reproduces the stylized facts of real markets, the statistical signatures real market data reliably shows.

**T4 Explainability** — You build an agent that predicts labels, values, or rankings for rows of a table, and supports each prediction with citations from a frozen evidence corpus. Predictions come with confidence intervals, and citations have to hold up.

## How a submission is judged

Every official submission is a Docker or other approved container image, a self-contained package holding your program and everything it needs to run. It implements one stable command-line verb for its track, and the organizers run it offline in a sandboxed container.

Scoring is not the first step. A submission first passes a sequence of admissibility gates, g0 to g3, covering integrity, output schema, cutoff and resource rules, and the domain semantics of its track. Each gate is pass or fail, and only a run that clears all four receives a metric and a rank.

Reported scores carry a bootstrap confidence interval, an error bar computed by resampling the evaluation set.

## Public practice, sealed exam

Each track ships as a pair of repositories. The answers stay sealed.

| Public practice | Private exam |
| --- | --- |
| Public-dev and validation units | Private-test held-out units |
| Runnable baselines and smoke scorer | Oracle solutions and final scorer |
| Manifest and canary safety checks | Canary registry and audit logs |

A *unit* is one item of evaluation: a coding task, a forecast, a simulation scenario, an explainability question. A *canary* is a marker planted in sealed material so that leaks become detectable. The smoke scorer in the public repo lets you check your own runs against public material before you send a submission in.

## The three phases

The competition runs in three phases. Dates are on the [timeline on the main page](https://www.agenthon.net/#timeline).

- **Development.** Public repos are open. You build against the public units and score yourself locally.
- **Final.** One final submission per entered track is evaluated on the sealed held-out units.
- **Verification.** Organizers rerun top submissions and review reproducibility.

[How evaluation works](https://www.agenthon.net/guides/design-spec/) goes a level deeper on submissions and the gates.

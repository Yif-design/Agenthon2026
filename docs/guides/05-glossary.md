# Glossary

Source: https://www.agenthon.net/guides/glossary/ (saved 2026-09-05)

Short definitions of the words used across this site and in the competition materials. They are grouped by theme, and each one is meant to carry you through the rest of the site rather than serve as a specification. The full rules, metrics, and thresholds are published before the Development phase opens, so this page describes the shape of the competition rather than its final parameters.

## The competition and its pieces

### Competition and benchmark

A benchmark is a set of tasks with agreed rules for scoring them. A competition adds teams, deadlines, phases, and a ranking. Agenthon 2026 is both: a benchmark for verifiable AI in quantitative finance, run as a NeurIPS 2026 competition.

### Track

One of the four contests inside Agenthon 2026: coding, forecasting, simulation, and explainability. Each track has its own tasks, its own headline metric, and its own pair of repositories.

### Phase

The competition runs in three phases. During Development you practise and iterate with a live leaderboard. The Final phase scores sealed tasks with the leaderboard hidden. Verification reruns leading submissions and reviews reproducibility before results are final. Dates live on the [timeline on the main page](https://www.agenthon.net/#timeline).

### Unit

One item that gets scored on its own: a single coding task, a single forecast, a single simulation scenario, a single analysis question.

### Task card

The short description file that travels with every unit. It tells you what the task asks for. You read task cards; you never edit them.

### Split (public-dev, validation, private-test)

Which pile a unit belongs to. public-dev units are practice material you can score on your own machine. validation units are also public and feed a live leaderboard. private-test units stay sealed and decide the final ranking.

### Baseline

A working solution the organizers publish so you can see what an unremarkable attempt already scores. Every track ships baselines you can run and try to beat.

## Repos, submissions, and the sandbox

### Public repo and private repo

Each track has two repositories. The public one is your practice kit: public-dev and validation units, runnable baselines, a smoke scorer, and the safety checks. The private one belongs to the organizers and holds the held-out units, the reference solutions, and the final scorer.

### Firewall

The rule that answer keys, reference solutions, and expected outputs belong only in the private repo, together with the automated checks and review steps that enforce it.

### Docker image

A self-contained box holding a program and everything it needs, so it behaves the same on any machine. Every official submission ships as a Docker or other approved container image. That is what makes a score a fact about your system rather than about your laptop.

### Submission verb

The single command word the organizers use to start your image: `solve` for coding, `forecast` for forecasting, `simulate` for simulation, `analyze` for explainability. The verb is stable.

### Sandbox

The closed environment a submission is scored in. It runs offline, and the run has to stay inside the cutoff and resource rules its track sets.

### Smoke scorer

A scorer shipped in the public repo so you can grade your own runs before you submit. It grades against public material, so treat it as a check on whether your output is well formed and roughly on track, not as a preview of your final standing.

## Gates, scoring, and staying honest

### Admissibility gate

A check your submission has to clear before anyone looks at its score, much like the technical inspection a car passes before a race. A run is ranked only after it passes every gate. A run that fails a gate is not scored, which is different from scoring zero.

### The gates g0 to g3

The four gates run in order. g0 covers integrity: the files and the image are what they claim to be. g1 covers schema: the output has the shape the track asked for. g2 covers cutoff and resource rules: no future data, and the run stayed inside the limits set for everyone. g3 covers domain semantics: the output makes sense for the subject matter, which is specific to each track.

### Leaderboard

The board showing where teams stand. It updates during Development, goes dark for the Final phase, and is published with confidence intervals once Verification is done.

### Confidence interval

A range around a score that says the true value is probably somewhere in here. Agenthon computes them by resampling units, a standard method called the bootstrap. Without intervals, a gap in the fourth decimal place would look like a real difference between two systems that actually perform the same.

### Reproducibility

Run the same submission again and the result should hold up. The Verification phase reruns leading submissions to check that their scores hold up.

### Data cutoff (embargo)

A date beyond which a unit's inputs may not reach. Everything a submission uses has to have existed by then. A model that predicts a price using that same price has not predicted anything, so the cutoff is what makes a forecast a forecast.

### Leakage

Using information that was not available at the cutoff, by accident or on purpose. A common example is citing a document that was published after the question's cutoff date.

### Canary

A hidden marker placed in competition material. If it later turns up in a submission's output, that points to material being copied rather than solved. It is how contamination gets detected after the fact.

## Headline metrics

### pass@1 and pass@3

The coding track's headline numbers. pass@1 is how often the agent solves a task on its first attempt; pass@3 is how often it solves the task within three attempts. Reporting both gives credit to an agent that finds the right answer some of the time, not only to one that lands it every time.

### CRPS

The continuous ranked probability score grades a probabilistic forecast, meaning a forecast that gives a range of outcomes with probabilities attached rather than a single number. It rewards landing close to what happened and being honest about how uncertain you were. Lower is better, and the forecasting track's headline metric is built on it.

### Events per second

The simulation track's headline metric: how many market events, such as orders, cancels and trades, a simulator gets through each second. Higher is better. Only submissions that pass the gates are ranked, so speed counts for nothing unless the simulation is still behaving correctly.

### Coverage

How often the real outcome actually falls inside the range a submission said it would. A system whose stated ranges keep missing is overconfident; one whose ranges are so wide they always contain the answer is not saying much. Coverage sits alongside answer quality in the Explainability track's headline metric.

### Faithfulness

Whether the claims in an answer are really supported by the sources it cites. An answer that reads well but leans on documents that do not support it is hallucinating, and this is the check that catches it.

### Information uplift

How much better a submission does than a comparable system that ignores the text. This is the question the forecasting track exists to answer: if reading the text corpus does not improve on a strong text-blind model, then the reasoning added nothing.

## Market and document vocabulary

### Limit order book

The live list of every outstanding buy and sell order in a market, organized by price. The highest price a buyer will pay is the best bid, and the lowest price a seller will accept is the best ask.

### Matching engine

The part of an exchange that decides which buy orders meet which sell orders, and at what price. A simulator that matches orders differently from the reference produces different trades and, from there, different prices, no matter how fast it runs.

### ABIDES

An open-source, agent-based market simulator. It models individual traders sending orders into an order book and records what comes out. Simulation-track submissions have to be ABIDES-compatible.

### Stylized facts

Statistical patterns that real markets show over and over: large moves arriving in bursts, extreme moves being more common than a bell curve would suggest, and similar regularities. A simulator can be very fast and still produce output with none of them, which is why they get checked.

### Evidence corpus

The fixed set of documents an Explainability-track submission is allowed to read. It is frozen, so every team works from the same material.

### Citation

A pointer from a claim in an answer back to the document and passage that supports it, like a footnote. Citations make a submission show its work.

# Organization & Repository Guide (Repo Guide)

Source: https://www.agenthon.net/guides/team-guide/ (saved 2026-09-05)

Agenthon 2026 keeps everything it publishes, and everything it seals, inside one GitHub organization. This page is a short tour: what a public practice repo gives you, what stays sealed, and why the four tracks are built the same way. The full rules, metrics, and thresholds are published before the Development phase opens, so read this as the shape of the competition rather than its final parameters.

## How the repositories are laid out

- **One shared main repo.** Whatever the four tracks have in common: the shared task format, the safety checks, and the docs.
- **Four track repo pairs.** Each track has a *public practice repo* that opens during the Development phase, and a *private exam repo* that stays sealed. The pair works the same way for T1 Coding, T2 Forecasting, T3 Simulation, T4 Explainability.
- **One website repo.** The site you're reading, holding documentation and, later, the leaderboard; no tasks or scoring code live there.

## Public practice, sealed exam

The split between a track's two halves is the design decision that matters most. You cannot read the exam.

| Public practice repo | Private sealed exam repo |
| --- | --- |
| Practice tasks you can run | Held-out tasks used for the final ranking |
| Runnable baselines showing a working submission end to end | Reference solutions, held by the organizers |
| A scorer you can run locally on the public tasks | The final scorer and ranking logic |
| Participant docs, templates, and safety checks | Audit material and evaluation logs |

**Practice tasks don't decide the final ranking.** Anything published could already have been memorized by a model, so public tasks are for learning and self-testing. The tasks that decide the final standings are unpublished and stay sealed.

## One format, one evaluation spine

Tasks are packaged the same way across tracks, so a coding task, a forecast, a simulation scenario, and an explainability question all arrive in the same shape. Terms are defined in the [glossary](https://www.agenthon.net/guides/glossary/).

Before anything is scored, a submission has to clear a short sequence of admissibility gates, checks that decide whether it qualifies for a score at all:

`g0 integrity → g1 schema → g2 cutoff and resource rules → g3 domain semantics → score`

A run is ranked only after it clears all four. Miss one and it isn't, and the failure is recorded under its gate. Submissions arrive as Docker images, self-contained packages of your code and everything it needs, and each track's image answers one stable command verb. Because format, gates, and packaging are shared, learning one track's layout teaches you the other three. The [overview](https://www.agenthon.net/guides/executive-summary/) covers what each track asks for.

## How you'll work

Clone the public practice repo for your track, run the baseline to see a complete submission work, then build your own and grade it locally.

Official submissions are made through the competition platform rather than through the repositories, and results appear on this site's [leaderboard](https://www.agenthon.net/#leaderboard). For how evaluation works end to end, see [How evaluation works](https://www.agenthon.net/guides/design-spec/); for the Development, Final, and Verification phase dates, see the [timeline](https://www.agenthon.net/#timeline).

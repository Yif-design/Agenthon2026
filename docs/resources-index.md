# Agenthon 2026 — Resources Index

Collected from https://www.agenthon.net/resources/ (login-only page) and the public guide/rule pages, on 2026-09-05.

## Folder layout

```
Agenthon2026/
├── README.md                          ← this file
├── starter-repos/                     ← the 5 official GitHub starter packages (full git clones)
│   ├── Agenthon2026-public/           ← competition overview: shared task format, safety checks, docs (START HERE)
│   ├── track1-coding-public/          ← T1 Coding — quant-finance coding agents (verb: solve)
│   ├── track2-forecasting-public/     ← T2 Forecasting — reasoning-augmented time series (verb: forecast)
│   ├── track3-simulation-public/      ← T3 Simulation — accelerated ABIDES-compatible market sim (verb: simulate)
│   └── track4-analysis-public/        ← T4 Explainability — evidence-grounded prediction (verb: analyze)
└── docs/                              ← site pages saved as Markdown
    ├── announcements.md               ← login-only Announcements page (starter-package release notes, key dates)
    ├── guides/
    │   ├── 01-competition-overview.md ← executive summary
    │   ├── 02-how-evaluation-works.md ← g0–g3 gates, scoring, anti-leakage
    │   ├── 03-repo-guide.md           ← how the public/private repos are laid out
    │   ├── 04-faq.md
    │   └── 05-glossary.md
    ├── rules-and-policies/
    │   ├── official-competition-rules.md
    │   └── data-and-software-licensing-policy.md
    └── past-events/
        └── alphathon-2025-questions.md
```

## The resources page, verbatim

The Resources page (once logged in) lists exactly five items, all GitHub repositories under the `Agenthon-2026` organization:

| Filter | Title | Link |
| --- | --- | --- |
| All | Starter package — competition overview | https://github.com/Agenthon-2026/Agenthon2026-public |
| T1 Coding | T1 Coding — starter package | https://github.com/Agenthon-2026/track1-coding-public |
| T2 Forecasting | T2 Forecasting — starter package | https://github.com/Agenthon-2026/track2-forecasting-public |
| T3 Simulation | T3 Simulation — starter package | https://github.com/Agenthon-2026/track3-simulation-public |
| T4 Explainability | T4 Explainability — starter package | https://github.com/Agenthon-2026/track4-analysis-public |

Organizers say the repos "will keep evolving" during Development — to refresh a repo later, run `git pull` inside its folder.

## Key dates (America/New_York)

| Phase | Dates |
| --- | --- |
| Registration | 17 Aug – 28 Sep 2026 |
| Development (now) | 28 Aug – 28 Sep 2026 |
| Final (one submission per track, sealed data) | 29 Sep – 12 Oct 2026 |
| Verification | 13 – 25 Oct 2026 |
| NeurIPS, Atlanta | 9 – 13 Dec 2026 |

## Tracks at a glance

| Track | Verb | Metric | Gate |
| --- | --- | --- | --- |
| T1 Coding | `solve` | pass@1 / pass@3 | pytest + financial invariants |
| T2 Forecasting | `forecast` | CRPS composite | as-of cutoff + calibration |
| T3 Simulation | `simulate` | events/sec | semantic regression |
| T4 Explainability | `analyze` | quality + coverage | faithfulness + embargo |

## Other useful links

- Home / timeline / leaderboard: https://www.agenthon.net/
- Guides index: https://www.agenthon.net/guides/
- Announcements (login): https://www.agenthon.net/announcements/
- My Team (login): https://www.agenthon.net/teams/my-team/
- Terms: https://www.agenthon.net/terms/ · Privacy: https://www.agenthon.net/privacy/
- Contact: admin@agenthon.net

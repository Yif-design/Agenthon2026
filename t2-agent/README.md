# t2-agent — Agenthon 2026 Track 2 submission

Our own code lives here, separate from the organizers' repo (`../starter-repos/track2-forecasting-public`),
so `git pull` on the starter repo never conflicts with our work.

## Layout

```
t2agent/
  cardio.py     read card.toml / panels / text index (input handling only)
  engine.py     statistical backbone: regime-blended joint block-bootstrap Monte Carlo
  knobs.py      the Adjustments contract (drift / vol multiplier / scenarios) the text stage fills in
  llm.py        stdlib OpenAI-compatible chat client (MODEL_ENDPOINT / MODEL_NAME from env, no tools)
  textstage.py  documents -> signal cards (one call per doc) -> scenario mixture (one call) -> Adjustments
  rationale.py  forecast_rationale.md writer (ledger of every adjustment, established vs inferred)
  cli.py        the `forecast` verb; `get_adjustments()` picks file / --no-text / LLM
scripts/
  run_all_units.py   run every practice unit through the agent and the official smoke scorer
  compare_runs.py    text vs no-text: how much the centre moved and the width changed, per cell
Dockerfile
```

## Local use

```bash
cd t2-agent
pip install -e .                                   # gives you the `forecast` command
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public --only F4 --limit 3
```

Single unit, by hand:

```bash
U=../starter-repos/track2-forecasting-public/units/t2-EXAMPLE-ust-curve-1m
forecast --panels $U --text $U/text --asof 2024-06-28 --out out/forecast.parquet --info out/info.json
python ../starter-repos/track2-forecasting-public/scoring/scoring.py score --card $U/card.toml --forecast out/forecast.parquet
```

## Docker

```bash
docker build -t t2-agent .
docker run --rm --network=none -v "$PWD/$U":/input:ro -v "$PWD/out":/output t2-agent \
  forecast --panels /input --text /input/text --asof 2024-06-28 --out /output/forecast.parquet
```

## Local model for development (Ollama on a Mac)

The official sandbox only exposes an organizer-hosted OpenAI-compatible endpoint via
`MODEL_ENDPOINT` / `MODEL_NAME`. Locally, Ollama plays that role:

```bash
brew install ollama
OLLAMA_CONTEXT_LENGTH=16384 ollama serve        # in its own terminal; default context is too small
ollama pull qwen2.5:7b                            # ~4.7 GB, fits 16 GB RAM, good at JSON
export MODEL_ENDPOINT=http://localhost:11434/v1 MODEL_NAME=qwen2.5:7b
```

If the Ollama menu-bar app is already running, set the context length for it instead:
`launchctl setenv OLLAMA_CONTEXT_LENGTH 16384`, then quit and restart the app.

Then:

```bash
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public --only EXAMPLE
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public            # text, cached in runs/_textcache
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public --no-text --runs runs_notext
python scripts/compare_runs.py runs runs_notext
```

The text stage never raises: no endpoint / bad JSON / budget exhausted all degrade to the neutral
backbone with a note in the rationale (a unit that errors costs 4.0, a neutral one ~1.0).

## Where the text stage plugs in (phase 3)

`t2agent/cli.py::get_adjustments()` returns an `Adjustments` object (see `knobs.py`). The LLM
module should read `unit.text_dir`, call `MODEL_ENDPOINT` / `MODEL_NAME` from the environment,
and return scenarios with `drift` (in horizon-sd units), `vol_mult`, `evidence` doc_ids and the
`established` flag. `Adjustments.validate()` refuses a scenario that narrows the distribution
without an established fact. For offline testing, pass `--adjustments some.json`:

```json
{"scenarios": [
  {"name": "hawkish-hold", "weight": 0.6, "drift": {"UST_2Y": 0.3}, "vol_mult": {}, "evidence": ["fomc-statement-2024-06-12"], "established": false},
  {"name": "cut-priced-in", "weight": 0.4, "drift": {"UST_2Y": -0.2}, "vol_mult": {"UST_2Y": 1.2}, "evidence": ["fomc-minutes-2024-05-22"], "established": false}
]}
```

## Local scoring with reconstructed outcomes (dev only)

The organizers ship no realized values, but 94/104 practice answers can be reconstructed from
sibling units' panels (they say so themselves). That turns the blind loop into a measured one:

```bash
python scripts/build_realized.py --repo ../starter-repos/track2-forecasting-public      # -> dev/realized/
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public --baseline --runs runs_base --realized-dir dev/realized
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public --no-text  --runs runs_notext --realized-dir dev/realized
python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public            --runs runs_text   --realized-dir dev/realized
python scripts/evaluate.py runs_base/summary.csv runs_notext/summary.csv runs_text/summary.csv
```

`evaluate.py` reports every run as a per-card ratio to the reference (the organizers' Gaussian
random walk), averaged equal-weight — the same shape as the leaderboard number (1.0 = no better
than the reference) — plus PIT calibration (`in90` should be ≈ 0.90, `below05` ≈ 0.05).
`dev/` is git- and docker-ignored: nothing under it may ever reach the image or the agent.

Backbone status (2026-09-07, 94 cards): mean ratio **0.928** vs the reference; F1 0.75, F2 0.99,
F3 0.83, F4 1.06. The suite is shock-heavy (even the reference has `in90` 0.66), which is what the
text stage exists to fix: with documents flagging an event it raises `stress_prob` and `vol_mult`.
Engine knobs for experiments: `T2_P_STRESS` (0.12), `T2_VOL_VV` (0.25), `T2_WIDTH` (1.15).

## Submitting to the Development leaderboard (CodaBench)

The submission is a zip holding one file, `submission.json`, that names a **publicly pullable,
digest-pinned, linux/amd64** image. Steps, from an Apple-silicon Mac:

```bash
# 1. sign in to GitHub Container Registry (a classic PAT with write:packages / read:packages)
echo $GHCR_TOKEN | docker login ghcr.io -u <github-user> --password-stdin

# 2. build for x86-64 and push (TEXT=off = model-free deterministic forecaster, models: [])
docker buildx build --platform linux/amd64 --provenance=false --sbom=false   --build-arg TEXT=off -t ghcr.io/<github-user>/t2-agent:v0.1-notext --push .

# 3. read the digest of what was pushed
docker buildx imagetools inspect ghcr.io/<github-user>/t2-agent:v0.1-notext   # "Digest: sha256:..."

# 4. make the package PUBLIC on github.com (Packages → t2-agent → Package settings → Change visibility)
#    then prove an anonymous client can pull it:
bash scripts/check_pullable.sh <github-user>/t2-agent sha256:<digest>

# 5. build + validate + zip the descriptor (team id from your CodaBench profile)
python scripts/make_submission.py --team-id <TEAM_ID>   --image ghcr.io/<github-user>/t2-agent --digest sha256:<digest> --out submissions/v0.1-notext.zip

# 6. upload submissions/v0.1-notext.zip on the CodaBench competition page (Development phase)
```

For an `api` submission (text stage on) build with `--build-arg TEXT=on` and pass
`--models models.json` listing the house model as the organizers publish it
(`{"name","version","training_cutoff","access":"api","revision"}`).

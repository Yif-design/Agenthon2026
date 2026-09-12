# Agenthon 2026 Track 2 submission image.
#   docker build -t t2-agent .
#   docker run --rm --network=none -v <unit>:/input:ro -v $PWD/out:/output t2-agent \
#       forecast --panels /input --text /input/text --asof 2024-06-28 --out /output/forecast.parquet
# Build for the fleet (x86-64) from an Apple-silicon Mac:
#   docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
#       -t ghcr.io/<user>/t2-agent:v0.1 --push .
# TEXT=off bakes a model-free deterministic forecaster (models: [] in submission.json);
# TEXT=on (default) runs the LLM text stage against MODEL_ENDPOINT / MODEL_NAME from the harness.
FROM python:3.13-slim-bookworm
LABEL qfbench2.interface_version="2.0"
ARG TEXT=on
ENV T2_TEXT=${TEXT}
LABEL agenthon.track="T2" agenthon.agent="t2agent"

ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "numpy==2.1.3" "pandas==2.2.3" "pyarrow==18.1.0"

WORKDIR /opt/t2agent
COPY pyproject.toml ./
COPY t2agent ./t2agent
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 1000 runner
USER runner
WORKDIR /work
# `forecast` is on PATH via [project.scripts]; no ENTRYPOINT so the harness's verb resolves.

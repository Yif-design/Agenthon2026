FROM python:3.13-slim

LABEL qfbench2.interface_version="2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app
COPY pyproject.toml README.md ARTIFACT_PROVENANCE.md ./
COPY t4agent ./t4agent
RUN python -m pip install --no-cache-dir .

# The evaluation harness replaces CMD with:
# analyze --task ... --corpus ... --out ...
CMD ["analyze", "--help"]

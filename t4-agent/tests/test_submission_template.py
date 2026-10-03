from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_development_submission_template_uses_c5_image_object() -> None:
    descriptor = json.loads((ROOT / "submission.dev.template.json").read_text())
    image = descriptor["image"]

    assert set(image) == {"registry", "repository", "digest"}
    assert image["registry"] == "ghcr.io"
    assert image["repository"] == "yif-design/agenthon2026-t4"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"])
    assert descriptor["interface_version"] == "2.0"
    assert descriptor["competition_id"] == "agenthon2026-analysis-dev"
    assert descriptor["track"] == "analysis"
    assert descriptor["phase"] == "dev"
    assert descriptor["category"] == "api"
    assert "team_id" not in descriptor
    assert "descriptor_digest" not in descriptor


def test_dockerfile_declares_matching_interface_label() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert 'LABEL qfbench2.interface_version="2.0"' in dockerfile

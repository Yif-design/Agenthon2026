"""Build, validate and zip `submission.json` for CodaBench.

    python scripts/make_submission.py --team-id <TEAM_ID> \
        --image ghcr.io/<user>/t2-agent --digest sha256:<64 hex> \
        [--phase dev] [--category byo-small|api] [--models models.json] [--license Apache-2.0] \
        [--out submission.zip]

* `--digest` is the digest of the pushed image (from `docker buildx imagetools inspect <ref>` or
  the `docker push` output), prefixed `sha256:`.
* `--category byo-small` + no `--models` = the model-free deterministic forecaster (the toolkit's
  own fixture uses exactly that, and `models: []` is the honest disclosure).
  `--category api` + `--models models.json` = calls the house endpoint; the JSON is a list of
  {name, version, training_cutoff, access, revision}.
* The descriptor is sealed with the toolkit's JCS digest and re-parsed with
  `SubmissionDescriptor.from_mapping` before it is zipped, so what is zipped is what validates.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import zipfile

try:
    from qfbench2_common.contracts.descriptor import SubmissionDescriptor, seal_descriptor_digest
except ImportError:
    sys.exit("qfbench2-common not installed: pip install \"qfbench2-common @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git@v2.3.1#subdirectory=common\"")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--team-id", required=True)
    p.add_argument("--image", required=True, help="registry/repository, e.g. ghcr.io/yefei/t2-agent")
    p.add_argument("--digest", required=True, help="sha256:<64 hex> of the pushed image")
    p.add_argument("--phase", default="dev", choices=["dev", "final", "verification"])
    p.add_argument("--category", default=None, help="byo-small (model-free) or api (house endpoint)")
    p.add_argument("--models", default=None, help="JSON file: list of model disclosures")
    p.add_argument("--license", default="Apache-2.0")
    p.add_argument("--image-access", default="public", choices=["public", "organizer_mirror"])
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("submission.zip"))
    a = p.parse_args()

    if not re.fullmatch(r"sha256:[0-9a-f]{64}", a.digest):
        sys.exit(f"--digest must look like sha256:<64 hex>, got {a.digest!r}")
    registry, _, repository = a.image.partition("/")
    if not repository or "." not in registry and registry != "localhost":
        sys.exit("--image must be <registry>/<repository>, e.g. ghcr.io/user/t2-agent or docker.io/user/t2-agent")
    models = json.loads(pathlib.Path(a.models).read_text(encoding="utf-8")) if a.models else []
    category = a.category or ("api" if models else "byo-small")

    body = {
        "schema_version": "1.0.0",
        "interface_version": "2.0",
        "competition_id": f"agenthon2026-forecasting-{a.phase}",
        "team_id": a.team_id,
        "track": "forecasting",
        "phase": a.phase,
        "category": category,
        "image": {"registry": registry, "repository": repository, "digest": a.digest},
        "image_access": a.image_access,
        "models": models,
        "license": a.license,
    }
    sealed = seal_descriptor_digest(body)
    try:
        desc = SubmissionDescriptor.from_mapping(sealed)      # raises ContractError if anything is off
    except Exception as exc:  # noqa: BLE001
        if models or "at least 1" not in str(exc):
            raise
        # The pinned toolkit (v2.3.1) still demands >= 1 model row even though C5 1.1.0 documents
        # `[]` for a model-free submission. Declare the deterministic engine itself, honestly, so
        # the descriptor validates with the same toolkit the ingestion uses.
        print(f"note: toolkit refused models=[] ({exc}); declaring the deterministic engine as the single row")
        body["models"] = [{
            "name": "t2agent-deterministic-engine",
            "version": "0.1.0",
            "training_cutoff": "none-no-learned-weights",
            "access": "local",
            "revision": a.digest.split(":")[1][:12],
        }]
        sealed = seal_descriptor_digest(body)
        desc = SubmissionDescriptor.from_mapping(sealed)
    text = json.dumps(sealed, indent=2) + "\n"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("submission.json", text)                    # one file, at the root, nothing else
    (a.out.with_suffix(".json")).write_text(text, encoding="utf-8")
    print(text)
    print(f"validated ({desc.track}/{desc.phase}/{desc.category}, {len(desc.models)} model(s)); wrote {a.out} and {a.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

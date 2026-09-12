#!/usr/bin/env bash
# Anonymous pullability check for a GHCR image (what the ingestion sees — no credential).
#   bash scripts/check_pullable.sh <user>/t2-agent sha256:<digest>
set -euo pipefail
REPO="${1:?repo like user/t2-agent}"; DIGEST="${2:?sha256:<64 hex>}"
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:${REPO}:pull&service=ghcr.io" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json' \
  "https://ghcr.io/v2/${REPO}/manifests/${DIGEST}")
echo "HTTP ${CODE}"
[ "${CODE}" = "200" ] && echo "OK: anonymously pullable" || echo "NOT pullable anonymously — make the package public (GitHub → Packages → Package settings → Change visibility)"

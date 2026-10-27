#!/usr/bin/env bash
# Playwright (Chromium) contre l'image finale, sur un reseau Docker dedie.
# Les rapports et captures restent dans tests/e2e/results (artefacts de la CI).
set -euo pipefail
IMAGE="$1"
NET="cct-e2e-$$"
APP="cct-e2e-app-$$"
cleanup() { docker rm -f "$APP" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker network create "$NET" >/dev/null
docker run -d --name "$APP" --network "$NET" --network-alias cct-web --read-only --tmpfs /tmp \
  -e ALLOWED_HOSTS=127.0.0.1,localhost,cct-web "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$APP" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=3)" >/dev/null 2>&1; then break; fi
  sleep 2
done
docker build -t cct-e2e:ci tests/e2e
mkdir -p tests/e2e/results && chmod 0777 tests/e2e/results
docker run --rm --network "$NET" -e E2E_BASE_URL=http://cct-web:8000 \
  -v "$PWD/tests/e2e/results:/e2e/results" cct-e2e:ci

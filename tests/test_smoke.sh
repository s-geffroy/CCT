#!/usr/bin/env bash
# Tests de bout en bout sur le VPS, sans rien executer sur l'hote :
#   1. typecheck + vitest du frontend (conteneur devtools, depot monte) ;
#   2. pytest dans l'image finale + Stockfish reel (service tests) ;
#   3. Playwright/Chromium contre le service app reconstruit (service e2e).
# Le build de l'image rejoue aussi typecheck/vitest : un echec casse le build.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== frontend : typecheck + vitest"
sudo appctl run devtools sh -c 'cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run typecheck && npm test'

echo "== backend : pytest dans l'image (Stockfish reel)"
sudo appctl run tests

echo "== e2e : Playwright contre l'application reconstruite"
sudo appctl rebuild
# Sortie capturee d'abord : avec pipefail, `grep -q` ferme le tube et le
# SIGPIPE recu par appctl ferait echouer le test a tort.
healthy=no
for _ in $(seq 1 40); do
  status=$(sudo appctl status 2>/dev/null || true)
  if grep -q '(healthy)' <<<"$status"; then healthy=yes; break; fi
  sleep 3
done
[ "$healthy" = yes ] || { echo "ECHEC : app non saine"; exit 1; }
sudo appctl run e2e

echo "OK : frontend, backend et e2e verts"

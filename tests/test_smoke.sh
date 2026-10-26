#!/usr/bin/env bash
# Tests de bout en bout sur le VPS, sans rien executer sur l'hote :
#   1. typecheck + vitest du frontend (conteneur devtools, depot monte) ;
#   2. pytest dans l'image finale + Stockfish reel (service tests).
# Le build de l'image rejoue aussi typecheck/vitest : un echec casse le build.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== frontend : typecheck + vitest"
sudo appctl run devtools sh -c 'cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run typecheck && npm test'

echo "== backend : pytest dans l'image (Stockfish reel)"
sudo appctl run tests

echo "OK : frontend et backend verts"

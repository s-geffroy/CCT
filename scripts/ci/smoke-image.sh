#!/usr/bin/env bash
# Smoke de l'image finale, dans les conditions du compose Windows : systeme de
# fichiers en lecture seule, /tmp en tmpfs, volume nomme sur /data, port local.
# Usage : scripts/ci/smoke-image.sh IMAGE [VERSION_ATTENDUE]
set -euo pipefail
IMAGE="$1"
EXPECTED_VERSION="${2:-}"
NAME="cct-smoke-$$"
VOLUME="cct-smoke-data-$$"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; docker volume rm "$VOLUME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" --read-only --tmpfs /tmp --security-opt no-new-privileges:true \
  -v "$VOLUME:/data" -p 127.0.0.1:18765:8000 "$IMAGE" >/dev/null

ready=""
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18765/api/v1/health/ready >/dev/null 2>&1; then ready=yes; break; fi
  sleep 2
done
if [ -z "$ready" ]; then docker logs "$NAME" | tail -50; echo "ECHEC : /health/ready ne repond pas"; exit 1; fi

meta=$(curl -fsS http://127.0.0.1:18765/api/v1/meta)
echo "meta : $meta"
echo "$meta" | grep -q '"name":"Stockfish 19' || { echo "ECHEC : moteur Stockfish 19 absent"; exit 1; }
if [ -n "$EXPECTED_VERSION" ]; then
  echo "$meta" | grep -q "\"app_version\":\"$EXPECTED_VERSION\"" || { echo "ECHEC : version attendue $EXPECTED_VERSION"; exit 1; }
fi
[ "$(docker exec "$NAME" id -u)" = "10001" ] || { echo "ECHEC : le serveur ne tourne pas en utilisateur non privilegie"; exit 1; }
# Une vraie recherche (profondeur 10), puis la sauvegarde utilisee par backup.ps1.
pos=$(curl -fsS -H 'Content-Type: application/json' -d '{"source":"fen","fen":"r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"}' http://127.0.0.1:18765/api/v1/positions)
pid=$(echo "$pos" | sed -E 's/.*"id":"([0-9a-f-]{36})".*/\1/')
job=$(curl -fsS -H 'Content-Type: application/json' -d "{\"position_id\":\"$pid\",\"target_depth\":10,\"multipv_max\":3}" http://127.0.0.1:18765/api/v1/analysis-jobs)
jid=$(echo "$job" | sed -E 's/^\{"id":"([0-9a-f-]{36})".*/\1/')
state=""
for _ in $(seq 1 60); do
  state=$(curl -fsS "http://127.0.0.1:18765/api/v1/analysis-jobs/$jid" | sed -E 's/.*"state":"([a-z_]+)".*/\1/')
  [ "$state" = "complete_depth" ] && break
  sleep 1
done
[ "$state" = "complete_depth" ] || { echo "ECHEC : analyse non terminee ($state)"; exit 1; }
docker exec "$NAME" python -m app.backup create | grep -q '"ok": true' || { echo "ECHEC : sauvegarde"; exit 1; }
docker stop -t 20 "$NAME" >/dev/null
docker logs "$NAME" 2>&1 | grep -q "arret" || { echo "ECHEC : arret propre (SIGTERM) non journalise"; exit 1; }
echo "OK : image finale saine (lecture seule, moteur, analyse, sauvegarde, arret propre)"

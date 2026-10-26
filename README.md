# Chess Calculation Trainer (cct)

Application locale d'entrainement au calcul des variantes d'echecs : on
calcule (mentalement ou en construisant un arbre), puis on confronte ses
variantes a un arbre de reference **selectif** produit par Stockfish 19.
Aucune promesse d'exhaustivite : jusqu'a 20 premiers coups, profondeur cible
21, budgets bornes.

- Specification : `specs/Chess_Calculation_Trainer_D1-D7_GitHubActions_Installation_1Clic_v2.zip`
- Arbitrages et ecarts a la spec : `docs/decisions.md`
- Rapport du Lot 0 (versions reelles, API constatees, bench moteur) : `docs/lot0-report.md`
- Rapport du Lot 1 (SQLite, migrations, instantanes de position) : `docs/lot1-report.md`
- Rapport du Lot 2 (seances B/C, immuabilite, anti-spoiler) : `docs/lot2-report.md`

Cible finale : Windows 11 x64 + Docker Desktop/WSL 2, image GHCR
`linux/amd64` et installation par double-clic (Lot 6). **Ce VPS sert au
developpement et aux tests uniquement** : aucun port publie.

## Structure

| chemin | contenu |
|---|---|
| `backend/app/` | FastAPI : `api/`, `domain/` (FEN, PGN, coups, instantanes), `engine/` (UCI, analyse, bench), `persistence/` (SQLite, migrations) |
| `backend/tests/` | pytest, dont integration avec le vrai Stockfish |
| `backend/Dockerfile` | multi-stage : `stockfish` (sf_19 universal), `frontend`, `pydeps`, `runtime`, `test`, `devtools` |
| `frontend/` | React 19 + TypeScript + Vite ; `react-chessboard`, `react-arborist` via adaptateurs |
| `tests/e2e/` | Playwright (Chromium reel, 1280 et 1024 px) contre le service `app` |
| `compose.yaml` | stack du VPS (`app`, `tests`, `e2e`, `devtools`) |

## Cycle de developpement (VPS)

Rien ne s'execute sur l'hote : tout passe par `appctl`.

```bash
tests/test_smoke.sh                 # vitest/typecheck, pytest dans l'image, Playwright
sudo appctl validate
sudo appctl rebuild
sudo appctl status                  # le conteneur 'app' doit passer healthy
sudo appctl logs                    # 'moteur demarre : Stockfish 19 ...'
```

Outils ponctuels :

```bash
# lockfiles (reseau sortant via cct-dev)
sudo appctl run devtools sh -c 'cd backend && uv lock'
sudo appctl run devtools sh -c 'cd frontend && npm install --package-lock-only'
# banc d'essai Stockfish (budget en secondes par recherche)
sudo appctl run tests python -m app.engine.bench --budget 120
```

## Licence

GPL-3.0-or-later (Stockfish et python-chess sont GPL ; voir `docs/decisions.md`).

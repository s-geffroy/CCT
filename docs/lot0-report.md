# Lot 0 — Rapport : dependances, API reelles, moteur

Date : 26/10/2026. Environnement : VPS Linux, AMD EPYC 9354P (4 vCPU visibles,
AVX2/AVX-512), Docker via `appctl`. Aucun test Windows (gate manuelle **non
validee**).

## Versions figees (verifiees a la source le 26/10/2026)

| Composant | Version | Licence | Ou c'est fige |
|---|---|---|---|
| Stockfish | `sf_19` (publie le 05/09/2026), archive sha256 `519b653d…2d76` | GPL-3.0-or-later | `backend/Dockerfile` (ARG) |
| Reseau NNUE | `nn-1a298aa575a0.nnue` (98,5 Mo), sha256 `1a298aa5…2dfc2` | (sous licence Stockfish/networks) | `backend/Dockerfile` (ARG) |
| python-chess | 1.11.2 | GPL-3.0+ | `backend/pyproject.toml`, `uv.lock` |
| FastAPI / Uvicorn | 0.162.0 / 0.54.0 | MIT / BSD-3 | idem |
| pytest / httpx2 | 9.1.1 / 2.16.0 | MIT / BSD-3 | groupe `dev` |
| Python | 3.13 (`python:3.13-slim-trixie`) | PSF | Dockerfile |
| Node | 24 LTS (`node:24-trixie-slim`) | MIT | Dockerfile |
| uv | 0.13.5 | MIT/Apache-2.0 | Dockerfile |
| React / React DOM | 19.3.1 | MIT | `frontend/package.json`, `package-lock.json` |
| react-chessboard | 5.12.1 (dep. `@dnd-kit/core` 6.3.1) | MIT | idem |
| react-arborist | 4.0.1 (+ `react-dnd` 16.0.1, `react-window` 1.8.11) | MIT | idem |
| chess.js | 1.4.0 (installe, non utilise a ce stade) | BSD-2-Clause | idem |
| Vite / Vitest / TypeScript | 8.3.5 / 5.0.5 / 7.0.2 | MIT / MIT / Apache-2.0 | idem |

Images de base epinglees par **tag** a ce stade ; l'epinglage par digest est
reporte au Lot 6 (release).

## Constats sur les API reelles

### Stockfish 19

- Nouvelle cible `ARCH=x86-64-universal` : un binaire, 8 variantes (x86-64 de
  base jusqu'a AVX-512 VNNI), choix a l'execution. **Resout la portabilite
  Windows** sans imposer AVX2 (risque « critique » du registre, doc 17).
- Un seul reseau NNUE (plus de couple big/small).
- **Piege trouve et corrige** : sans `#embed` (GCC 14 de Debian trixie), le
  Makefile incorpore le reseau via `hexdump`. Si `hexdump` est absent
  (`debian:trixie-slim`), le binaire embarque un reseau **vide sans aucune
  erreur** ; il ne plante qu'au premier `go`. Le premier build passait son
  bench uniquement parce que le `.nnue` traînait dans le repertoire courant.
  Corrections : `bsdextrautils` installe, taille du dump controlee (> 100 Mo),
  bench + `go depth 8` lances depuis un repertoire **vide**.
- Une position illegale (roi capturable) fait **planter** Stockfish
  (`Unsupported position`). `analyse_root` refuse toute position invalide
  avant le moteur (T06).
- Bench de build (1 thread, `bench 16 1 10`) : ~1,06 M noeuds/s.

### python-chess 1.11.2

- `engine.analysis(board, Limit(depth=…), multipv=k)` en flux, `multipv` passe a
  l'appel (pas de `configure({'MultiPV':…})`) : conforme au doc 06.
- `info` peut porter `lowerbound`/`upperbound` : un palier n'est atteste que par
  une info exacte (`exact_depth`).
- `chess.pgn.read_game` remonte les coups illegaux dans `game.errors` et
  abandonne le reste de la variante : on les expose en `warnings`.

### react-chessboard 5.12.1 (API `options`)

- `onPieceDrop({piece, sourceSquare, targetSquare}) => boolean` est
  **synchrone** : impossible d'attendre la validation serveur dans le rappel.
  L'adaptateur refuse le depot visuel, envoie le coup, et la FEN renvoyee par
  le serveur fait foi (leger « retour » visuel ; option : prevalidation
  `chess.js` au Lot 5).
- **Aucune boite de promotion** integree : fournie par `ChessboardAdapter`, sans
  dame implicite.
- `SparePiece` exige un `ChessboardProvider` commun avec `<Chessboard />` ;
  `allowDragOffBoard` permet de retirer une piece. Codes de pieces `wP`/`bK`.
- `fenStringToPositionObject` exporte : utile pour l'editeur.
- **Aucune navigation clavier** : la saisie SAN textuelle reste la voie
  accessible (Lot 5).
- Utilise `ResizeObserver` (stub necessaire sous jsdom).

### react-arborist 4.0.1

- `disableDrag`, `disableDrop`, `disableEdit` : reorganisation interdite comme
  demande. Embarque tout de meme `react-dnd` + backend HTML5 (inutilises).
- Virtualise via `react-window` : hauteur **fixe** obligatoire.
- Un arbre de coups naif imbrique chaque coup sous le precedent (40 coups = 40
  niveaux). Convention retenue (`adapters/variationTree.ts`) : suite principale
  au meme niveau, variantes indentees sous le coup qu'elles remplacent.
- Comparaison avec une vue **PGN en ligne** (`components/MoveText.tsx`) : les
  deux sont dans le spike (bascule « PGN en ligne / Arbre »). Recommandation
  provisoire : PGN en ligne par defaut (plus compact, lecture naturelle),
  arborist pour les grands arbres de reference (repli, virtualisation). A
  confirmer par un essai utilisateur reel.

## Ce que le spike demontre

| Chaine | Preuve |
|---|---|
| FEN -> validation serveur -> echiquier | `test_domain.py`, `test_api.py`, `ChessboardAdapter` (64 cases rendues) |
| PGN a variantes, commentaires, NAG -> arbre | `test_pgn_*`, `variationTree.test.ts`, `MoveText` |
| Coup -> legalite + SAN serveur | `test_play_*`, `/api/v1/moves/play` |
| Promotion explicite, roque, prise en passant | `test_promotion_must_be_explicit`, `test_castling_and_en_passant` |
| Editeur pieces libres -> FEN | `placementFromPosition`, `applyEditorDrop` |
| MultiPV <= 20 racines distinctes, < 20 sans doublon, terminal = 0 ligne | `test_engine.py` (vrai Stockfish) |
| Mat type, point de vue Blancs, budget sans faux depth 21 | `test_engine.py` |
| Host/Origin/CORS, taille de requete, XSS commentaires | `test_api.py`, `MoveText` |

Resultats : **pytest 43/43** (image finale, Stockfish reel), **vitest 9/9**,
**typecheck OK**, **Playwright 16/16** (8 scenarios x 1280 et 1024 px, Chromium
reel), image construite, conteneur `app` sain.

### Navigateur reel (Playwright 1.64.0, Chromium)

Valide dans un vrai navigateur, contre le conteneur `app` :

- glisser-deposer `e2-e4` (capteur dnd-kit) -> appel `/moves/play` -> SAN et
  position venant du serveur ;
- coup illegal glisse : message `ILLEGAL_MOVE`, echiquier intact ;
- promotion : boite de choix, `e8=N` sans dame implicite ;
- editeur : pieces libres posees, piece retiree en la deposant hors de
  l'echiquier, FEN mise a jour, explication serveur des roques incoherents ;
- PGN : navigation dans les deux vues (en ligne, arborist), commentaire
  `<script>` affiche en texte et non execute ;
- aucune requete hors de l'origine de l'application (fonctionnement hors ligne).

Constats :

- **Editeur trop haut a 1024 x 768** : les pieces libres (~85 px chacune) et le
  formulaire depassent la hauteur ; la rangee noire sort de l'ecran des qu'on
  pose une piece en bas. A traiter au Lot 5 (pieces libres plus petites ou de
  part et d'autre de l'echiquier).
- **Nom d'hote `app` inutilisable** dans Chromium : HTTPS force par HSTS
  preload (`.app`). Alias reseau `cct-web` pour les tests.

## Non valide a ce stade (dit sans detour)

- Navigateurs autres que Chromium (Firefox, Edge reel sous Windows), tactile.
- Navigation clavier sur l'echiquier : absente de react-chessboard (Lot 5).
- Aucun test Windows, aucune CI GitHub (Lot 6).
- Images de base non epinglees par digest.

## Banc d'essai moteur

`sudo appctl run tests python -m app.engine.bench --budget 180 --threads 2 --hash 128`
— Stockfish 19 universal, 2 threads, Hash 128 Mo, conteneur limite a 2 CPU /
1 Go (pic observe ~320 Mo), AMD EPYC 9354P (Zen 4).

Temps (s) pour **attester** chaque palier sur **toutes** les lignes demandees :

| Position | coups legaux | MultiPV | d8 | d12 | d16 | **d21** | statut |
|---|---:|---:|---:|---:|---:|---:|---|
| position initiale | 20 | 1 | 0,4 | 0,4 | 0,5 | **1,2** | depth_met |
| position initiale | 20 | 20 | 0,1 | 0,8 | 3,2 | **20,3** | depth_met |
| FEN utilisateur (doc 14) | 42 | 1 | 0,0 | 0,0 | 0,3 | **1,9** | depth_met |
| FEN utilisateur (doc 14) | 42 | 20 | 0,0 | 0,3 | 8,2 | **58,1** | depth_met |
| Kiwipete | 48 | 1 | 0,0 | 0,0 | 0,3 | **1,8** | depth_met |
| Kiwipete | 48 | 20 | 0,1 | 0,8 | 8,3 | **22,4** | depth_met |
| finale (12 coups) | 12 | 1 | 0,0 | 0,0 | 0,1 | **0,2** | depth_met |
| finale (12 coups) | 12 | 12 | 0,0 | 0,0 | 0,4 | **31,4** | depth_met |

Debit : 1,2 a 1,4 M noeuds/s (milieu de jeu), 3,7 M en finale.

### Lecture

- **Racine** : MultiPV 20 a profondeur 21 tient en 20–60 s ici. Sur un PC
  Windows ordinaire via WSL 2 (CPU portable, 2 threads), compter
  vraisemblablement 2 a 3 fois plus, soit ~1–3 min : le budget de **300 s**
  par defaut est realiste. L'inquietude C.1 de la revue etait trop pessimiste
  pour la racine.
- **Paliers** : d8/d12 arrivent en moins d'une seconde, d16 en ~3–8 s. Le
  retour progressif (D7) est donc tangible des les premieres secondes.
- **Le cout MultiPV n'est pas lineaire** : x10 a x30 par rapport au MultiPV 1,
  et non x20 attendu ; la finale a 12 coups est la plus couteuse en relatif
  (l'arbre de recherche d'une finale est profond).
- **Expansion** : un noeud en MultiPV 1 a d21 coute ~2 s ici ; MultiPV 3 est a
  mesurer au Lot 4. Avec 80 noeuds et 300 s, compter ~4 s par noeud : faisable
  ici, juste sur un portable. A recalibrer sur la machine Windows de reference.
- Ces chiffres valent pour **ce** CPU. Le doc 11 l'exige : aucun seuil en
  secondes universel ; refaire le bench sur le PC Windows cible (W12).

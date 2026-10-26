# Arbitrages sur le dossier de spécifications D1–D7 v2

Source : `specs/Chess_Calculation_Trainer_D1-D7_GitHubActions_Installation_1Clic_v2.zip`.
Revue du 26/10/2026. Ces arbitrages précisent le dossier sans changer D1–D7.
Le doc 14 demande de les consigner ici.

## Décisions du propriétaire

- **Rôle de ce VPS : dev et test seulement.** L'application ne sert personne ici. Les
  tests HTTP tournent dans le conteneur, et `exposure: none` est conservé. Toute
  exposition future passe par `app-exposure.py`, jamais par des labels écrits à la main.
- **Périmètre : spec intégrale** (lots 0 à 6, Lot 4 complet inclus). On livre d'abord la
  verticale testée (position → B/C → recherche → révélation → débriefing → sauvegarde).

## Adaptations au dépôt

1. `compose.yaml` racine = stack VPS (build local, réseau `internal`, volume `cct_*`), seul
   fichier lu par `appctl`. Le compose Windows de production va dans
   `packaging/windows/compose.yaml` ; le workflow le copie depuis cet emplacement.
2. Le squelette `src/worker.py` sera remplacé par le serveur FastAPI. Le healthcheck HTTP
   (`/api/v1/health/live`) remplace le battement `/tmp/heartbeat`. `CLAUDE.md` est à mettre
   à jour en même temps.
3. Rien ne tourne sur l'hôte : lint et tests passent par un stage `test` du Dockerfile
   multi-stage. Le Makefile garde `docker` direct pour la CI GitHub.
4. Limites VPS relevées à environ 1 Go / 2 CPU pour Stockfish. Tests moteur à budgets
   réduits.
5. Image : `ghcr.io/s-geffroy/cct` (dépôt `s-geffroy/CCT`).

## Corrections apportées au dossier

| Réf. | Problème | Correction |
|---|---|---|
| B1 | Seuil Windows 22000 (doc 16) contre 22631 (modèle) | un seul seuil : 22631 (Win11 23H2) |
| B2 | `TotalPhysicalMemory < 8GB` rejette les PC « 8 Go » | seuil 7,5 Gio, avertissement en dessous de 8 |
| B3 | `start.ps1`/`stop.ps1` relancent `verify.ps1` complet | contrôle léger : Docker joignable |
| B4 | update, backup et uninstall n'ont pas de lanceur `.cmd` | ajouter `METTRE_A_JOUR.cmd`, `SAUVEGARDER.cmd`, `DESINSTALLER.cmd` |
| B5 | healthcheck Docker sur `/ready` : moteur KO → conteneur unhealthy | Docker sur `/live` ; l'installateur lit `/ready` et signale « moteur indisponible » |
| B6 | release publiée alors que le package GHCR est privé et Windows non testé | `gh release create --draft`, puis passage Public, pull anonyme, W12, publication manuelle |
| B7 | `packages: write` aussi sur PR et push main (G02) | job `test` read-only, job `publish` sur tags seulement |
| B8 | pas de test de port occupé dans `install.ps1` | ajouter le test avant `up` |
| B9 | `OUVRIR.cmd` lancé depuis le dossier extrait échoue | le README pointe vers le raccourci / `%LOCALAPPDATA%` ; message explicite |
| B10 | `draft → active` sans endpoint ; `reviewed` jamais déclenché | session créée `active` ; `reviewed` posé à la génération du rapport |
| B11 | versions non vérifiées (SF 19, actions v4–v7, react-chessboard 5.12.1) | revérifier au Lot 0 ; épingler les actions par SHA |

## Risques maintenus (périmètre intégral)

- **Depth 21 × MultiPV 20 sur 2 threads.** Bench du Lot 0 (`docs/lot0-report.md`) :
  20–60 s sur le VPS, ~1–3 min estimées sur un portable Windows. Le budget de 300 s à
  la racine tient. Le risque se déplace vers l'expansion (80 nœuds / 300 s) : à
  mesurer au Lot 4 et sur le PC Windows de référence.
- **Lot 4.** Les seuils de diagnostic ne sont pas calibrés et le corpus de 20 positions
  doit être annoté à la main. Jusque-là, verdict `unverified` par défaut ; aucun verdict
  fort.
- **Arbre UI.** Le spike du Lot 0 compare `react-arborist` à un rendu PGN inline
  indenté ; D3 impose un arbre, pas un widget précis.

## Autres arbitrages

- Licence du code original : **GPL-3.0-or-later**. `python-chess` (GPL-3.0) et Stockfish
  imposent déjà ce choix.
- Anti-spoiler : filtrage côté serveur conservé. La menace localhost réelle (DNS
  rebinding, CSRF) est couverte par la validation Host/Origin.
- Doc 16 : les modèles `templates/` font foi ; les exemples du doc 16 sont caducs.
- Gates W01–W12 : **non validées** tant qu'aucun Windows 11 réel n'a été testé.

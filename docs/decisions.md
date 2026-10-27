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
- **Lot 4.** Les seuils de diagnostic restent des valeurs de conception (`review.POLICY`,
  versionnée). Le corpus de 21 positions (`backend/tests/corpus/`) est annoté par
  l'implémenteur sur des écarts nets (mat, pièce perdue, finale nulle) ; il **doit être
  relu par un joueur** avant toute conclusion pédagogique. Hors corpus, la prudence vient
  de la règle : pas de verdict sans évaluation exacte à profondeur ≥ 12, et une réfutation
  exige un changement de classe (gagnant / équilibré / perdant).
- **Arbre UI.** Le spike du Lot 0 compare `react-arborist` à un rendu PGN inline
  indenté ; D3 impose un arbre, pas un widget précis.

## Autres arbitrages

- Licence du code original : **GPL-3.0-or-later**. `python-chess` (GPL-3.0) et Stockfish
  imposent déjà ce choix.
- Anti-spoiler : filtrage côté serveur conservé. La menace localhost réelle (DNS
  rebinding, CSRF) est couverte par la validation Host/Origin.
- Doc 16 : les modèles `templates/` font foi ; les exemples du doc 16 sont caducs.
- Gates W01–W12 : **non validées** tant qu'aucun Windows 11 réel n'a été testé.

## Lot 4 : arbre de référence et débriefing

- **Nœud = travail sur la racine + un chemin.** Un nœud de l'arbre n'est pas un nouvel
  instantané de position : c'est un travail d'analyse portant sur la position de
  l'exercice et une suite UCI (`analysis_jobs.node_path_json`). La règle anti-spoiler
  (échiquier de la racine) s'applique donc telle quelle à tout l'arbre, et le moteur
  reçoit l'historique complet (répétitions comprises).
- **Routes** : `/api/v1/reference-trees` (création en étude libre, liste par position),
  `/reference-trees/{id}` et `/reference-trees/{id}/expand`, plutôt que
  `/positions/{id}/reference-tree` et `/positions/{id}/expand` (doc 08) : une position
  peut porter plusieurs arbres (séances successives, réglages différents).
- **Deux enveloppes** (nœuds et temps) de mêmes plafonds : exploration automatique
  (meilleurs coups, défenses critiques) et branches du joueur. Sans cela, la
  préparation lancée pendant que le joueur calcule épuiserait les 80 nœuds et les 300 s
  avant la soumission, et ses propres coups resteraient non vérifiés.
- **Politique d'expansion** (doc 06) : à la racine les 3 meilleurs coups ; côté adverse
  la meilleure défense, plus les réponses à moins de 150 cp d'elle (au plus 3) ; côté du
  joueur la meilleure riposte ; jusqu'à 4 demi-coups. MultiPV 3 aux nœuds, profondeur
  21, 30 s par nœud au plus. `score_swing` n'est pas encore une raison de sélection.
- **Équité de la file** : vieillissement de +1 de priorité par minute d'attente.
- **Évaluation d'un coup** : de préférence la ligne de la recherche du parent (même
  recherche que les alternatives, donc comparable) ; sinon l'analyse ciblée de la
  position après le coup (profondeur locale + 1). Les transpositions sont annotées,
  jamais utilisées comme preuve.
- **`reviewed`** : posé quand le rapport est stable (arbre terminé) et enregistré, y
  compris avec la qualité « référence insuffisante ». Une réanalyse demandée ensuite
  produit un nouveau rapport (révision d'arbre différente) ; l'ancien reste en base.
- **Taxonomie non implémentée telle quelle** : `evaluation_mismatch` ne compare que
  « avantage blanc / noir / égalité » ; « initiative », « attaque », « incertain » sont
  déclarés non comparables.

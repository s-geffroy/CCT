# Lot 1 — Rapport : noyau domaine, persistance, positions

Date : 26/10/2026. DoD du doc 13 : « depuis un PGN avec variante, on choisit un
noeud, visualise sa position et conserve le contexte » — **atteinte et testee
de bout en bout** (Playwright, avec rechargement de la page).

## Ce qui a ete livre

### Persistance SQLite (`backend/app/persistence/`)

- Base `/data/app.sqlite` sur le volume `cct_data` ; **WAL actif sur le volume**
  (verifie dans les logs : `journal wal`), `busy_timeout` 5 s, cles etrangeres
  actives, transactions courtes `BEGIN IMMEDIATE`.
- Migrations versionnees deterministes : fichiers `NNNN_nom.sql`, numerotation
  contigue verifiee, une transaction par migration, table `schema_migrations`.
  Choix : bibliotheque standard plutot qu'Alembic (le doc 02 autorise les deux) :
  pas d'ORM, pas de dependance de plus pour une douzaine de tables.
- **Sauvegarde automatique avant toute mise a niveau** d'une base existante, via
  l'API `backup()` de SQLite (jamais une copie de fichier d'une base en WAL) :
  `/data/backups/app-v<ancienne>-<horodatage>.sqlite`.
- Refus de demarrer sur une base plus recente que l'application (retour arriere
  applicatif sans restauration impossible, doc 10).
- Migration `0001` : `pgn_imports` (entree brute conservee + sha256), `games`,
  `game_nodes`, `positions`, `settings`.

### Instantanes de position (`backend/app/domain/snapshots.py`)

- Un instantane = FEN + **contexte de regles** : FEN de depart, suite UCI rejouee
  et verifiee par python-chess (ou `null` = historique inconnu), et indicateur
  `history_complete` (vrai seulement depuis la position initiale standard).
- Consequence visible : une triple repetition est **reclamable** depuis un noeud
  PGN, et **ne l'est pas** pour la meme FEN isolee (deux instantanes distincts).
- Empreinte `context_key` (sha256 de variante, FEN de depart, historique ou
  espace `history_unknown`, FEN, version de politique) : **meme contexte = meme
  instantane** (POST idempotent : 201 puis 200). Constate en conditions reelles :
  4 instantanes apres plusieurs executions completes de la suite e2e.
- Trois sources : `pgn` (noeud d'une partie importee), `fen` (avec les coups
  eventuellement joues sur l'echiquier depuis cette FEN), `editor` (sans
  historique, avertissement explicite).
- Historique SAN calcule par le serveur pour l'affichage.

### PGN importe

- Import persiste en une transaction (entree brute + parties + noeuds) ; plusieurs
  parties par fichier, choix de la partie dans l'UI.
- Numero de coup et camp **lus sur l'echiquier** : une partie avec en-tete FEN
  commencant aux Noirs au coup 23 s'affiche `23... Kd7 24. e4` (bug latent du
  Lot 0, qui deduisait le numero du demi-coup).
- Arbre **pagine** : `GET /games/{id}/tree?root=&max_nodes=` (parcours en
  largeur, `frontier` des noeuds non developpes) ; l'UI affiche « … suite non
  chargee » et complete a la demande, dans les deux vues.

### API ajoutee

| Methode | Chemin | Contrat |
|---|---|---|
| `POST` | `/api/v1/games/import-pgn` | 201, parties persistees (sans l'arbre complet) |
| `GET` | `/api/v1/games`, `/api/v1/games/{id}` | liste paginee, metadonnees |
| `GET` | `/api/v1/games/{id}/tree` | sous-arbre borne depuis `root` |
| `POST` | `/api/v1/positions` | `source` = `pgn` / `fen` / `editor` ; 201 ou 200 si deja connu |
| `GET` | `/api/v1/positions`, `/api/v1/positions/{id}` | liste paginee, instantane |

`/health/ready` controle aussi la base ; `/meta` donne la version du schema.

### Interface

- Module « Positions » : onglets FEN / PGN / Editeur, bouton « Retenir cette
  position », panneau **Position retenue** (FEN, trait, origine, statut de
  l'historique, coups, nullite reclamable, avertissements) distinct de la
  position affichee — les deux reperes demandes au doc 04 — et liste des
  positions enregistrees.
- L'editeur ne se ferme que si le serveur accepte la position.

## Tests

| Suite | Resultat |
|---|---|
| pytest (image finale, Stockfish reel) | **59/59** (+16 : migrations, sauvegarde, rollback, instantanes, API, redemarrage) |
| vitest | **13/13** |
| Playwright (Chromium, 1280 et 1024 px) | **26/26**, stable sur 3 executions consecutives |
| T14 (persistance `appctl down` / `up`) | memes instantanes avant/apres, aucune migration rejouee |

## Constats et corrections pendant le lot

- **dnd-kit bloque tout clic sur le document 50 ms apres un depot**
  (`AbstractPointerSensor.detach`). Sans effet pour un humain, mais cause de
  tests instables : les aides e2e attendent apres un depot.
- **Glisser pendant l'animation de react-chessboard (150 ms) est ignore** : les
  tests attendent la piece et la fin de l'animation.
- **Message d'erreur hors de l'ecran** quand l'editeur fait defiler la page :
  l'alerte est desormais collee en haut de l'ecran.
- `<label>` englobant un `<select>` : le nom accessible inclut l'option choisie ;
  `aria-label` explicite.
- Coups du PGN en ligne colles dans le texte (`1. c4e5`) : separateur reel ajoute
  (lecture d'ecran, copier-coller).

## Reste ouvert

- Editeur trop haut a 1024 x 768 (constat du Lot 0, Lot 5).
- Export JSON/PGN des positions et sessions : prevu avec les sessions (Lots 2 et 4).
- Pas encore de suppression de position ni d'import (doc 05 : apres validation stricte).

# Lot 2 — Rapport : seances B et C sans moteur apparent

Date : 26/10/2026. DoD du doc 13 : « calcul et sauvegarde possibles hors ligne
avec moteur desactive ; aucune fuite » — **atteinte** : toute la suite pytest
des seances tourne moteur desactive, et aucune reponse avant revelation ne
contient de donnee moteur (scanner cote API et cote navigateur).

## Ce qui a ete livre

### Seances (`/api/v1/sessions`)

- Etats `active -> submitted -> revealed` et `active -> abandoned` ; `reviewed`
  reserve au Lot 4. Une seance est creee directement `active` (arbitrage B10).
- Chaque mutation exige `expected_revision` ; revision perimee -> **409
  `REVISION_CONFLICT`** avec la revision courante (double clic, deux onglets).
- **Mode C (arbre)** : ajout d'un coup sous un parent (UCI ou SAN, SAN calcule
  par le serveur, doublon refuse), suppression de sous-arbre, commentaire,
  appreciation humaine (6 valeurs du doc 04), promotion en suite principale.
- **Annuler / retablir cote serveur** : chaque etat de l'arbre est conserve
  (`tree_states`) ; une nouvelle modification abandonne la branche de
  retablissement, comme dans un editeur.
- **Mode B (mental)** : aucun coup sur l'echiquier (409 `MENTAL_MODE`), notes et
  variantes ecrites facultatives, masquables. **Les variantes ne sont analysees
  qu'a la soumission** : signaler un coup illegal pendant la seance serait deja
  un diagnostic de calcul. Au debriefing, chaque ligne est rejouee ; le premier
  coup impossible est localise (`coup 3 « Ke3 »`), rien n'est invente au-dela.
- Soumission : autoevaluation facultative (candidats, menace principale,
  estimation), duree, **instantane de tentative** ; seance sans trace marquee
  `no_trace` (P10 : pas de score objectif invente).
- Export JSON versionne (`cct-session` v1) et PGN de l'arbre (variantes et
  commentaires), historique pagine `GET /api/v1/history`.

### Immuabilite garantie par la base (migration 0002)

Triggers SQLite, en plus des controles applicatifs :

- `attempt_snapshots` : ni UPDATE ni DELETE ;
- `user_nodes`, `tree_states` : aucune ecriture si la seance n'est plus `active` ;
- contenu de la seance (notes, variantes, autoevaluation, curseur) fige apres
  soumission ;
- transitions d'etat interdites hors du graphe ci-dessus.

Teste en ecrivant directement dans la base : chaque tentative de modification
d'une seance soumise echoue (`test_database_itself_refuses_changes_after_submission`).

### Anti-spoiler

- Une seule fonction, `session_view()`, decide de ce qui sort ; avant la
  revelation, la section `reference` **n'existe pas** (pas meme vide).
- `backend/tests/spoiler.py` : scanner reutilisable des cles interdites (doc 08 :
  `pv`, `score`, `best_move`, `rank`, `multipv`, `mate`, `depth`, `reference`,
  `lines`…). Un « client hostile » lit toutes les reponses de seances B et C
  avant revelation (creation, mutations, lecture, export, positions,
  historique, meta) : aucune cle interdite.
- Le meme controle tourne **dans le navigateur** (Playwright) sur toutes les
  reponses reseau de la seance.
- Garde-fou pour le Lot 3 : un test echoue si une route d'analyse apparait dans
  l'OpenAPI sans etre couverte par ce controle.
- Nommage : les variantes ecrites du joueur s'appellent `written_lines`, pour ne
  jamais ressembler aux `lines` moteur.

### Interface

- Navigation par URL (`#/positions`, `#/session/<id>`, `#/history`) : un
  rechargement reprend la seance en cours depuis le serveur.
- Depuis la position retenue : « Calcul mental (B) » ou « Construire mon arbre (C) ».
- Seance C : echiquier jouable a la position du coup selectionne (le coup ajoute
  devient le coup selectionne : on enchaine la variante), saisie SAN, annuler /
  retablir, commentaire, appreciation, promotion, suppression confirmee.
- Seance B : echiquier fige (orientation retournable), saisie masquable.
- Chronometre **facultatif**, masque par defaut. Abandon confirme.
- Debriefing : variantes ecrites numerotees et coup illegal localise,
  autoevaluation, notes, statut de la reference (« pas encore disponible »).

## Tests

| Suite | Resultat |
|---|---|
| pytest (image finale) | **76/76** (+17 : seances B/C, conflits, annuler/retablir, triggers, client hostile, export, reprise apres redemarrage) |
| vitest | **14/14** |
| Playwright (Chromium, 1280 et 1024 px) | **32/32**, deux executions consecutives |
| Migration reelle v1 -> v2 sur `cct_data` | sauvegarde `app-v1-…sqlite` creee avant, schema v2, WAL |

## Corrections pendant le lot

- PGN en ligne : espacement des variantes (`( 1. d4  )1... e5` -> `( 1. d4 ) 1... e5`),
  utile aussi au copier-coller.
- Variantes du debriefing numerotees comme l'historique (`1. e4 e5 2. Nf3`).

## Reste ouvert

- Les seances ne lancent encore aucune analyse : `start_analysis_in_background`
  (doc 08) arrive avec l'orchestrateur du Lot 3.
- Diagnostics de calcul (taxonomie du doc 07) : Lot 4.
- Editeur trop haut a 1024 x 768 : Lot 5.

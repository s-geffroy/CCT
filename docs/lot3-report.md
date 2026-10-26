# Lot 3 — Rapport : orchestrateur Stockfish progressif

Date : 26/10/2026. DoD du doc 13 : « etat stable sous interruptions, crash et
redemarrage ; resultats corrects et traces » — **atteinte et testee avec le vrai
moteur** (annulation, mort du processus Stockfish, redemarrage du serveur).

## Ce qui a ete livre

### Planificateur (`backend/app/engine/scheduler.py`)

- Une boucle asyncio dans l'unique processus Uvicorn, un seul Stockfish, une
  file **persistante** (SQLite) prise par priorite puis anciennete :
  demande explicite d'etude (100) avant preparation de fond d'une seance (50).
- File bornee (`MAX_QUEUED_JOBS`, 20) : au-dela, **429 `TOO_MANY_JOBS`**.
- Chaque recherche part de l'echiquier **rejoue avec son historique** : le
  moteur recoit `position fen … moves …` et connait les repetitions passees.
- Paliers 8/12/16/21 : chaque palier atteste (toutes les lignes, info exacte,
  sans borne) est enregistre comme point stable ; les infos intermediaires
  restent en memoire et sont diffusees au plus une fois par seconde.
- Ecritures d'un travail serialisees dans un thread dedie : un palier ne peut
  jamais etre enregistre apres le resultat final.
- **Annulation** idempotente : en file, immediate ; en cours, l'evenement d'arret
  stoppe Stockfish meme s'il n'emet rien. Mesure : arret en moins de 5 s (T10).
- **Panne du moteur** : processus tue en plein calcul -> travail `failed`,
  moteur redemarre, travail suivant termine normalement, `/ready` revient (T12).
- **Redemarrage du serveur** : un travail reste `running` devient `interrupted`.
- **Le planificateur ne s'arrete jamais sur une erreur de travail** : il la
  journalise, marque le travail en echec et continue (voir « Incident » plus bas).

### Cache et deduplication

- Cle de cache : contexte de la position (FEN de depart + historique + FEN,
  doc 05), identite du moteur (version, empreinte du reseau NNUE, threads,
  hash), profondeur cible, MultiPV, version de politique.
- Demande equivalente en file ou en cours -> meme travail ; resultat deja a la
  profondeur cible -> reutilise (200, `reused: true`).

### Anti-spoiler : une seule regle

> Les resultats d'un travail ne sont lisibles que si **aucune seance non
> revelee** (`active` ou `submitted`) ne porte sur **le meme echiquier**
> (pieces, trait, roques, prise en passant), quel que soit le demandeur.

Elle couvre, testes un par un :

- le travail de reference d'une seance, avant la revelation ;
- l'etude libre demandee pendant la seance (refus **409 `SESSION_IN_PROGRESS`**),
  y compris via un autre instantane du meme echiquier (editeur) ;
- une etude **deja calculee avant** la seance : masquee tant que la seance est
  ouverte, de nouveau visible apres abandon ;
- le flux SSE : avant revelation, l'etat seul (`analysis-status` :
  `progress_category`, `is_ready`).

Le test « client hostile » lit, pendant que la reference se calcule et une
fois prete, toutes les reponses de la seance et des routes d'analyse (REST et
SSE) : aucune cle interdite. Un test echoue si une route d'analyse apparait sans
etre couverte par ce controle.

Constat en conditions reelles : lors des essais, des seances restees ouvertes
(executions de tests interrompues) ont **effectivement masque** la reference
d'une autre seance sur la position de depart — la regle a fonctionne comme
prevu ; les tests e2e abandonnent desormais ces restes avant de commencer.

### API

| Methode | Chemin | Contrat |
|---|---|---|
| `POST` | `/api/v1/analysis-jobs` | etude libre (profondeur 8..32, MultiPV 1..20, budget 5..1800 s) ; 201 / 200 si reutilise ; 409, 422, 429, 503 |
| `GET` | `/api/v1/analysis-jobs?position_id=` | travaux de la position (vue complete ou etat seul) |
| `GET` | `/api/v1/analysis-jobs/{id}` | idem |
| `POST` | `/api/v1/analysis-jobs/{id}/cancel` | idempotent |
| `GET` | `/api/v1/analysis-jobs/{id}/events` | SSE : etat courant complet a chaque connexion, battement 15 s, fermeture apres `max_seconds` (EventSource se reconnecte) |

Seances : `start_analysis_in_background` (vrai par defaut) ; avant revelation,
`preparation` = etat seul ; apres, `reference` = travail complet. Si le moteur
etait indisponible au debut, la reference est lancee a la revelation.

Chaque ligne : rang, 1er coup (UCI + SAN serveur), PV UCI et SAN, profondeur
annoncee et **profondeur attestee**, score type au point de vue des Blancs
(`cp` / `mate`, bornes conservees), statut (`provisional`, `depth_met`,
`budget_exhausted`…). Couverture annoncee : `all_root_moves` ou
`top_moves_only` — jamais « exhaustif ».

### Interface

- Etude libre (A) depuis la position retenue : reglages, Analyser / Arreter,
  **tableau des variantes sous l'echiquier**, paliers atteints, debit, phrase de
  couverture, navigation coup par coup dans une variante.
- Seance : indicateur « reference en preparation / prete » suivi en direct (SSE,
  etat seul) ; apres revelation, tableau de la reference sous l'echiquier.
- Evaluations au point de vue des Blancs, `M+n` / `M-n`, `≈` si provisoire,
  `≥` / `≤` pour les bornes ; legende explicite profondeur ≠ longueur de PV.

## Mesures (VPS, 2 threads, hash 128 Mo)

Reference d'une seance (partie italienne, 33 coups legaux, MultiPV 20) :
paliers 8 / 12 / 16 / 21 atteints a **0,1 / 1,4 / 4,2 / 19,8 s**, 20 lignes a
profondeur 21 attestee, ~1,5 M noeuds/s.

## Tests

| Suite | Resultat |
|---|---|
| pytest (image finale, vrai Stockfish) | **89/89** (+13 : cycle de vie, cache, annulation, budget, crash, redemarrage, file bornee, SSE, anti-spoiler x3, moteur desactive) |
| vitest | **17/17** |
| Playwright | **36/36**, deux executions consecutives |

## Incident pendant le lot (et ce qui a change)

1. **Test bloque, conteneur orphelin.** Le `TestClient` attend la fin d'un flux
   SSE ; un flux de travail masque restait ouvert indefiniment. Corrections :
   flux SSE bornes (`max_seconds`, reconnexion transparente) ; plafond dur
   `timeout --signal=KILL` dans les commandes des images `test` et `e2e` ;
   `faulthandler_timeout` (pile d'appels apres 120 s) ; `globalTimeout`
   Playwright. **Reste** : le conteneur `cct-tests-run-46b3e3064f3e`, lance avant
   ces plafonds, ne peut pas etre arrete par `appctl` (voir ci-dessous).
2. **File d'analyse figee en silence.** Un `TypeError` (arguments nommes non
   transmis lors de l'ecriture finale) tuait la tache du planificateur sans
   trace. Correction du bug, et surtout : la boucle journalise et survit a toute
   erreur d'un travail.

## Reste ouvert

- Conteneur orphelin a supprimer par un administrateur :
  `docker rm -f cct-tests-run-46b3e3064f3e` (inactif, ~220 Mo).
- Arbre de reference ramifie (defenses critiques, branches du joueur) et
  diagnostics : Lot 4.
- Reglages moteur (threads, hash) modifiables depuis l'interface : Lot 5.

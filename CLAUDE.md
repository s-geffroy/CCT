# Regles du projet cct

Ce fichier est lu par Claude Code au demarrage. Il fixe les regles non
negociables de ce projet sur ce VPS.

## Ce projet n'expose rien (sur ce VPS)

Le produit est une application web locale pour Windows (FastAPI + UI React +
Stockfish, voir `specs/` et `docs/decisions.md`). **Sur ce VPS, il ne sert
qu'au developpement et aux tests** : aucun port publie, pas de labels
Traefik, pas de reseau edge, `exposure: none` dans `app.yaml` -- et appctl
refuse l'un sans l'autre.

Il n'y a donc pas d'URL a ouvrir en fin de tache. Ce qui tient lieu
d'interface : **les tests** (`appctl run tests`), **les logs** et **l'etat de
sante** du conteneur.

Si l'application doit un jour etre joignable (tailnet), ca se declare :
`sudo /opt/infra/scripts/app-exposure.py cct --set app=tailnet --port
app=8000`, qui met `app.yaml` et les labels a jour ensemble. Ne bricole jamais
les labels a la main.

## Le serveur

- Un seul processus Uvicorn (`--workers 1`) : le planificateur Stockfish vit
  dans ce processus. Ne jamais en lancer plusieurs.
- Un seul processus Stockfish, jamais partage sans `EngineManager.lock`.
- **Une panne moteur ne tue pas le serveur** : `/api/v1/health/live` reste vert,
  `/api/v1/health/ready` passe en 503. Les modes B/C marchent sans moteur.
- Le healthcheck Docker lit `/live` (le processus repond), pas `/ready`.
- **SIGTERM s'honore** : l'arret passe par le `lifespan` FastAPI, qui quitte
  Stockfish proprement dans `stop_grace_period`.
- Aucune donnee moteur (coup, score, PV, rang) ne sort par l'API ou le SSE
  d'une seance non revelee : le filtrage est cote serveur, et teste.
  Regle unique (`analysis_repo.is_visible`) : les resultats d'un travail ne
  sont lisibles que si aucune seance `active`/`submitted` ne porte sur le meme
  echiquier. Toute nouvelle route d'analyse doit passer par `job_view()` et
  etre ajoutee au test client hostile (un test echoue sinon).
  La meme regle couvre l'arbre de reference (`tree_view()`, echiquier de sa
  racine : un noeud est un travail sur la racine + un chemin), le debriefing
  (`/sessions/{id}/review`) et l'export JSON d'une seance deja revelee.
- Le planificateur (`engine/scheduler.py`) ne doit jamais s'arreter sur une
  erreur de travail : il la journalise, marque le travail `failed`, continue.
  Ses abonnes (`on_finished`, `on_idle`) non plus : l'arbre de reference
  (`services.ReferenceService`) avance par eux, dans le thread d'ecriture.
- Arbre de reference : deux enveloppes de memes plafonds (`TREE_*`), l'une pour
  l'exploration automatique, l'autre pour les branches du joueur, sinon la
  preparation pendant la seance epuiserait la verification de ses coups.
- Debriefing (`domain/review.py`) : pur, sans moteur ; une evaluation n'est une
  preuve qu'exacte et a profondeur >= `min_verdict_depth`. Tout changement de
  seuil change `POLICY["version"]` et passe par le corpus
  (`backend/tests/corpus/positions.json`, un test par cas).

## Services Compose

| service | role | lancement |
|---|---|---|
| `app` | l'image livree (`runtime`) | `sudo appctl rebuild` |
| `tests` | image `test` : pytest dans l'image finale | `sudo appctl run tests` |
| `e2e` | Playwright/Chromium contre `app` (alias `cct-web`) | `sudo appctl rebuild && sudo appctl run e2e` |
| `devtools` | Node + Python + uv sur le depot monte, reseau `cct-dev` | `sudo appctl run devtools sh -c '...'` |

`devtools` sert a generer les lockfiles et a lancer typecheck/vitest ; rien ne
s'execute sur l'hote, meme si `node` ou `python3` y sont presents.

Les conteneurs `appctl run` sont plafonnes (`timeout --signal=KILL` dans les
CMD des images `test` et `e2e`) : `appctl down` ne les arrete pas, un test bloque
laisserait sinon un conteneur orphelin. Garder ce plafond.

`e2e` joint l'application par l'alias `cct-web`, jamais `app` : Chromium force
HTTPS sur ce nom (`.app` est un TLD en liste HSTS preload). Captures et
rapports dans `tests/e2e/results/` (ignore par git).

## Logs

- Tout part sur la sortie standard, **non bufferise** (`PYTHONUNBUFFERED=1`
  dans le Dockerfile, journal configure par `app/log.py`). Sans ca,
  `appctl logs` ne montre rien pendant des minutes, et on croit le serveur
  bloque.
- Une ligne par evenement, horodatee. Pas de secret, pas de donnee personnelle.
- Le volume de logs est une ressource : pas de journal d'acces Uvicorn
  (`--no-access-log`), pas de ligne par `info` UCI ; journalise les
  recherches (debut, paliers, fin) et les erreurs.

## Execution

- Tout runtime applicatif tourne dans Docker. Rien ne s'execute sur l'hote.
- N'installe aucun runtime applicatif sur l'hote.
- PostgreSQL, Redis et tout service de donnees sont DEDIES a cette application
  et declares dans ce `compose.yaml`. Il n'existe pas de base partagee sur ce
  VPS.
- Un worker qui consomme une file ou une base la declare ici, en
  `exposure: none`, sur le reseau `internal`.
- Utilise `appctl` pour toute operation Docker privilegiee. Tu n'as pas acces
  directement a la commande `docker`.
- Pour une tache periodique, garde la boucle : pas de cron dans le conteneur,
  pas de cron sur l'hote.

## Perimetre

- Travaille uniquement dans /srv/apps/cct.
- Ne touche jamais a /opt/infra.
- Ne tente jamais d'acceder aux autres applications du VPS.

## Interdictions (appctl les refuse)

- `privileged: true`
- `network_mode: host`, `pid: host`, `ipc: host`, `uts: host`
- `cap_add`, `devices`, `volumes_from`, `cgroup_parent`
- `security_opt` desactivant apparmor ou seccomp
- montage de /var/run/docker.sock
- bind mount hors de ce projet
- `build.context` hors de ce projet
- publication d'un port sur 0.0.0.0

## Secrets

- Aucun secret dans Git, dans le `.env` du projet, dans un prompt ou dans les
  logs. Une cle d'API de service tiers en est un.
- Les vrais secrets vivent dans /etc/app-secrets/cct/ (root uniquement) et
  sont injectes via Docker Compose Secrets, lus dans /run/secrets/....
- Un secret se pose avec `sudo appctl secret set <nom>` -- mais la valeur, ce
  n'est pas toi qui la tapes. Donne la commande a l'humain, qui la lance dans
  son terminal (saisie masquee). `sudo appctl secret list` montre ce qui
  existe ; aucune commande ne relit une valeur, et c'est voulu.
- Le mode du fichier secret est reporte tel quel dans le conteneur : en `0400`
  root, un worker qui tourne en utilisateur non privilegie -- le cas ici -- lit
  `permission denied`. Poser `0444` sur le fichier ; sur l'hote, c'est le
  repertoire (0700 root) qui protege.

## Donnees

- Les donnees persistantes vont dans des named volumes, nommes `cct_<usage>`.
  L'application utilise `cct_data`, monte sur `/data` (SQLite). L'ancien
  `cct_state` du squelette n'est plus monte ; il n'est pas supprime.
- Schema SQLite : migrations `backend/app/persistence/migrations/NNNN_*.sql`,
  numerotees sans trou, jamais modifiees une fois livrees (en ajouter une).
  Une sauvegarde `backup()` est faite automatiquement avant toute mise a niveau.
- Ne supprime jamais un volume sans demande explicite.
- N'execute jamais `docker volume prune`.

## Fin de tache

1. `tests/test_smoke.sh` (typecheck/vitest, pytest dans l'image, Playwright) et
   les tests pertinents ;
2. `sudo appctl validate` ;
3. `sudo appctl rebuild` si necessaire ;
4. `sudo appctl status` -- le conteneur doit finir `healthy` ;
5. `sudo appctl logs` -- verifier que le moteur a demarre (`moteur demarre :
   Stockfish 19`), pas seulement que le conteneur tourne ;
6. signaler tout echec restant sans le masquer.

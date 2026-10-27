# Lot 7 — Rapport : installateur Windows natif et gestion du moteur

Date : 27/10/2026. Décision du propriétaire : remplacer le paquet Docker Windows
(Lot 6) par un installateur natif, sans Docker ni WSL, et utiliser un Stockfish
existant, sinon télécharger la release officielle. La signature de code est
reportée.

**État : livré et testé en CI sur un vrai Windows. La validation sur le PC du
propriétaire (W01 à W12) reste à faire.** L'installateur a été construit, installé,
utilisé, mis à jour et désinstallé automatiquement sur le runner `windows-2025` de
GitHub. Aucune release `v0.2.x` n'a encore été taguée.

## Ce qui a été livré (quatre PR)

### A. Gestion du moteur (PR #5)

- `engine/locate.py` : candidats dans l'ordre suivant ; refus gardés avec leur raison.
  - chemin des Réglages ;
  - `STOCKFISH_PATH` ;
  - `PATH` ;
  - dossiers habituels sous Windows (Program Files, Arena, ChessBase) ;
  - moteur déjà téléchargé.

  Chaque candidat est vérifié par une poignée de main UCI avec un délai, et doit
  être Stockfish 16 ou plus récent.
- `engine/download.py`, `engine/catalog.py` : release `sf_19` *universal*
  (Windows `.zip`, Linux `.tar.gz`), SHA-256 vérifié **avant** extraction,
  installation atomique dans `<données>/engines/sf_19/`, avec la licence GPL.
- API : `GET /api/v1/engine`, `POST /engine/rescan`, `POST /engine/download`.
  Réglage `engine_path` ; la clé de cache utilise l'empreinte du binaire hors image
  Docker.
- Interface : panneau « Moteur Stockfish » dans les Réglages (moteur actuel,
  candidats écartés, téléchargement avec progression, nouvelle recherche). Le
  bandeau « moteur indisponible » y renvoie.

### B. Lanceur de bureau (PR #6)

- `python -m app.desktop [--stop]` :
  - instance unique (verrou `msvcrt`/`fcntl`) ;
  - port 8765, sinon un voisin, sinon un port du système, sur `127.0.0.1` ;
  - ouverture du navigateur ;
  - journal tournant `<données>/logs/cct.log`, console facultative (`pythonw`).
- Arrêt propre : `POST /api/v1/desktop/shutdown`, avec un jeton aléatoire écrit dans
  le dossier de données. Ces routes sont absentes de l'image Docker.
- `app.main:app` est construit paresseusement ; le CMD Docker est inchangé.

### C. Installateur (PR #7)

- `packaging/windows/build.ps1` :
  - Python 3.13.17 embarqué, pip 26.2.1 et Inno Setup 7.1.0, épinglés par
    SHA-256 ;
  - dépendances `uv.lock` avec empreintes (wheels `win_amd64`) ;
  - `python-chess` extrait de son archive source épinglée (il n'a pas de wheel) ;
  - interface compilée, bytecode précompilé, contrôle d'import.
- `cct.iss` :
  - installation par utilisateur, sans droits administrateur ;
  - raccourcis du menu Démarrer : ouvrir, arrêter, dossier des données ;
  - arrêt de l'instance avant une mise à jour ;
  - données jamais supprimées.
- CI `windows-installer` : construction, installation silencieuse, démarrage par
  `pythonw`, interface, **Stockfish téléchargé**, **analyse réelle**, instance unique,
  réinstallation par-dessus l'application ouverte, désinstallation qui garde les
  données. La release en brouillon joint le `Setup` et son `.sha256`.

### D. Documentation et retrait du paquet Docker (cette PR)

- `README_WINDOWS.md` et `VALIDATION_WINDOWS.md` (nouvelles gates W01 à W12) réécrits
  pour l'installateur natif ; `docs/release.md` et `docs/decisions.md` mis à jour,
  ainsi que `CLAUDE.md` et le README.
- Les scripts du paquet Docker Windows, `make_windows_bundle.py` et le ZIP de la
  release sont retirés.
- **Correction de sûreté** : les données natives passent de
  `%LOCALAPPDATA%\ChessCalculationTrainer\data` à
  `%LOCALAPPDATA%\Chess Calculation Trainer\data`. Le désinstalleur de l'ancien
  paquet Docker efface tout `%LOCALAPPDATA%\ChessCalculationTrainer` sauf
  `backups\` : lancé après l'installation native, il aurait effacé ses données.
  Aucune version native n'avait encore été publiée. Les sauvegardes Docker sont
  désormais lues explicitement à l'ancien emplacement, et le smoke Windows vérifie
  leur reprise.
- `merge-pr.mjs` exige le troisième check, comme le ruleset `protection-main`.

## Tests

- VPS :
  - pytest (157), dont faux moteurs UCI, téléchargement depuis un serveur HTTP local
    (empreinte fausse refusée) et cycle de vie du lanceur avec de vrais processus ;
  - vitest (24), Playwright (56, dont le panneau Moteur) ;
  - Pester et PSScriptAnalyzer.
- CI GitHub : les trois jobs ci-dessus sur chaque PR. La première exécution sous
  Windows a révélé trois défauts, corrigés :
  - `python-chess` sans wheel ;
  - les guillemets que Windows PowerShell 5.1 retire ;
  - `uv` sans `/tmp` dans son image.

## Ce qui n'a PAS pu être vérifié ici

- SmartScreen, le navigateur réel, les raccourcis cliqués, un antivirus tiers, un
  compte avec accents, un PC sans connexion : W01 à W12, sur le PC du propriétaire.
- La reprise d'une **vraie** sauvegarde v0.1.x (le test utilise une base créée par
  l'application).

## Reste à faire (opérateur)

1. Tag `v0.2.0` avec l'accord du propriétaire : la release en brouillon contiendra le
   `Setup`.
2. Fiche `packaging/windows/VALIDATION_WINDOWS.md` sur le PC du propriétaire ; si vous
   aviez la v0.1.x Docker, faites d'abord la procédure de passage (`README_WINDOWS.md`).
3. Signature de code, le jour où un certificat est disponible.

## Point ouvert

- Test e2e instable, vu une fois le 27/10 (relance verte). `analysis.spec.ts`,
  « étude libre » : après `fill('12')`, la ligne affichait une cible de 32 au lieu
  de 12. Ce code n'a pas changé au Lot 7. Piste : le champ est réécrit par le
  chargement des réglages juste après la saisie. À instrumenter s'il revient.

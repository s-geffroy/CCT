# Lot 6 — Rapport : publication GitHub et paquet Windows

Date : 27/10/2026. DoD du doc 13 : « machine Windows propre compatible […] installe
depuis Release sans dépendances de développement ; permet restauration de données ».

**État : livrable prêt, DoD non encore démontrable.** Tout ce qui se vérifie sur ce
VPS est vert. La première exécution de la CI GitHub, la première image publiée et
surtout l'installation sur un vrai PC Windows 11 restent à faire : les gates G01 à
G06 et W01 à W12 sont **non validées** à ce jour.

## Ce qui a été livré

### Paquet Windows (`packaging/windows/`)

- `compose.yaml` de production : image par digest, `127.0.0.1:8765` seulement,
  lecture seule, `/tmp` en tmpfs, volume `chess-calculation-trainer-data`,
  2 CPU / 2 Go, healthcheck sur `/live`.
- Huit lanceurs `.cmd`, chacun pour un double-clic :
  - `INSTALLER`, `OUVRIR`, `ARRETER` ;
  - `METTRE_A_JOUR`, `SAUVEGARDER`, `RESTAURER` ;
  - `DESINSTALLER`, `COLLECTER_DIAGNOSTIC`.
- Les scripts PowerShell, dont toute la logique testable est dans `common.ps1` :
  - **prérequis manquants proposés** : WSL 2 (`wsl --install`, fenêtre UAC) et Docker
    Desktop (installateur officiel via `winget`, sans jamais accepter de licence à la
    place de l'utilisateur), démarrage automatique de Docker, bascule vers les
    conteneurs Linux ; en cas de refus, gestes pas à pas et lien officiel ;
  - **installation** : prérequis, refus d'une autre version, port occupé détecté,
    image par digest, attente de `/live` puis `/ready` (moteur indisponible
    signalé sans échec), raccourci Bureau ;
  - **mise à jour** : sauvegarde vérifiée obligatoire, nouvelle image, migrations,
    retour arrière automatique de l'image **et** des données en cas d'échec ;
  - **sauvegarde** cohérente faite dans le conteneur, vérifiée, copiée sur le PC ;
    **restauration** choisie dans une liste, avec confirmation, l'ancienne base
    étant gardée ;
  - **désinstallation** sans jamais effacer les données par défaut ; `-PurgeData`
    exige une double confirmation ;
  - **rapport de diagnostic** sur le Bureau, avec nom du compte, du poste et chemin
    du profil masqués.
- `README_WINDOWS.md` (notice) et `VALIDATION_WINDOWS.md` (fiche W01–W12 et dépôt du
  rapport sur la branche GitHub `validation-windows`).

### Serveur

- `python -m app.backup create | verify` : sauvegarde par l'API SQLite,
  `integrity_check`, version de schéma.
- Restauration au démarrage depuis `/data/restore/incoming.sqlite`, avant les
  migrations : un fichier invalide est mis de côté, l'ancienne base est
  sauvegardée avant d'être remplacée.
- Version de l'application et révision injectées au build (affichées dans
  l'en-tête) ; étiquettes OCI ; `LICENSE` et notices copiées dans l'image.

### Publication

- `.github/workflows/container-release.yml` :
  - `test` (lecture seule) : `make ci` = pytest, vitest, ZIP d'essai, smoke de
    l'image finale en lecture seule, Playwright ;
  - `windows-scripts` : PSScriptAnalyzer + Pester sous **Windows PowerShell 5.1** ;
  - sur tag seulement, `publish` (`packages: write`) : image GHCR puis smoke de
    l'image **publiée, par digest** ;
  - sur tag seulement, `release` (`contents: write`) : ZIP + `.sha256` en
    **brouillon**.
- Actions épinglées par SHA, aucun jeton personnel.
- `scripts/ci/make_windows_bundle.py` : ZIP reproductible, contrôles
  (ASCII, CRLF, fichiers, digest, pas de `:latest`), SHA-256 calculé après
  l'archive.
- `LICENSE` (GPL-3.0) et `THIRD_PARTY_NOTICES.md` générés depuis l'image finale et
  le lockfile (Stockfish et réseau NNUE avec leurs sources et empreintes).
- `docs/release.md` : activer Actions, taguer, rendre le paquet public, tester le
  pull anonyme, valider sous Windows, publier le brouillon.

## Tests

| Suite | Résultat |
|---|---|
| pytest (image finale, vrai Stockfish) | **141/141** (+5 : sauvegarde cohérente pendant l'exécution, vérification, restauration au démarrage, fichier invalide écarté, CLI) |
| vitest | **24/24** |
| scripts Windows (PowerShell 7, service `pwsh`) | analyse statique : **0 problème** (dont syntaxe compatible 5.1) ; Pester **33/33** |
| Playwright | **52/52** |
| ZIP Windows | fabriqué et relu : 24 fichiers, manifeste par digest, digest invalide refusé |

## Ce qui n'a PAS pu être vérifié ici

- `make ci`, `scripts/ci/*.sh` et le workflow utilisent `docker` directement : ils
  tournent sur le runner GitHub, pas sur ce VPS. Seules leur syntaxe (bash, YAML)
  et la fabrication du ZIP sont vérifiées. **La première exécution de la CI peut
  révéler des corrections à faire.**
- Windows PowerShell 5.1 réel, Docker Desktop, WSL 2, SmartScreen, chemins
  accentués : job `windows-scripts` (5.1, sans Docker) puis poste réel (W01–W12).

## Reste à faire (opérateur)

1. Pousser `main` → premier passage de la CI (G01).
2. Taguer `v0.1.0` (avec votre accord) → image et brouillon (G03, G04, G06).
3. Paquet GHCR en Public, puis pull anonyme (G05).
4. Validation sur un PC Windows 11 (W01–W12), rapport sur `validation-windows`.
5. Publier le brouillon.

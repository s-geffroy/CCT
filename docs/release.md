# Publier une version (GitHub Actions, GHCR, paquet Windows)

Procédure opérateur. Rien n'est publié automatiquement sans un **tag** volontaire,
et la release reste un **brouillon** tant que les vérifications manuelles ne sont
pas faites.

## Ce que fait la CI (`.github/workflows/container-release.yml`)

| Événement | Jobs | Publie ? |
|---|---|---|
| Pull request, push sur `main`, lancement manuel | `test` (pytest, vitest, image finale, Playwright, ZIP d'essai) et `windows-scripts` (PSScriptAnalyzer, Pester sous Windows PowerShell 5.1) | non |
| Tag `vX.Y.Z` | les mêmes, puis `publish` (image `ghcr.io/s-geffroy/cct`, smoke de l'image **par digest**) et `release` (ZIP Windows + `.sha256`, release en **brouillon**) | image : oui ; release : brouillon |

Permissions : lecture seule partout ; `packages: write` seulement pour `publish`,
`contents: write` seulement pour `release`, et seulement sur un tag. Aucun jeton
personnel : le `GITHUB_TOKEN` éphémère suffit. Les actions sont épinglées par SHA.

## Une seule fois : activer GitHub Actions

1. Dépôt → **Settings → Actions → General**.
2. *Actions permissions* : autoriser les actions (au minimum `actions/*` et `docker/*`).
3. *Workflow permissions* : garder **Read repository contents and packages
   permissions** (les jobs demandent eux-mêmes l'écriture nécessaire).
4. Onglet **Actions** : le workflow apparaît après le premier push sur `main` ;
   **Run workflow** relance les tests sans rien publier (gate G01).

## Publier `vX.Y.Z`

1. `main` à jour et vert dans Actions (tests du push).
2. Tag annoté, poussé (avec l'accord du propriétaire) :
   ```bash
   git tag -a v0.1.0 -m "Premiere version"
   git push origin v0.1.0
   ```
3. Actions → exécution du tag : quatre jobs verts. Le job `publish` affiche le
   digest ; le brouillon de release (onglet **Releases**) contient le ZIP, son
   `.sha256` et l'image par digest dans les notes.
4. **Rendre l'image publique** (une fois, au premier tag) : profil GitHub →
   **Packages → cct → Package settings → Change visibility → Public**. Un dépôt
   public ne rend pas son paquet public automatiquement.
5. **Pull anonyme** (gate G05) depuis une machine sans identifiants GHCR :
   `docker pull ghcr.io/s-geffroy/cct@sha256:<digest des notes>`.
6. **Validation Windows** (W01 à W12) : télécharger le ZIP **du brouillon**, suivre
   `VALIDATION_WINDOWS.md`, déposer le rapport sur la branche `validation-windows`.
7. Seulement ensuite : **Publish release** sur le brouillon.

Un tag publié n'est jamais réécrit : une correction devient `vX.Y.(Z+1)`.

## Dépannage

| Symptôme | Cause probable | Correction |
|---|---|---|
| pas de workflow dans Actions | fichier absent de `main` | pousser `main` |
| `permission_denied: write_package` | droits du paquet | Package settings → *Manage Actions access* → ajouter le dépôt |
| `docker pull` anonyme refusé | paquet encore privé | étape 4 |
| job `windows-scripts` rouge | encodage, analyse statique ou Pester | lire le journal ; reproduire avec `sudo appctl run pwsh` |
| job `test` rouge sur Playwright | régression d'interface | artefact `e2e-results` (captures, traces) |

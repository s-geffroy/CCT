# Publier une version (GitHub Actions, installateur Windows, image GHCR)

Procédure opérateur. Rien n'est publié sans un **tag** volontaire, et la release
reste un **brouillon** tant que la validation sur un vrai PC Windows n'est pas faite.

## Ce que fait la CI (`.github/workflows/container-release.yml`)

| Événement | Jobs | Publie ? |
|---|---|---|
| Pull request, push sur `main`, lancement manuel | `test` (pytest, vitest, image finale, Playwright, dépendances Windows = `uv.lock`) ; `windows-scripts` (PSScriptAnalyzer, Pester sous Windows PowerShell 5.1) ; `windows-installer` (construit le `Setup`, l'**installe** sur le runner Windows, démarre, télécharge Stockfish, analyse, met à jour par-dessus, désinstalle) | non |
| Tag `vX.Y.Z` | les mêmes, puis `publish` (image `ghcr.io/s-geffroy/cct`, smoke **par digest**) et `release` (`Setup` + `.sha256`, release en **brouillon**) | image : oui ; release : brouillon |

Les trois jobs de test sont des **checks obligatoires** du ruleset `protection-main`,
et `scripts/ci/merge-pr.mjs` les exige aussi.

Permissions : lecture seule partout. `packages: write` n'est accordé qu'à `publish`
et `contents: write` qu'à `release`, et seulement sur un tag. Le `GITHUB_TOKEN`
éphémère suffit : aucun jeton personnel. Les actions sont épinglées par SHA.

L'installateur Windows embarque Python, pip et Inno Setup, tous épinglés par
version **et** SHA-256 (`packaging/windows/native.ps1`). Les dépendances Python sont
celles de `uv.lock`, avec leurs empreintes (`packaging/windows/requirements.txt`).
Après une modification de `uv.lock`, régénérez ce fichier :

```bash
sudo appctl run devtools sh -c 'cd backend && uv export --frozen --no-dev --no-emit-project --format requirements-txt' > packaging/windows/requirements.txt
```

## Publier `vX.Y.Z`

1. `main` à jour et vert dans Actions (tests du push).
2. Tag annoté, poussé **avec l'accord du propriétaire** :
   ```bash
   git tag -a v0.2.0 -m "Installateur Windows natif"
   git push origin v0.2.0
   ```
3. Dans Actions, l'exécution du tag doit avoir tous ses jobs verts. Le brouillon de
   release (onglet **Releases**) contient alors
   `ChessCalculationTrainer-Setup-vX.Y.Z.exe`, son `.sha256` et, dans les notes, le
   digest de l'image.
4. **Validation Windows** (W01 à W12) : téléchargez le `Setup` **du brouillon**,
   suivez `packaging/windows/VALIDATION_WINDOWS.md`, puis déposez le rapport sur la
   branche `validation-windows`.
5. Seulement ensuite : **Publish release** sur le brouillon.

L'image GHCR ne sert plus aux utilisateurs Windows. Elle reste publiée pour un
déploiement serveur. Si vous la voulez accessible sans identifiants, faites ce
réglage une seule fois : **Packages → cct → Package settings → Change visibility →
Public**.

Un tag publié n'est jamais réécrit : une correction devient `vX.Y.(Z+1)`.

## Signature de code (plus tard)

Le `Setup` n'est pas signé, donc SmartScreen avertit à la première exécution.
Le jour venu, ajoutez une étape `signtool` dans le job `windows-installer`, entre
la construction et le smoke, avec le certificat en secret GitHub. La CI vérifiera
alors l'exécutable signé.

## Dépannage

| Symptôme | Cause probable | Correction |
|---|---|---|
| `windows-installer` rouge à la construction | empreinte changée en amont, wheel absent | lire le journal ; une source modifiée est **refusée**, il faut ré-épingler volontairement |
| `windows-installer` rouge au smoke | régression de démarrage, du moteur ou de la mise à jour | artefact `windows-native-logs` (`cct.log`, journal d'installation) |
| `test` rouge sur `windows-requirements` | `uv.lock` modifié sans régénérer `requirements.txt` | commande ci-dessus |
| `windows-scripts` rouge | encodage (ASCII, CRLF), analyse statique ou Pester | reproduire avec `sudo appctl run pwsh` |
| `test` rouge sur Playwright | régression d'interface | artefact `e2e-results` (captures, traces) |
| `permission_denied: write_package` | droits du paquet GHCR | Package settings → *Manage Actions access* → ajouter le dépôt |

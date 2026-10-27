# Chess Calculation Trainer — installation sous Windows

Application locale d'entraînement au calcul des variantes. Elle tourne dans
Docker Desktop et s'ouvre dans votre navigateur, à l'adresse
`http://127.0.0.1:8765`, sur votre PC uniquement : rien n'est accessible depuis
le réseau.

## Ce qu'il faut

- Windows 11 64 bits (version 23H2 ou plus récente), processeur Intel ou AMD.
- 8 Go de mémoire, 5 Go d'espace libre.
- **Docker Desktop**, avec WSL 2 et les conteneurs Linux (choix par défaut).
  S'il manque, `INSTALLER.cmd` **propose de l'installer** pour vous (installateur
  officiel de Docker via `winget`), comme WSL 2 (`wsl --install`), toujours avec
  votre accord et la fenêtre d'autorisation de Windows ; si vous refusez, il
  affiche les gestes à faire. Il démarre Docker Desktop s'il est arrêté et propose
  de passer en conteneurs Linux si besoin. Page officielle :
  https://docs.docker.com/desktop/setup/install/windows-install/
  Docker Desktop a ses propres conditions de licence : c'est **vous** qui les lisez
  et les acceptez au premier démarrage (le script ne le fait jamais à votre place).
  Après l'installation de WSL, Windows doit redémarrer : relancez ensuite
  `INSTALLER.cmd`, il reprend où il en était.

Aucun autre logiciel n'est nécessaire (ni Python, ni Node, ni Git).

## Installer

1. Téléchargez depuis la page Releases du projet le fichier
   `ChessCalculationTrainer-Windows-vX.Y.Z.zip` et, à côté, son `.sha256`.
2. (Recommandé) Vérifiez l'empreinte dans PowerShell :
   ```powershell
   Get-FileHash -Algorithm SHA256 .\ChessCalculationTrainer-Windows-vX.Y.Z.zip
   Get-Content .\ChessCalculationTrainer-Windows-vX.Y.Z.zip.sha256
   ```
   Les 64 caractères doivent être identiques. Sinon, **ne lancez rien**.
3. Clic droit sur le ZIP → **Extraire tout**. Ne lancez rien depuis l'intérieur
   du ZIP.
4. Démarrez Docker Desktop et attendez qu'il soit prêt.
5. Double-cliquez **`INSTALLER.cmd`** dans le dossier extrait.

L'installation copie l'application dans `%LOCALAPPDATA%\ChessCalculationTrainer`,
télécharge l'image (quelques minutes la première fois), démarre, vérifie que
tout répond, crée le raccourci **Chess Calculation Trainer** sur le Bureau et
ouvre le navigateur. Le dossier extrait peut ensuite être supprimé.

Windows peut afficher un avertissement SmartScreen pour un fichier `.cmd`
téléchargé : vérifiez que l'archive vient bien de la page Releases du projet et
que l'empreinte concorde. Ne désactivez jamais SmartScreen ni l'antivirus.

Les `.cmd` lancent PowerShell avec `-ExecutionPolicy Bypass` **pour leur propre
script seulement** : la politique de votre poste n'est pas modifiée. Sur un poste
d'entreprise verrouillé, ce lancement peut être interdit : voyez votre service
informatique.

## Au quotidien

| Action | Comment |
|---|---|
| Ouvrir | raccourci du Bureau (ou `OUVRIR.cmd` dans `%LOCALAPPDATA%\ChessCalculationTrainer`) |
| Arrêter | `ARRETER.cmd` : l'application s'arrête, vos données restent |
| Sauvegarder | `SAUVEGARDER.cmd` : copie vérifiée dans `...\ChessCalculationTrainer\backups` |
| Restaurer | `RESTAURER.cmd` : choisir une sauvegarde ; la base actuelle est d'abord copiée |
| Mettre à jour | extraire le ZIP de la **nouvelle** version, double-cliquer son `METTRE_A_JOUR.cmd` |
| Désinstaller | `DESINSTALLER.cmd` : les données sont **conservées** |
| Signaler un problème | `COLLECTER_DIAGNOSTIC.cmd` : rapport texte sur le Bureau |

Vos séances et positions vivent dans le volume Docker
`chess-calculation-trainer-data`. Arrêter, réinstaller, mettre à jour ou
désinstaller ne l'efface pas. Pour tout effacer (définitif), en PowerShell :
`& "$env:LOCALAPPDATA\ChessCalculationTrainer\scripts\windows\uninstall.ps1" -PurgeData`
(double confirmation demandée).

## Mise à jour

`INSTALLER.cmd` refuse d'installer une autre version par-dessus l'existante.
Utilisez `METTRE_A_JOUR.cmd` de la nouvelle version : il sauvegarde vos données
(sauvegarde vérifiée), passe à la nouvelle image, laisse l'application migrer sa
base, puis vérifie qu'elle répond. Si la nouvelle version ne démarre pas, il
**revient automatiquement** à l'ancienne version et à vos données d'avant la mise
à jour.

## Problèmes fréquents

| Message | Que faire |
|---|---|
| Docker Desktop absent | l'installer depuis le lien officiel, le démarrer, relancer `INSTALLER.cmd` |
| Docker ne répond pas | démarrer Docker Desktop, attendre « Engine running », relancer |
| Conteneurs Windows | menu de Docker Desktop → *Switch to Linux containers* |
| Port 8765 déjà utilisé | changer `HOST_PORT=8766` dans `%LOCALAPPDATA%\ChessCalculationTrainer\.env`, relancer `INSTALLER.cmd` |
| Image refusée (*denied*) | l'image n'est pas encore publique : signalez-le au projet |
| Moteur indisponible | l'entraînement reste possible ; envoyez le rapport de diagnostic |

## Licence

Logiciel libre sous GPL-3.0-or-later (`LICENSE`). Il embarque Stockfish 19
(GPL-3.0) et d'autres composants listés dans `THIRD_PARTY_NOTICES.md`, avec
l'adresse de leurs sources.

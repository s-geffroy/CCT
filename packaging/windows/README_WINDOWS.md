# Chess Calculation Trainer sous Windows

Application d'entraînement au calcul des variantes, qui tourne **sur votre PC**,
dans votre navigateur. Rien n'est envoyé sur Internet ; seul le téléchargement
de Stockfish (une fois, si nécessaire) passe par le réseau.

**Il ne faut ni Docker, ni WSL, ni droits administrateur.**

## Configuration

- Windows 10 (1809 ou plus récent) ou Windows 11, 64 bits ;
- 4 Go de mémoire au minimum, 300 Mo de disque environ (Stockfish compris) ;
- un navigateur récent (Edge, Chrome, Firefox).

## Installer

1. Dans la page de la version sur GitHub (*Releases*), téléchargez
   `ChessCalculationTrainer-Setup-vX.Y.Z.exe`.
2. Double-cliquez dessus. L'installateur n'est pas encore signé : Windows
   (SmartScreen) affiche « Windows a protégé votre ordinateur ». Cliquez sur
   **Informations complémentaires**, puis **Exécuter quand même**.
3. Suivez l'assistant (licence GPL, raccourci Bureau en option). À la fin,
   l'application s'ouvre dans le navigateur.

Facultatif : l'empreinte du fichier est publiée à côté (`.sha256`). Pour la
comparer, dans PowerShell :
`Get-FileHash .\ChessCalculationTrainer-Setup-vX.Y.Z.exe -Algorithm SHA256`.

## Stockfish

Au premier lancement, l'application cherche un Stockfish déjà présent sur le PC
(Program Files, Arena, ChessBase, `PATH`). Il doit s'agir de Stockfish 16 ou d'une
version plus récente.

S'il n'y en a pas, ouvrez **Réglages → Moteur Stockfish → Télécharger Stockfish**.
L'application télécharge alors la version officielle Stockfish 19 (environ 80 Mo)
depuis GitHub. Elle vérifie son empreinte avant de l'installer dans le dossier des
données.

Pour utiliser un autre Stockfish, indiquez son chemin dans le champ « Chemin d'un
Stockfish existant » du même écran, puis enregistrez.

Sans moteur, les séances de calcul (B et C) restent possibles ; l'analyse les
rattrape dès qu'un moteur est disponible.

## Au quotidien

| Pour… | Faire |
|---|---|
| Ouvrir | menu Démarrer → **Chess Calculation Trainer** (ou le raccourci Bureau). Un second clic rouvre simplement l'onglet. |
| Arrêter | menu Démarrer → Chess Calculation Trainer → **Arreter Chess Calculation Trainer**. Fermer l'onglet ne suffit pas : l'application continue en arrière-plan, sans fenêtre. |
| Voir les données | menu Démarrer → Chess Calculation Trainer → **Dossier des donnees** |
| Mettre à jour | lancer le `Setup` de la nouvelle version, même si l'application est ouverte : elle est arrêtée proprement, puis remplacée. Vos données sont conservées. |
| Désinstaller | Paramètres Windows → Applications → **Chess Calculation Trainer** → Désinstaller. Vos données sont conservées. |

L'application écoute seulement sur `127.0.0.1` (votre PC). Elle prend le port 8765,
ou un port voisin s'il est occupé.

## Où sont les fichiers

| Quoi | Où |
|---|---|
| Programme (remplacé à chaque mise à jour) | `%LOCALAPPDATA%\Programs\ChessCalculationTrainer` |
| **Vos données** : base, Stockfish téléchargé, journal | `%LOCALAPPDATA%\Chess Calculation Trainer\data` |
| Journal (à joindre en cas de problème) | `...\data\logs\cct.log` |

Une copie de la base est faite automatiquement avant chaque changement de format
(dans `...\data\backups`).

**Sauvegarder vous-même** : arrêtez l'application, puis copiez le dossier `data`
ailleurs.

**Restaurer** une base `.sqlite` : arrêtez l'application, puis copiez le fichier sous
le nom `...\data\restore\incoming.sqlite` et rouvrez l'application. Elle le vérifie
avant de le prendre, et l'ancienne base est gardée à côté.

## Vous aviez la version Docker (v0.1.x)

Faites ces étapes **dans cet ordre**. L'ancien désinstalleur supprime un raccourci
Bureau du même nom : il doit passer avant le nouvel installateur.

1. Dans `%LOCALAPPDATA%\ChessCalculationTrainer` (dossier de l'ancienne version),
   double-cliquez sur **`SAUVEGARDER.cmd`**. Une copie vérifiée est écrite dans
   `...\ChessCalculationTrainer\backups`.
2. Dans le même dossier, double-cliquez sur **`DESINSTALLER.cmd`** et gardez les
   données (réponse par défaut).
3. Installez la nouvelle version (ci-dessus). Au premier lancement, la dernière
   sauvegarde Docker est reprise automatiquement et vérifiée. Le journal l'indique :
   « donnees de l'ancienne version Docker reprises ».

Docker Desktop n'est plus nécessaire. Vous pouvez le désinstaller s'il ne vous sert
à rien d'autre.

## En cas de problème

| Symptôme | Que faire |
|---|---|
| Rien ne s'ouvre après un clic | attendre 10 s (premier démarrage), puis recliquer. Sinon, joindre `...\data\logs\cct.log`. |
| « Moteur indisponible » | Réglages → Moteur Stockfish : la raison est affichée ; télécharger, ou indiquer un chemin. |
| Téléchargement de Stockfish refusé | réseau filtré ou empreinte inattendue : rien n'a été installé. Réessayer plus tard, ou indiquer un Stockfish déjà présent. |
| L'installateur dit que l'application ne s'est pas arrêtée | menu Démarrer → Arreter, puis relancer l'installateur. |

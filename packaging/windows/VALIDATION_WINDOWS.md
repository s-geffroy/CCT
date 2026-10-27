# Fiche de validation Windows (gates W01 à W12) : installateur natif

À remplir sur un **vrai PC Windows 11 x64**. Pour chaque test, notez **OK**, **KO**
ou **non testé**. Pour chaque KO, décrivez en une phrase ce que vous avez fait, ce que
vous avez vu et ce qui était attendu. Un KO est aussi utile qu'un OK.

La CI fait déjà tourner une installation automatique sur un Windows de GitHub :
installation silencieuse, Stockfish téléchargé, analyse, mise à jour,
désinstallation. Cette fiche couvre ce qu'elle ne voit pas : SmartScreen, le
navigateur, les raccourcis, un vrai compte et un vrai réseau.

- Version testée : `v____` (nom du `Setup`)
- Date : ____
- PC : modèle, processeur, mémoire ; antivirus autre que Defender ? ____

| ID | Scénario | Gestes | Résultat attendu | Résultat |
|---|---|---|---|---|
| W01 | Installation | double-clic sur le `Setup`, passer SmartScreen (Informations complémentaires → Exécuter quand même), assistant | aucune demande administrateur (pas de fenêtre UAC) ; l'application s'ouvre dans le navigateur ; entrée dans le menu Démarrer | |
| W02 | Stockfish | Réglages → Moteur Stockfish | soit un Stockfish du PC est trouvé (nom, chemin), soit **Télécharger** l'installe (barre de progression, puis « Stockfish 19 ») ; plus de bandeau « moteur indisponible » | |
| W03 | Séance complète | une séance (mode B ou C), Go, soumission, révélation, débriefing | comme d'habitude ; l'analyse se fait | |
| W04 | Instance unique | recliquer 2 ou 3 fois sur le raccourci | un onglet s'ouvre à chaque fois, toujours sur la même application (mêmes séances) | |
| W05 | Arrêt, puis réouverture | menu Démarrer → Arreter ; vérifier que la page ne répond plus ; rouvrir | arrêt en quelques secondes ; réouverture avec les données | |
| W06 | Redémarrage du PC | redémarrer Windows, rouvrir par le raccourci | tout est là ; Stockfish n'est pas retéléchargé | |
| W07 | Local uniquement | depuis un téléphone sur le même Wi-Fi : `http://<IP-du-PC>:8765` | page inaccessible ; aucune alerte du pare-feu Windows à l'installation | |
| W08 | Compte avec accent ou espace | session Windows « Élodie Test » : installer, ouvrir | tout fonctionne | |
| W09 | Mise à jour | application ouverte, lancer le `Setup` d'une version plus récente (ou le même) | l'application est arrêtée puis remplacée ; séances et Stockfish conservés ; nouvelle version affichée | |
| W10 | Désinstallation | Paramètres → Applications → Désinstaller, puis réinstaller | programme supprimé ; après réinstallation, les données sont retrouvées | |
| W11 | Tests automatiques Windows | rien à faire (CI GitHub) | jobs « scripts Windows » et « installateur Windows natif » verts | |
| W12 | Passage depuis la version Docker (si vous l'aviez) | suivre « Vous aviez la version Docker » de `README_WINDOWS.md` | anciennes séances présentes dans l'Historique | |

## Transmettre les résultats (GitHub, sans Git ni jeton)

1. Sur https://github.com/s-geffroy/CCT, ouvrez le sélecteur de branche, tapez
   `validation-windows`, puis « Create branch » (la première fois seulement).
2. Sur cette branche : **Add file → Create new file**. Nommez le fichier
   `validation/AAAA-MM-JJ/resultats.md`, collez-y cette fiche remplie, puis choisissez
   « Commit directly to the validation-windows branch ».
3. Ouvrez le dossier `validation/AAAA-MM-JJ/`, puis **Add file → Upload files** :
   déposez le journal `%LOCALAPPDATA%\Chess Calculation Trainer\data\logs\cct.log`
   et vos captures d'écran.
4. Dites dans la conversation avec Claude : « rapport déposé, dossier
   validation/AAAA-MM-JJ ».

Ne déposez rien sur `main`. Le journal ne contient ni secret ni contenu de séance.
Il contient en revanche des chemins de fichiers, donc votre nom de compte Windows :
relisez-le et masquez ce nom si vous le souhaitez. Vérifiez aussi vos captures.

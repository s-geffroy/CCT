# Fiche de validation Windows (gates W01 à W12)

À remplir sur un **vrai PC Windows 11 x64**. Une case par test : **OK**, **KO**
ou **non testé**. Pour chaque KO : ce que vous avez fait, ce que vous avez vu, ce
qui était attendu (une phrase suffit). Un KO est aussi utile qu'un OK.

- Version testée : `v____` (nom du ZIP)
- Date : ____
- PC : (modèle, processeur, mémoire)

| ID | Scénario | Gestes | Résultat attendu | Résultat |
|---|---|---|---|---|
| W01 | Docker Desktop déjà prêt | extraire le ZIP, double-clic `INSTALLER.cmd` | « Installation terminée », navigateur ouvert sur l'application, raccourci sur le Bureau | |
| W02 | Docker Desktop (et WSL) absents (autre PC ou VM) | double-clic `INSTALLER.cmd`, répondre N, puis relancer et répondre O | N : gestes + lien officiel, rien d'installé ; O : installation officielle (fenêtre UAC), redémarrage demandé pour WSL, puis l'installation reprend | |
| W03 | Docker arrêté, puis en mode conteneurs Windows | quitter Docker Desktop, `INSTALLER.cmd` ; puis *Switch to Windows containers*, `INSTALLER.cmd` | Docker démarré automatiquement ; bascule vers Linux proposée ; vos autres conteneurs Docker intacts | |
| W04 | Réinstallation même version | faire une séance, puis relancer `INSTALLER.cmd` | aucune erreur ; la séance est toujours dans l'Historique | |
| W05 | Autre version via `INSTALLER.cmd` | lancer `INSTALLER.cmd` d'une autre version | refus, renvoi vers `METTRE_A_JOUR.cmd` | |
| W06 | Arrêt | `ARRETER.cmd`, puis le raccourci du Bureau | arrêt, puis redémarrage avec les données | |
| W07 | Local uniquement | depuis un téléphone sur le même Wi-Fi : `http://<IP-du-PC>:8765` | page inaccessible | |
| W08 | Compte avec accent ou espace | session Windows « Élodie Test » : installer, ouvrir par le raccourci | tout fonctionne, ZIP supprimé ensuite | |
| W09 | Sauvegarde et restauration | séance A, `SAUVEGARDER.cmd`, séance B, `RESTAURER.cmd` (choisir la sauvegarde) | A présente, B absente ; message « Restauration faite et vérifiée » | |
| W10 | Désinstallation | `DESINSTALLER.cmd`, puis réinstaller | données retrouvées après réinstallation | |
| W11 | Tests automatiques Windows | (fait par la CI GitHub : rien à faire) | job « windows-scripts » vert | |
| W12 | Rapport du poste | `COLLECTER_DIAGNOSTIC.cmd` | fichier `cct-rapport-...txt` dans le dossier personnel (`%USERPROFILE%`, par exemple `C:\Users\<nom>`) | |

Mise à jour (si une nouvelle version existe) : `METTRE_A_JOUR.cmd` de la nouvelle
version → données conservées, nouvelle version affichée en haut de l'application
(à côté du nom du moteur) : ____

## Transmettre les résultats (GitHub, sans Git ni jeton)

1. Sur https://github.com/s-geffroy/CCT, sélecteur de branche → taper
   `validation-windows` → « Create branch » (la première fois seulement).
2. Sur cette branche : **Add file → Create new file**, nom
   `validation/AAAA-MM-JJ/resultats.md`, coller cette fiche remplie,
   « Commit directly to the validation-windows branch ».
3. Ouvrir le dossier `validation/AAAA-MM-JJ/` → **Add file → Upload files** :
   le `cct-rapport-....txt` de votre dossier personnel (`%USERPROFILE%`) et vos captures d'écran.
4. Dire dans la conversation avec Claude : « rapport déposé, dossier
   validation/AAAA-MM-JJ ».

Ne rien déposer sur `main`. Le rapport ne contient ni secret ni nom de compte
(masqués) ; vérifiez quand même vos captures.

# Lot 5 — Rapport : UX, accessibilite, reglages

Date : 27/10/2026. DoD du doc 13 : « Playwright desktop/mobile, pas de blocage UI
sur analyse active » — **atteinte** : 52 tests navigateur verts sur desktop, laptop et mobile, dont un test de fluidite pendant une recherche active.

## Ce qui a ete livre

### Reglages (`GET`/`PUT /api/v1/settings`, `app/preferences.py`)

- Reglages bornes, valides cote serveur (refus 422 qui nomme le reglage et ses
  bornes), persistes dans la table `settings` (seules les valeurs modifiees ;
  une valeur stockee devenue invalide est ignoree au demarrage) :
  moteur (threads, hash), etude libre (profondeur, MultiPV, budget), reference
  des seances (profondeur, budget), arbre (budget, noeuds, profondeur locale,
  budget par noeud, demi-coups automatiques), affichage (point de vue des
  evaluations).
- Bornes tirees du conteneur : threads <= quota CPU (cgroups), hash <= un quart
  de la memoire allouee.
- **Threads et hash s'appliquent sans redemarrer** l'application, apres la
  recherche en cours (verrou du moteur) ; l'identite du moteur dans la cle de
  cache change avec eux, aucun resultat n'est confondu. L'interface montre la
  configuration appliquee et celle en attente.
- Les nouvelles seances et les nouveaux arbres lisent les reglages courants.

### Interface (shadcn/ui, doc 03)

- Socle **Tailwind 4 + shadcn/ui** (Radix), versions epinglees, toutes publiees
  depuis plus de deux semaines : `Button`, `Badge`, `AlertDialog`, `Progress`,
  `NativeSelect`, `Input`, `Label`, `Sonner` (notifications), etc. Les selects
  restent natifs (accessibles, utilisables au doigt). Les controles natifs
  restants ont la meme apparence.
- Navigation : Positions, Seance, Etude, Historique, **Reglages** ; bandeau
  « moteur indisponible » (verifie toutes les 30 s) qui rappelle que les
  seances B/C restent possibles.
- **Point de vue des evaluations** : Blancs (defaut) ou camp au trait, avec
  libelle de colonne et legende toujours visibles ; les bornes s'inversent avec
  le camp.
- **Clavier** : tableau des variantes (haut/bas : variante, gauche/droite :
  coups, Debut/Fin) ; texte des coups des parties et des seances (droite :
  suite, gauche : retour, haut/bas : variantes soeurs, Debut : racine) ;
  onglets de source (fleches) ; confirmation d'abandon en vraie boite modale
  (Echap annule).
- **Lecteurs d'ecran** : chaque piece de l'echiquier est nommee (« Cavalier
  blanc en g1 »), ce que `react-chessboard` ne fait pas ; evaluations et
  profondeurs explicitees ; etat de la recherche annonce (`aria-live`).
- Etude libre : valeurs proposees depuis les reglages ; barre « temps ecoule /
  budget » (jamais un pourcentage de profondeur) ; filtre informatif captures /
  echecs.
- **Editeur a 1024 x 768** : echiquier et reglages cote a cote, tout tient dans
  la fenetre sans defilement (teste).
- **Mobile** : aucune page plus large que l'ecran (FEN longues coupees, champs
  bornes), echiquier et tableaux empiles.
- Etats vides et d'erreur explicites (historique, positions, analyse sans
  ligne, champ de reglage fautif).
- Historique : qualite du debriefing.

### Non-blocage pendant une analyse

Le flux SSE est deja limite a un instantane par seconde (Lot 3) ; les lignes du
tableau sont memoisees et ne se redessinent que si leurs donnees changent.
Test Playwright : pendant 8 s de flux d'une recherche a profondeur 32, chaque
selection de ligne et chaque pas dans la variante est visible en moins de 500 ms,
et aucune tache longue du navigateur ne depasse 200 ms.

## Tests

| Suite | Resultat |
|---|---|
| pytest (image finale, vrai Stockfish) | **136/136** (+4 : bornes, persistance, valeur stockee invalide, application a chaud de threads/hash) |
| vitest | **24/24** (+4 : clavier dans l'arbre de coups, point de vue et bornes, noms des pieces) |
| Playwright | **52/52**, deux executions consecutives : desktop 1280, laptop 1024 et **mobile Pixel 7** (+16, dont axe-core WCAG A/AA sans violation grave sur 5 pages, reglages, clavier, fluidite pendant une analyse, editeur a 1024 x 768, seance complete sur telephone sans debordement) |

En cours de lot, le premier passage a revele : un nom accessible en double (panneau
d'onglets), des pieces sans nom pour les lecteurs d'ecran (signale par axe), un
debordement horizontal sur mobile (FEN longues, champ `size=60`) et la validation
native du navigateur qui court-circuitait le message du serveur. Tous corriges.

## Ecarts et limites

- Theme sombre : facultatif dans la spec, non fait.
- `react-chessboard` n'offre pas de deplacement des pieces au clavier : la saisie
  SAN reste le chemin clavier et lecteur d'ecran pour jouer un coup.
- Les textes des diagnostics (serveur) restent au point de vue des Blancs, ce que
  l'interface signale quand l'autre point de vue est choisi.
- Mobile : teste sur le profil Pixel 7 de Playwright (Chromium), pas sur un vrai
  telephone ; le glisser-deposer tactile n'y est pas teste (saisie SAN).

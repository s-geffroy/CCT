# Lot 4 — Rapport : arbre de reference ramifie et debriefing

Date : 27/10/2026. DoD du doc 13 : « corpus de 20 exercices donne des diagnostics
attendus et abstention quand reference insuffisante » — **atteinte** sur un corpus
de 21 positions, avec le vrai moteur, en parcourant toute l'API (seance, coups,
soumission, arbre, revelation, debriefing). Reserve importante : le corpus est
annote par l'implementeur, pas par un joueur (voir « Limites »).

## Ce qui a ete livre

### Arbre de reference (`domain/reference_policy.py`, `services.py`)

- Un **noeud** = une position atteinte depuis la racine de l'exercice par une suite
  UCI ; son analyse est un travail ordinaire du planificateur (racine + chemin,
  historique complet transmis au moteur). Statuts : `queued`, `provisional`,
  `depth_met`, `budget_exhausted`, `incomplete`, `failed`, `pruned_by_policy`,
  `terminal` — jamais « mauvaise variante ».
- **Raison de selection** conservee sur chaque noeud : `root`, `top_rank`,
  `opponent_best_defense`, `opponent_alternative`, `user_branch`,
  `user_requested_reanalysis` ; une branche reanalysee reste marquee comme telle.
- **Politique bornee** (doc 06) : 3 meilleurs coups racine ; cote adverse la
  meilleure defense et les reponses a moins de 150 cp ; cote joueur la meilleure
  riposte ; 4 demi-coups ; MultiPV 3 aux noeuds ; plafonds 80 noeuds, 300 s,
  30 s par noeud (variables `TREE_*`). Les branches du joueur passent en tete et
  ont leur **propre enveloppe** (memes plafonds) : la preparation lancee pendant le
  calcul ne peut pas epuiser la verification de ses coups.
- L'arbre avance quand un travail se termine, quand la file se vide, a la
  soumission et sur demande ; il se reprend apres un redemarrage (travail
  interrompu relance une fois).
- **Reanalyse a la demande** (`POST /reference-trees/{id}/expand`) : approfondir un
  noeud (+4 demi-coups de profondeur cible) ou analyser un coup qui prolonge un
  noeud ; l'analyse precedente reste lisible pendant la nouvelle.
- **File equitable** : vieillissement de +1 de priorite par minute d'attente.

### Debriefing (`domain/review.py`, `GET /sessions/{id}/review`)

Fonction pure, sans moteur ni mutation des arbres (projection). Taxonomie du
doc 07 : `candidate_found`, `candidate_omitted`, `critical_defense_omitted`,
`illegal_continuation`, `evaluation_mismatch`, `acceptable_alternative`,
`tactical_refutation`, `unverified`, `no_trace`, chacune avec sa certitude
(`certain`, `verifie par le moteur`, `non determine`) et ses preuves (suite
legale, FEN de bascule, scores, profondeurs).

Regles de prudence (politique versionnee `POLICY["version"] = 1`) :

- une evaluation n'est une preuve que si elle est **exacte** (sans borne) et
  atteste une profondeur **>= 12** ; sinon « non determine » ;
- une **refutation** exige un ecart >= 200 cp **et** un changement de classe
  (gagnant / equilibre / perdant) : un coup qui gagne moins vite n'est jamais
  refute (corpus C02 : « Rf1 » au lieu du mat reste une alternative acceptable) ;
- une **defense critique oubliee** : le joueur a envisage des reponses adverses,
  pas la meilleure, et la meilleure est plus forte d'au moins 100 cp que toutes les
  siennes ; s'il s'est arrete avant, c'est de l'horizon, pas une omission ;
- hierarchie : legalite > refutation > ecart robuste > divergence de PV (jamais un
  verdict) ; transpositions annotees, jamais utilisees comme preuve.

Dimensions separees, sans note globale : couverture des candidats pertinents,
anticipation adverse, exactitude des lignes, horizon restitue, appreciations.
Qualite declaree : `final`, `provisional` (arbre en construction) ou
`insufficient` (abstention). Le rapport stable est enregistre
(`reviews`, `review_diagnostics`) et la seance passe `reviewed`.

### Anti-spoiler

Meme regle unique, etendue : un arbre (et chacun de ses travaux), le debriefing et
l'export JSON d'une seance deja revelee sont masques des qu'une seance non revelee
porte sur le meme echiquier. Teste par le client hostile (arbre, reanalyse,
debriefing, creation d'arbre d'etude, avant revelation ; puis seance revelee
re-masquee par une nouvelle seance). Le test de garde des routes couvre les quatre
nouvelles routes.

### Interface

- Seance revelee : panneau **Diagnostics** (qualite declaree, dimensions,
  diagnostics avec « Voir la position », tableau « Vos coups » avec verdicts) et
  **Arbre de reference** (raison et statut de chaque noeud, evaluation, detail des
  lignes d'un noeud, « Approfondir », « Analyser ce coup »), suivis tant que l'arbre
  se construit.
- Etude libre : « Construire l'arbre de reference » avec les reglages courants.
- Historique : qualite du debriefing.

## Corpus (DoD)

`backend/tests/corpus/positions.json` (version 1), un test par cas
(`test_corpus.py`), moteur reel a profondeur reduite (racine 14, noeuds 12 ;
profil « shallow » a 8 pour l'abstention) :

| groupe | cas | verdict attendu (et obtenu) |
|---|---|---|
| combinaisons forcees | C01, C03, C04, C05 | mat / fourchette trouves ; Dxf7+?? refute par Rxf7 |
| defenses critiques | D01, D02, D03 | ...d5, exd5, ...dxe5 non envisagees |
| positions calmes | Q01, Q02, Q03 | aucun verdict negatif |
| finales | E01, E02, E03 | nulle sans verdict ; Dd2+?? et Dc7?? (pat) refutes |
| promotion / e.p. / roques | P01, P02, A03 | a8=C refute (nulle), a8=D trouve ; exf6 e.p. et roques evalues |
| terminales | T01, T02 | sans trace ; coup illegal (certain) |
| abstention | A01, A02, C02 | profondeur 8 : aucun verdict, meme sur une gaffe ; gain moins rapide non puni |


## Mesures (VPS, 2 threads, hash 128 Mo, reglages par defaut)


## Limites

- **Corpus annote par l'implementeur**, sur des ecarts nets choisis pour etre robustes
  a faible profondeur ; il ne valide pas les seuils sur des positions fines. A relire
  par un joueur, et a enrichir de positions « calmes » ou le moteur hesite.
- Les evaluations sans tables de finales restent des centipions : en E01 (nulle
  theorique), le moteur donne +0,4 a plusieurs coups ; le rapport n'en tire aucun
  verdict negatif, mais liste des « candidats de premier plan » discutables.
- `score_swing` n'est pas encore une raison de selection ; « initiative »,
  « attaque », « incertain » ne sont pas comparables a une evaluation.

## Reste ouvert

- Conteneur orphelin du Lot 3 a supprimer par un administrateur :
  `docker rm -f cct-tests-run-46b3e3064f3e`.
- Lot 5 : UX (editeur trop haut a 1024 x 768, clavier, shadcn/ui), reglages.

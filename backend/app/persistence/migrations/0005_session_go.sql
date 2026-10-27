-- Lot 6 (retour utilisateur) : bouton « Go ». Une seance creee est prete mais
-- pas lancee (go_at NULL) : ni chronometre ni moteur. Go fixe go_at (debut du
-- chronometre, jamais affiche pendant la seance) et lance la reference.
-- Pas de nouvel etat : la seance reste `active`, ses triggers d'immuabilite
-- sont inchanges.
ALTER TABLE sessions ADD COLUMN go_at TEXT;
-- Choix fait a la creation, applique au Go : preparer la reference en arriere-plan.
ALTER TABLE sessions ADD COLUMN analysis_on_go INTEGER NOT NULL DEFAULT 1 CHECK (analysis_on_go IN (0, 1));
-- Les seances existantes ont commence a leur creation.
UPDATE sessions SET go_at = started_at;

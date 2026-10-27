-- Lot 4 : arbre de reference ramifie et debriefing (diagnostics).
--
-- Un noeud de l'arbre de reference est une position atteinte depuis la racine
-- de l'exercice par `path_json` (suite UCI). Son analyse est un travail
-- ordinaire portant sur la position racine + ce chemin : la regle de visibilite
-- (echiquier de la racine) s'applique donc telle quelle a tout l'arbre.

ALTER TABLE analysis_jobs ADD COLUMN node_path_json TEXT;  -- NULL = la position elle-meme

CREATE TABLE reference_trees (
    id            TEXT PRIMARY KEY,
    position_id   TEXT NOT NULL REFERENCES positions(id),
    session_id    TEXT REFERENCES sessions(id),             -- NULL = etude libre
    state         TEXT NOT NULL CHECK (state IN
        ('building', 'complete', 'budget_exhausted', 'node_limit', 'failed')),
    settings_json TEXT NOT NULL,                            -- budget, plafonds, profondeur locale
    revision      INTEGER NOT NULL DEFAULT 0,               -- incrementee a chaque changement de noeud
    pruned_count  INTEGER NOT NULL DEFAULT 0,               -- branches ecartees par la politique
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX reference_trees_position ON reference_trees (position_id);

CREATE TABLE reference_nodes (
    id               TEXT PRIMARY KEY,
    tree_id          TEXT NOT NULL REFERENCES reference_trees(id) ON DELETE CASCADE,
    parent_id        TEXT REFERENCES reference_nodes(id) ON DELETE CASCADE,
    path_json        TEXT NOT NULL,                         -- '[]' pour la racine
    ply              INTEGER NOT NULL,
    move_uci         TEXT,
    move_san         TEXT,
    fen              TEXT NOT NULL,
    job_id           TEXT REFERENCES analysis_jobs(id),
    previous_job_id  TEXT REFERENCES analysis_jobs(id),     -- analyse precedente, si reanalyse
    status           TEXT NOT NULL CHECK (status IN
        ('queued', 'provisional', 'depth_met', 'budget_exhausted', 'incomplete', 'failed', 'pruned_by_policy',
         'terminal')),
    selection_reason TEXT NOT NULL CHECK (selection_reason IN
        ('root', 'top_rank', 'opponent_best_defense', 'opponent_alternative', 'user_branch',
         'user_requested_reanalysis')),
    reanalysed       INTEGER NOT NULL DEFAULT 0 CHECK (reanalysed IN (0, 1)),
    created_at       TEXT NOT NULL,
    UNIQUE (tree_id, path_json)
);
CREATE INDEX reference_nodes_tree ON reference_nodes (tree_id, parent_id);
CREATE INDEX reference_nodes_job ON reference_nodes (job_id);

ALTER TABLE sessions ADD COLUMN reference_tree_id TEXT REFERENCES reference_trees(id);

-- Rapport de debriefing : recalcule tant que l'arbre evolue, enregistre quand
-- il est stable (la seance passe alors `reviewed`).
CREATE TABLE reviews (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    tree_revision INTEGER,
    quality       TEXT NOT NULL CHECK (quality IN ('final', 'provisional', 'insufficient')),
    report_json   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX reviews_session ON reviews (session_id, created_at);

CREATE TABLE review_diagnostics (
    id                TEXT PRIMARY KEY,
    review_id         TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    category          TEXT NOT NULL CHECK (category IN
        ('candidate_found', 'candidate_omitted', 'critical_defense_omitted', 'illegal_continuation',
         'evaluation_mismatch', 'acceptable_alternative', 'tactical_refutation', 'unverified', 'no_trace')),
    user_node_id      TEXT,
    reference_node_id TEXT,
    evidence_json     TEXT NOT NULL,
    verdict           TEXT NOT NULL,
    explanation       TEXT NOT NULL,
    certainty         TEXT NOT NULL CHECK (certainty IN ('certain', 'verified', 'uncertain', 'undetermined'))
);
CREATE INDEX review_diagnostics_review ON review_diagnostics (review_id);

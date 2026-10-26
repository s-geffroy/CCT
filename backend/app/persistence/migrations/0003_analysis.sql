-- Lot 3 : travaux d'analyse Stockfish et lignes calculees.

CREATE TABLE analysis_jobs (
    id               TEXT PRIMARY KEY,
    position_id      TEXT NOT NULL REFERENCES positions(id),
    session_id       TEXT REFERENCES sessions(id),       -- NULL = etude libre (mode A)
    purpose          TEXT NOT NULL CHECK (purpose IN ('study', 'initial_reference')),
    scope            TEXT NOT NULL CHECK (scope = 'root'),
    priority         INTEGER NOT NULL,
    state            TEXT NOT NULL CHECK (state IN
        ('queued', 'running', 'complete_depth', 'budget_exhausted', 'incomplete',
         'cancelled', 'failed', 'interrupted', 'terminal')),
    settings_json    TEXT NOT NULL,                      -- profondeur, MultiPV, budget, moteur
    cache_key        TEXT NOT NULL,
    revision         INTEGER NOT NULL DEFAULT 0,         -- incrementee a chaque instantane publie
    stages_json      TEXT NOT NULL DEFAULT '{}',         -- palier -> secondes
    legal_moves      INTEGER,
    multipv          INTEGER,
    elapsed_s        REAL,
    nodes            INTEGER,
    nps              INTEGER,
    error            TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    ended_at         TEXT
);
CREATE INDEX analysis_jobs_queue ON analysis_jobs (state, priority, created_at);
CREATE INDEX analysis_jobs_cache ON analysis_jobs (cache_key, state);
CREATE INDEX analysis_jobs_session ON analysis_jobs (session_id);

-- Une ligne par premier coup et par instantane conserve (paliers atteints,
-- puis resultat final) : on garde les points stables, la derniere version
-- est celle de plus grand `snapshot`.
CREATE TABLE analysis_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    snapshot      INTEGER NOT NULL,                     -- revision du travail
    stage         INTEGER,                              -- palier atteste (NULL = final)
    multipv_index INTEGER NOT NULL,
    root_move_uci TEXT NOT NULL,
    pv_uci_json   TEXT NOT NULL,
    depth         INTEGER NOT NULL,
    exact_depth   INTEGER NOT NULL,
    seldepth      INTEGER,
    nodes         INTEGER,
    score_type    TEXT NOT NULL CHECK (score_type IN ('cp', 'mate', 'unknown')),
    score_value   INTEGER,
    score_bound   TEXT CHECK (score_bound IN ('lower', 'upper')),
    is_final      INTEGER NOT NULL CHECK (is_final IN (0, 1))
);
CREATE INDEX analysis_lines_job ON analysis_lines (job_id, snapshot, multipv_index);

-- Reference moteur d'une seance (un travail peut etre partage via le cache).
ALTER TABLE sessions ADD COLUMN reference_job_id TEXT REFERENCES analysis_jobs(id);

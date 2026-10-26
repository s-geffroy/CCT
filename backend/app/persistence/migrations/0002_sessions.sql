-- Lot 2 : seances d'entrainement B (mental) et C (arbre personnel).
-- L'immuabilite apres soumission est garantie par la base elle-meme (triggers),
-- pas seulement par le code applicatif.

CREATE TABLE sessions (
    id                   TEXT PRIMARY KEY,
    position_id          TEXT NOT NULL REFERENCES positions(id),
    mode                 TEXT NOT NULL CHECK (mode IN ('mental', 'tree')),
    state                TEXT NOT NULL CHECK (state IN ('active', 'submitted', 'revealed', 'reviewed', 'abandoned')),
    revision             INTEGER NOT NULL DEFAULT 1,
    tree_cursor          INTEGER NOT NULL DEFAULT 0,   -- etat courant dans tree_states (annuler/retablir)
    allow_text_notes     INTEGER NOT NULL CHECK (allow_text_notes IN (0, 1)),
    notes                TEXT NOT NULL DEFAULT '',
    lines_text           TEXT NOT NULL DEFAULT '',     -- mode B : variantes ecrites, une par ligne
    self_assessment_json TEXT,
    started_at           TEXT NOT NULL,
    submitted_at         TEXT,
    revealed_at          TEXT,
    abandoned_at         TEXT,
    duration_ms          INTEGER
);
CREATE INDEX sessions_started ON sessions (started_at);
CREATE INDEX sessions_position ON sessions (position_id);

-- Arbre utilisateur courant (vue materialisee de l'etat tree_cursor).
-- parent_id NULL = coup joue depuis la position de la seance.
CREATE TABLE user_nodes (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_id        TEXT REFERENCES user_nodes(id) ON DELETE CASCADE,
    order_index      INTEGER NOT NULL,
    move_uci         TEXT NOT NULL,
    move_san         TEXT NOT NULL,
    fen_after        TEXT NOT NULL,
    comment          TEXT NOT NULL DEFAULT '',
    human_assessment TEXT CHECK (human_assessment IN
        ('white_better', 'black_better', 'equal', 'initiative', 'attack', 'unclear')),
    created_at       TEXT NOT NULL
);
CREATE INDEX user_nodes_tree ON user_nodes (session_id, parent_id, order_index);

-- Etats successifs de l'arbre, pour annuler/retablir cote serveur.
CREATE TABLE tree_states (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

-- Tentative soumise : jamais modifiee.
CREATE TABLE attempt_snapshots (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL UNIQUE REFERENCES sessions(id),
    snapshot_json TEXT NOT NULL,
    submitted_at  TEXT NOT NULL
);

CREATE TRIGGER attempt_snapshots_no_update BEFORE UPDATE ON attempt_snapshots
BEGIN SELECT RAISE(ABORT, 'tentative soumise immuable'); END;

CREATE TRIGGER attempt_snapshots_no_delete BEFORE DELETE ON attempt_snapshots
BEGIN SELECT RAISE(ABORT, 'tentative soumise immuable'); END;

CREATE TRIGGER user_nodes_frozen_insert BEFORE INSERT ON user_nodes
WHEN (SELECT state FROM sessions WHERE id = NEW.session_id) <> 'active'
BEGIN SELECT RAISE(ABORT, 'seance figee'); END;

CREATE TRIGGER user_nodes_frozen_update BEFORE UPDATE ON user_nodes
WHEN (SELECT state FROM sessions WHERE id = OLD.session_id) <> 'active'
BEGIN SELECT RAISE(ABORT, 'seance figee'); END;

CREATE TRIGGER user_nodes_frozen_delete BEFORE DELETE ON user_nodes
WHEN (SELECT state FROM sessions WHERE id = OLD.session_id) <> 'active'
BEGIN SELECT RAISE(ABORT, 'seance figee'); END;

CREATE TRIGGER tree_states_frozen BEFORE INSERT ON tree_states
WHEN (SELECT state FROM sessions WHERE id = NEW.session_id) <> 'active'
BEGIN SELECT RAISE(ABORT, 'seance figee'); END;

-- Contenu de la tentative fige des la soumission.
CREATE TRIGGER sessions_frozen_content BEFORE UPDATE OF notes, lines_text, self_assessment_json, tree_cursor ON sessions
WHEN OLD.state <> 'active'
BEGIN SELECT RAISE(ABORT, 'seance figee'); END;

-- Transitions d'etat autorisees uniquement.
CREATE TRIGGER sessions_state_transitions BEFORE UPDATE OF state ON sessions
WHEN NEW.state <> OLD.state AND NOT (
       (OLD.state = 'active'    AND NEW.state IN ('submitted', 'abandoned'))
    OR (OLD.state = 'submitted' AND NEW.state = 'revealed')
    OR (OLD.state = 'revealed'  AND NEW.state = 'reviewed'))
BEGIN SELECT RAISE(ABORT, 'transition d''etat interdite'); END;

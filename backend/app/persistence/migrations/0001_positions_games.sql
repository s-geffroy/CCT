-- Lot 1 : imports PGN, parties, arbres importes, instantanes de position.
-- Les identifiants sont des UUID (texte). Dates ISO 8601 UTC.

CREATE TABLE pgn_imports (
    id           TEXT PRIMARY KEY,
    raw_pgn      TEXT NOT NULL,          -- entree d'origine, jamais modifiee
    sha256       TEXT NOT NULL,
    games_count  INTEGER NOT NULL,
    truncated    INTEGER NOT NULL CHECK (truncated IN (0, 1)),
    imported_at  TEXT NOT NULL
);

CREATE TABLE games (
    id                  TEXT PRIMARY KEY,
    import_id           TEXT NOT NULL REFERENCES pgn_imports(id) ON DELETE CASCADE,
    game_index          INTEGER NOT NULL,
    headers_json        TEXT NOT NULL,
    parse_warnings_json TEXT NOT NULL,
    history_known       INTEGER NOT NULL CHECK (history_known IN (0, 1)),
    root_node_id        TEXT NOT NULL,
    nodes_count         INTEGER NOT NULL,
    imported_at         TEXT NOT NULL,
    UNIQUE (import_id, game_index)
);

CREATE TABLE game_nodes (
    id               TEXT PRIMARY KEY,
    game_id          TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    parent_id        TEXT REFERENCES game_nodes(id) ON DELETE CASCADE,
    order_index      INTEGER NOT NULL,   -- 0 = suite principale
    ply              INTEGER NOT NULL,
    move_number      INTEGER,            -- NULL pour la racine
    color            TEXT CHECK (color IN ('white', 'black')),
    uci              TEXT,
    san              TEXT,
    fen              TEXT NOT NULL,
    comment          TEXT NOT NULL,
    starting_comment TEXT NOT NULL,
    nags_json        TEXT NOT NULL
);
CREATE INDEX game_nodes_tree ON game_nodes (game_id, parent_id, order_index);

-- Instantane immuable : la position et le contexte de regles qui l'accompagne.
-- history_uci_json NULL = historique inconnu (FEN isolee, editeur).
CREATE TABLE positions (
    id                TEXT PRIMARY KEY,
    context_key       TEXT NOT NULL UNIQUE,
    variant           TEXT NOT NULL CHECK (variant = 'standard'),
    fen               TEXT NOT NULL,
    initial_fen       TEXT NOT NULL,
    history_uci_json  TEXT,
    history_complete  INTEGER NOT NULL CHECK (history_complete IN (0, 1)),
    source_type       TEXT NOT NULL CHECK (source_type IN ('fen', 'pgn', 'editor')),
    source_game_id    TEXT REFERENCES games(id) ON DELETE SET NULL,
    source_node_id    TEXT REFERENCES game_nodes(id) ON DELETE SET NULL,
    turn              TEXT NOT NULL CHECK (turn IN ('white', 'black')),
    legal_moves_count INTEGER NOT NULL,
    outcome           TEXT,
    claimable_draw    TEXT,
    validation_status TEXT NOT NULL CHECK (validation_status = 'valid'),
    created_at        TEXT NOT NULL
);
CREATE INDEX positions_created ON positions (created_at);

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

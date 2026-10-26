"""Acces aux donnees : imports PGN, parties, arbres importes, instantanes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass

from ..domain.pgn import PgnImport
from ..domain.snapshots import Snapshot, history_san
from .db import transaction, utc_now


# --------------------------------------------------------------------- PGN

def save_import(conn: sqlite3.Connection, raw_pgn: str, result: PgnImport) -> tuple[str, list[dict]]:
    """Enregistre l'entree brute et toutes ses parties en une seule transaction."""
    import_id = str(uuid.uuid4())
    now = utc_now()
    games = []
    with transaction(conn):
        conn.execute(
            "INSERT INTO pgn_imports (id, raw_pgn, sha256, games_count, truncated, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
            (import_id, raw_pgn, hashlib.sha256(raw_pgn.encode()).hexdigest(), len(result.games), int(result.truncated), now),
        )
        for game in result.games:
            game_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO games (id, import_id, game_index, headers_json, parse_warnings_json, history_known,"
                " root_node_id, nodes_count, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (game_id, import_id, game.index, json.dumps(game.headers, ensure_ascii=False),
                 json.dumps(game.warnings, ensure_ascii=False), int(game.history_known), game.root_id,
                 len(game.nodes), now),
            )
            # Parents avant enfants (ordre d'insertion du parcours) : la cle
            # etrangere parent_id est satisfaite a chaque ligne.
            rows = []
            for node in game.nodes.values():
                parent = game.nodes.get(node.parent_id) if node.parent_id else None
                order = parent.children.index(node.id) if parent else 0
                rows.append((node.id, game_id, node.parent_id, order, node.ply, node.move_number, node.color,
                             node.uci, node.san, node.fen, node.comment, node.starting_comment, json.dumps(node.nags)))
            conn.executemany(
                "INSERT INTO game_nodes (id, game_id, parent_id, order_index, ply, move_number, color, uci, san, fen,"
                " comment, starting_comment, nags_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            games.append(_game_dict(conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()))
    return import_id, games


def _game_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "import_id": row["import_id"],
        "index": row["game_index"],
        "headers": json.loads(row["headers_json"]),
        "warnings": json.loads(row["parse_warnings_json"]),
        "history_known": bool(row["history_known"]),
        "root_node_id": row["root_node_id"],
        "nodes_count": row["nodes_count"],
        "imported_at": row["imported_at"],
    }


def get_game(conn: sqlite3.Connection, game_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    return _game_dict(row) if row else None


def list_games(conn: sqlite3.Connection, limit: int, offset: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM games ORDER BY imported_at DESC, game_index LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [_game_dict(r) for r in rows]


def _node_dict(row: sqlite3.Row, children: list[str]) -> dict:
    return {
        "id": row["id"],
        "parent_id": row["parent_id"],
        "ply": row["ply"],
        "move_number": row["move_number"],
        "color": row["color"],
        "uci": row["uci"],
        "san": row["san"],
        "fen": row["fen"],
        "comment": row["comment"],
        "starting_comment": row["starting_comment"],
        "nags": json.loads(row["nags_json"]),
        "children": children,
    }


@dataclass
class TreePage:
    root_id: str
    nodes: dict[str, dict]
    truncated: bool
    frontier: list[str]  # noeuds dont les enfants n'ont pas ete renvoyes


def get_tree(conn: sqlite3.Connection, game_id: str, root_id: str, max_nodes: int) -> TreePage | None:
    """Sous-arbre a partir de `root_id`, en largeur, borne a `max_nodes` noeuds."""
    rows = conn.execute(
        "SELECT * FROM game_nodes WHERE game_id = ? ORDER BY parent_id, order_index", (game_id,)
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    if root_id not in by_id:
        return None
    children: dict[str, list[str]] = {}
    for r in rows:
        if r["parent_id"] is not None:
            children.setdefault(r["parent_id"], []).append(r["id"])

    nodes: dict[str, dict] = {}
    frontier: list[str] = []
    queue = deque([root_id])
    while queue:
        node_id = queue.popleft()
        kids = children.get(node_id, [])
        nodes[node_id] = _node_dict(by_id[node_id], kids)
        if len(nodes) + len(queue) + len(kids) > max_nodes and kids:
            frontier.append(node_id)
            continue
        queue.extend(kids)
    # Les noeuds de la frontiere gardent la liste de leurs enfants (non charges) :
    # le client sait qu'il y a une suite a demander.
    return TreePage(root_id=root_id, nodes=nodes, truncated=bool(frontier), frontier=frontier)


def get_node(conn: sqlite3.Connection, node_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM game_nodes WHERE id = ?", (node_id,)).fetchone()


def path_from_root(conn: sqlite3.Connection, node_id: str) -> list[str]:
    """Suite UCI de la racine de la partie jusqu'a ce noeud."""
    rows = conn.execute(
        """
        WITH RECURSIVE ancestors(id, parent_id, uci, ply) AS (
            SELECT id, parent_id, uci, ply FROM game_nodes WHERE id = ?
            UNION ALL
            SELECT g.id, g.parent_id, g.uci, g.ply FROM game_nodes g JOIN ancestors a ON g.id = a.parent_id
        )
        SELECT uci FROM ancestors WHERE uci IS NOT NULL ORDER BY ply
        """,
        (node_id,),
    ).fetchall()
    return [r["uci"] for r in rows]


# --------------------------------------------------------------- positions

def _position_dict(row: sqlite3.Row) -> dict:
    history = json.loads(row["history_uci_json"]) if row["history_uci_json"] is not None else None
    return {
        "id": row["id"],
        "variant": row["variant"],
        "fen": row["fen"],
        "initial_fen": row["initial_fen"],
        "history_uci": history,
        "history_san": history_san(row["initial_fen"], history),
        "history_complete": bool(row["history_complete"]),
        "source_type": row["source_type"],
        "source_game_id": row["source_game_id"],
        "source_node_id": row["source_node_id"],
        "turn": row["turn"],
        "legal_moves_count": row["legal_moves_count"],
        "outcome": row["outcome"],
        "claimable_draw": row["claimable_draw"],
        "created_at": row["created_at"],
    }


def create_position(
    conn: sqlite3.Connection, snap: Snapshot, source_type: str,
    game_id: str | None = None, node_id: str | None = None,
) -> tuple[dict, bool]:
    """Cree l'instantane, ou renvoie l'existant de meme contexte (idempotent)."""
    with transaction(conn):
        existing = conn.execute("SELECT * FROM positions WHERE context_key = ?", (snap.context_key,)).fetchone()
        if existing:
            return _position_dict(existing), False
        position_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO positions (id, context_key, variant, fen, initial_fen, history_uci_json, history_complete,"
            " source_type, source_game_id, source_node_id, turn, legal_moves_count, outcome, claimable_draw,"
            " validation_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid', ?)",
            (position_id, snap.context_key, snap.variant, snap.fen, snap.initial_fen,
             json.dumps(list(snap.history_uci)) if snap.history_uci is not None else None,
             int(snap.history_complete), source_type, game_id, node_id, snap.turn, snap.legal_moves_count,
             snap.outcome, snap.claimable_draw, utc_now()),
        )
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    return _position_dict(row), True


def get_position(conn: sqlite3.Connection, position_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    return _position_dict(row) if row else None


def list_positions(conn: sqlite3.Connection, limit: int, offset: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM positions ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [_position_dict(r) for r in rows]

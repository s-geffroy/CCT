"""Seances : creation, mutations conditionnelles, annuler/retablir, soumission.

Toute mutation passe par `mutate()` : dans une transaction IMMEDIATE, on relit
la seance, on verifie son etat et `expected_revision`, on ecrit, puis on
incremente la revision. Deux onglets ou un double clic ne s'ecrasent donc pas.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime

from ..domain.errors import DomainError, NotFound
from ..domain.training import Conflict, TreeState
from .db import transaction, utc_now


class StateError(DomainError):
    status_code = 409


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def create(conn: sqlite3.Connection, position_id: str, mode: str, allow_text_notes: bool,
           analysis_on_go: bool = True) -> str:
    """Seance prete, pas lancee : `go_at` reste vide jusqu'au Go."""
    session_id = str(uuid.uuid4())
    now = utc_now()
    with transaction(conn):
        if conn.execute("SELECT 1 FROM positions WHERE id = ?", (position_id,)).fetchone() is None:
            raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
        conn.execute(
            "INSERT INTO sessions (id, position_id, mode, state, allow_text_notes, started_at, analysis_on_go)"
            " VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (session_id, position_id, mode, int(allow_text_notes), now, int(analysis_on_go)),
        )
        conn.execute("INSERT INTO tree_states (session_id, seq, state_json, created_at) VALUES (?, 0, '{}', ?)",
                     (session_id, now))
    return session_id


def get(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise NotFound("SESSION_NOT_FOUND", "Seance inconnue.")
    return row


def load_tree(conn: sqlite3.Connection, session_id: str) -> TreeState:
    rows = conn.execute("SELECT * FROM user_nodes WHERE session_id = ?", (session_id,)).fetchall()
    return {
        r["id"]: {
            "id": r["id"], "parent_id": r["parent_id"], "order_index": r["order_index"],
            "move_uci": r["move_uci"], "move_san": r["move_san"], "fen_after": r["fen_after"],
            "comment": r["comment"], "human_assessment": r["human_assessment"], "created_at": r["created_at"],
        }
        for r in rows
    }


def undo_redo_flags(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[bool, bool]:
    has_next = conn.execute(
        "SELECT 1 FROM tree_states WHERE session_id = ? AND seq = ?", (row["id"], row["tree_cursor"] + 1)
    ).fetchone()
    return row["tree_cursor"] > 0, has_next is not None


def mutate(conn: sqlite3.Connection, session_id: str, expected_revision: int,
           action: Callable[[sqlite3.Row], None], *, require_state: str = "active") -> None:
    with transaction(conn):
        row = get(conn, session_id)
        if row["state"] != require_state:
            raise StateError("SESSION_STATE", f"Operation impossible : seance a l'etat « {row['state']} ».",
                             {"state": row["state"]})
        if row["revision"] != expected_revision:
            raise Conflict("REVISION_CONFLICT", "La seance a change entre-temps : recharger.",
                           {"current_revision": row["revision"]})
        action(row)
        conn.execute("UPDATE sessions SET revision = revision + 1 WHERE id = ?", (session_id,))


def _depth_order(state: TreeState) -> list[dict]:
    """Parents avant enfants (contrainte de cle etrangere)."""
    depth: dict[str, int] = {}

    def d(node_id: str) -> int:
        chain = []
        current: str | None = node_id
        while current is not None and current not in depth:
            chain.append(current)
            current = state[current]["parent_id"]
        base = depth[current] if current is not None else -1
        for nid in reversed(chain):
            base += 1
            depth[nid] = base
        return depth[node_id]

    return sorted(state.values(), key=lambda n: d(n["id"]))


def _materialize(conn: sqlite3.Connection, session_id: str, state: TreeState) -> None:
    conn.execute("DELETE FROM user_nodes WHERE session_id = ?", (session_id,))
    conn.executemany(
        "INSERT INTO user_nodes (id, session_id, parent_id, order_index, move_uci, move_san, fen_after, comment,"
        " human_assessment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(n["id"], session_id, n["parent_id"], n["order_index"], n["move_uci"], n["move_san"], n["fen_after"],
          n["comment"], n["human_assessment"], n["created_at"]) for n in _depth_order(state)],
    )


def write_tree(conn: sqlite3.Connection, row: sqlite3.Row, state: TreeState) -> None:
    """Nouvel etat de l'arbre : l'historique de retablissement est abandonne."""
    require_started(row)
    cursor = row["tree_cursor"] + 1
    conn.execute("DELETE FROM tree_states WHERE session_id = ? AND seq >= ?", (row["id"], cursor))
    conn.execute("INSERT INTO tree_states (session_id, seq, state_json, created_at) VALUES (?, ?, ?, ?)",
                 (row["id"], cursor, json.dumps(state), utc_now()))
    conn.execute("UPDATE sessions SET tree_cursor = ? WHERE id = ?", (cursor, row["id"]))
    _materialize(conn, row["id"], state)


def move_cursor(conn: sqlite3.Connection, row: sqlite3.Row, step: int) -> None:
    require_started(row)
    target = row["tree_cursor"] + step
    state_row = conn.execute(
        "SELECT state_json FROM tree_states WHERE session_id = ? AND seq = ?", (row["id"], target)
    ).fetchone()
    if target < 0 or state_row is None:
        raise StateError("NOTHING_TO_" + ("UNDO" if step < 0 else "REDO"),
                         "Rien a annuler." if step < 0 else "Rien a retablir.")
    conn.execute("UPDATE sessions SET tree_cursor = ? WHERE id = ?", (target, row["id"]))
    _materialize(conn, row["id"], json.loads(state_row["state_json"]))


def set_notes(conn: sqlite3.Connection, row: sqlite3.Row, notes: str | None, lines_text: str | None) -> None:
    require_started(row)
    if notes is not None:
        conn.execute("UPDATE sessions SET notes = ? WHERE id = ?", (notes, row["id"]))
    if lines_text is not None:
        conn.execute("UPDATE sessions SET lines_text = ? WHERE id = ?", (lines_text, row["id"]))


def submit(conn: sqlite3.Connection, row: sqlite3.Row, self_assessment: dict | None, snapshot: dict) -> None:
    require_started(row)
    now = utc_now()
    # Duree de reflexion : depuis le Go (le moteur calculait pendant ce temps).
    duration = int((_parse_ts(now) - _parse_ts(row["go_at"] or row["started_at"])).total_seconds() * 1000)
    # Le contenu est ecrit AVANT le changement d'etat : apres, les triggers le figent.
    conn.execute("UPDATE sessions SET self_assessment_json = ? WHERE id = ?",
                 (json.dumps(self_assessment) if self_assessment is not None else None, row["id"]))
    conn.execute("INSERT INTO attempt_snapshots (id, session_id, snapshot_json, submitted_at) VALUES (?, ?, ?, ?)",
                 (str(uuid.uuid4()), row["id"], json.dumps(snapshot, ensure_ascii=False), now))
    conn.execute("UPDATE sessions SET state = 'submitted', submitted_at = ?, duration_ms = ? WHERE id = ?",
                 (now, duration, row["id"]))


def reveal(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    conn.execute("UPDATE sessions SET state = 'revealed', revealed_at = ? WHERE id = ?", (utc_now(), row["id"]))


def abandon(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    conn.execute("UPDATE sessions SET state = 'abandoned', abandoned_at = ? WHERE id = ?", (utc_now(), row["id"]))


def get_attempt(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM attempt_snapshots WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    return {"submitted_at": row["submitted_at"], **json.loads(row["snapshot_json"])}


def history(conn: sqlite3.Connection, limit: int, offset: int) -> list[dict]:
    rows = conn.execute(
        "SELECT s.id, s.mode, s.state, s.started_at, s.go_at, s.submitted_at, s.revealed_at, s.duration_ms,"
        " p.id AS position_id, p.fen,"
        " (SELECT r.quality FROM reviews r WHERE r.session_id = s.id ORDER BY r.created_at DESC LIMIT 1) AS review_quality"
        " FROM sessions s JOIN positions p ON p.id = s.position_id"
        " ORDER BY s.started_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def start(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    """Go : debut du chronometre (jamais affiche pendant la seance)."""
    if row["go_at"] is not None:
        raise StateError("ALREADY_STARTED", "Seance deja lancee.")
    conn.execute("UPDATE sessions SET go_at = ? WHERE id = ?", (utc_now(), row["id"]))


def require_started(row: sqlite3.Row) -> None:
    if row["go_at"] is None:
        raise StateError("SESSION_NOT_STARTED", "Appuyez d'abord sur Go pour commencer la seance.")


def previous_attempts(conn: sqlite3.Connection, row: sqlite3.Row, board_key) -> list[dict]:
    """Autres tentatives lancees sur le meme probleme (meme echiquier), pour
    comparer les durees de reflexion. Jamais avant la fin de la seance."""
    fen = conn.execute("SELECT fen FROM positions WHERE id = ?", (row["position_id"],)).fetchone()["fen"]
    rows = conn.execute(
        "SELECT s.id, s.mode, s.state, s.go_at, s.duration_ms, p.fen FROM sessions s"
        " JOIN positions p ON p.id = s.position_id WHERE s.id <> ? AND s.go_at IS NOT NULL ORDER BY s.go_at DESC",
        (row["id"],)).fetchall()
    return [{k: r[k] for k in ("id", "mode", "state", "go_at", "duration_ms")}
            for r in rows if board_key(r["fen"]) == board_key(fen)]

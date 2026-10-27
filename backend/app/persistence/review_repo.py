"""Rapports de debriefing enregistres (un par revision stable de l'arbre)."""
from __future__ import annotations

import json
import sqlite3
import uuid

from .db import transaction, utc_now


def latest(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reviews WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,)).fetchone()


def save(conn: sqlite3.Connection, session: sqlite3.Row, tree_revision: int | None, report: dict) -> str:
    """Enregistre le rapport et ses diagnostics ; la seance revelee devient
    `reviewed` (rapport affichable avec qualite declaree, pas « verite »)."""
    review_id = str(uuid.uuid4())
    with transaction(conn):
        conn.execute(
            "INSERT INTO reviews (id, session_id, tree_revision, quality, report_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (review_id, session["id"], tree_revision, report["quality"], json.dumps(report, ensure_ascii=False),
             utc_now()))
        conn.executemany(
            "INSERT INTO review_diagnostics (id, review_id, category, user_node_id, reference_node_id, evidence_json,"
            " verdict, explanation, certainty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(str(uuid.uuid4()), review_id, d["category"], d["user_node_id"], d["reference_node_id"],
              json.dumps(d["evidence"], ensure_ascii=False), d["verdict"], d["explanation"], d["certainty"])
             for d in report["diagnostics"]])
        conn.execute("UPDATE sessions SET state = 'reviewed' WHERE id = ? AND state = 'revealed'", (session["id"],))
    return review_id

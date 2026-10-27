"""Arbres de reference : noeuds, statuts derives des travaux, vues.

Le statut d'un noeud suit celui de son travail d'analyse ; il n'est jamais
« mauvaise variante » : non explore, ecarte par la politique, en echec...
"""
from __future__ import annotations

import json
import sqlite3
import uuid

import chess

from ..domain.errors import NotFound
from . import analysis_repo, repo
from .db import transaction, utc_now

NODE_STATUS = {
    "queued": "queued",
    "running": "provisional",
    "complete_depth": "depth_met",
    "budget_exhausted": "budget_exhausted",
    "incomplete": "incomplete",
    "cancelled": "failed",
    "failed": "failed",
    "interrupted": "failed",
    "terminal": "terminal",
}
PENDING = ("queued", "provisional")
ANALYSED = ("depth_met", "budget_exhausted", "incomplete")
# Deux enveloppes de memes plafonds : la preparation automatique, lancee pendant
# que le joueur calcule, ne doit pas epuiser la verification de ses branches.
USER_REASONS = ("user_branch",)
AUTO_REASONS = ("top_rank", "opponent_best_defense", "opponent_alternative")
USABLE_JOB_STATES = ("complete_depth", "budget_exhausted", "incomplete")


def get_tree(conn: sqlite3.Connection, tree_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM reference_trees WHERE id = ?", (tree_id,)).fetchone()
    if row is None:
        raise NotFound("TREE_NOT_FOUND", "Arbre de reference inconnu.")
    return row


def path_of(row: sqlite3.Row) -> tuple[str, ...]:
    return tuple(json.loads(row["path_json"]))


def nodes(conn: sqlite3.Connection, tree_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reference_nodes WHERE tree_id = ? ORDER BY ply, created_at", (tree_id,)).fetchall()


def create_tree(conn: sqlite3.Connection, *, position_id: str, session_id: str | None, root_job: sqlite3.Row,
                root_fen: str, settings: dict) -> str:
    tree_id, now = str(uuid.uuid4()), utc_now()
    with transaction(conn):
        conn.execute(
            "INSERT INTO reference_trees (id, position_id, session_id, state, settings_json, created_at, updated_at)"
            " VALUES (?, ?, ?, 'building', ?, ?, ?)",
            (tree_id, position_id, session_id, json.dumps(settings), now, now))
        conn.execute(
            "INSERT INTO reference_nodes (id, tree_id, parent_id, path_json, ply, fen, job_id, status, selection_reason,"
            " created_at) VALUES (?, ?, NULL, '[]', 0, ?, ?, ?, 'root', ?)",
            (str(uuid.uuid4()), tree_id, root_fen, root_job["id"], NODE_STATUS[root_job["state"]], now))
        if session_id is not None:
            conn.execute("UPDATE sessions SET reference_tree_id = ? WHERE id = ?", (tree_id, session_id))
    return tree_id


def insert_node(conn: sqlite3.Connection, *, tree_id: str, parent_id: str, path: tuple[str, ...], move_uci: str,
                move_san: str, fen: str, job_id: str | None, status: str, reason: str) -> None:
    with transaction(conn):
        cur = conn.execute(
            "INSERT OR IGNORE INTO reference_nodes (id, tree_id, parent_id, path_json, ply, move_uci, move_san, fen,"
            " job_id, status, selection_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), tree_id, parent_id, json.dumps(list(path)), len(path), move_uci, move_san, fen,
             job_id, status, reason, utc_now()))
        if cur.rowcount:
            _bump(conn, tree_id)


def replace_job(conn: sqlite3.Connection, node: sqlite3.Row, job: sqlite3.Row, *, reanalysed: bool) -> None:
    """Nouvelle analyse d'un noeud ; la precedente reste lisible tant que la
    nouvelle n'a rien produit."""
    with transaction(conn):
        conn.execute(
            "UPDATE reference_nodes SET job_id = ?, previous_job_id = ?, status = ?, reanalysed = ? WHERE id = ?",
            (job["id"], node["job_id"], NODE_STATUS[job["state"]], int(reanalysed or node["reanalysed"]), node["id"]))
        _bump(conn, node["tree_id"])


def refresh_statuses(conn: sqlite3.Connection, tree_id: str) -> None:
    with transaction(conn):
        rows = conn.execute(
            "SELECT n.id, n.status, j.state FROM reference_nodes n JOIN analysis_jobs j ON j.id = n.job_id"
            " WHERE n.tree_id = ?", (tree_id,)).fetchall()
        changed = False
        for r in rows:
            status = NODE_STATUS[r["state"]]
            if status != r["status"]:
                conn.execute("UPDATE reference_nodes SET status = ? WHERE id = ?", (status, r["id"]))
                changed = True
        if changed:
            _bump(conn, tree_id)


def set_state(conn: sqlite3.Connection, tree_id: str, state: str, pruned: int | None = None) -> None:
    with transaction(conn):
        row = get_tree(conn, tree_id)
        new_pruned = row["pruned_count"] if pruned is None else pruned
        if row["state"] != state or row["pruned_count"] != new_pruned:
            conn.execute("UPDATE reference_trees SET state = ?, pruned_count = ?, revision = revision + 1,"
                         " updated_at = ? WHERE id = ?", (state, new_pruned, utc_now(), tree_id))


def _bump(conn: sqlite3.Connection, tree_id: str) -> None:
    conn.execute("UPDATE reference_trees SET revision = revision + 1, updated_at = ? WHERE id = ?", (utc_now(), tree_id))


def trees_for_job(conn: sqlite3.Connection, job_id: str) -> list[str]:
    rows = conn.execute("SELECT DISTINCT tree_id FROM reference_nodes WHERE job_id = ?", (job_id,)).fetchall()
    return [r["tree_id"] for r in rows]


def building_trees(conn: sqlite3.Connection) -> list[str]:
    return [r["id"] for r in conn.execute("SELECT id FROM reference_trees WHERE state = 'building'").fetchall()]


def study_trees(conn: sqlite3.Connection, position_id: str, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reference_trees WHERE position_id = ? AND session_id IS NULL ORDER BY created_at DESC LIMIT ?",
        (position_id, limit)).fetchall()


def tree_for_root_job(conn: sqlite3.Connection, job_id: str, settings: dict) -> sqlite3.Row | None:
    """Arbre d'etude deja construit sur la meme analyse racine et les memes reglages."""
    rows = conn.execute(
        "SELECT t.* FROM reference_trees t JOIN reference_nodes n ON n.tree_id = t.id AND n.ply = 0"
        " WHERE n.job_id = ? AND t.session_id IS NULL ORDER BY t.created_at DESC", (job_id,)).fetchall()
    return next((r for r in rows if json.loads(r["settings_json"]) == settings), None)


# --------------------------------------------------------------- lectures

def lines_job_id(conn: sqlite3.Connection, node: sqlite3.Row) -> str | None:
    """Travail dont on lit les lignes : l'analyse courante si elle a produit
    quelque chose, sinon la precedente (reanalyse en cours ou en echec)."""
    if node["job_id"] is None:
        return None
    if node["previous_job_id"] is None:
        return node["job_id"]
    state = conn.execute("SELECT state FROM analysis_jobs WHERE id = ?", (node["job_id"],)).fetchone()["state"]
    return node["job_id"] if state in USABLE_JOB_STATES else node["previous_job_id"]


def raw_lines(conn: sqlite3.Connection, job_id: str | None) -> list[dict]:
    """Lignes sans notation (pour la politique d'expansion, appelee souvent)."""
    if job_id is None:
        return []
    return [
        {"rank": r["multipv_index"], "root_move_uci": r["root_move_uci"], "exact_depth": r["exact_depth"],
         "score": {"kind": r["score_type"], "value": r["score_value"], "perspective": "white", "bound": r["score_bound"]}}
        for r in analysis_repo.latest_lines(conn, job_id)
    ]


def full_lines(conn: sqlite3.Connection, node: sqlite3.Row, position: dict, scheduler=None) -> tuple[dict | None, list[dict]]:
    """(vue du travail, lignes avec notation) pour un noeud."""
    job_id = lines_job_id(conn, node)
    if job_id is None:
        return None, []
    job = analysis_repo.get(conn, job_id)
    board = analysis_repo.job_board(position, path_of(node))
    live = scheduler.live.get(job_id) if scheduler is not None else None
    view = analysis_repo.full_view(conn, job, board, live)
    return view, view["lines"]


def spent_seconds(conn: sqlite3.Connection, tree_id: str, envelope: str) -> float:
    """Temps consomme ou reserve dans une enveloppe : `user` (branches du joueur)
    ou `auto` (expansions automatiques). Ni la racine ni les reanalyses demandees
    n'y comptent. Travaux termines + budgets des travaux en file."""
    reasons = USER_REASONS if envelope == "user" else AUTO_REASONS
    rows = conn.execute(
        "SELECT j.state, j.elapsed_s, j.settings_json FROM reference_nodes n"
        " JOIN analysis_jobs j ON j.id = (CASE WHEN n.reanalysed = 1 THEN n.previous_job_id ELSE n.job_id END)"
        f" WHERE n.tree_id = ? AND n.selection_reason IN ({",".join("?" * len(reasons))})",
        (tree_id, *reasons)).fetchall()
    total = 0.0
    for r in rows:
        if r["state"] in ("queued", "running"):
            total += json.loads(r["settings_json"])["budget_s"]
        else:
            total += r["elapsed_s"] or 0.0
    return total


# ------------------------------------------------------------------- vues

def progress_category(state: str) -> str:
    return "running" if state == "building" else "stopped" if state == "failed" else "done"


def hidden_view(tree: sqlite3.Row) -> dict:
    category = progress_category(tree["state"])
    return {"id": tree["id"], "visibility": "hidden", "progress_category": category, "is_ready": category == "done"}


def full_view(conn: sqlite3.Connection, tree: sqlite3.Row, scheduler=None, max_lines: int = 5) -> dict:
    """Vue complete : a n'appeler que si l'arbre est visible (le service le garantit)."""
    position = repo.get_position(conn, tree["position_id"])
    out_nodes = []
    for node in nodes(conn, tree["id"]):
        job, lines = full_lines(conn, node, position, scheduler)
        out_nodes.append({
            "id": node["id"],
            "parent_id": node["parent_id"],
            "path_uci": list(path_of(node)),
            "ply": node["ply"],
            "move_uci": node["move_uci"],
            "move_san": node["move_san"],
            "fen": node["fen"],
            "status": node["status"],
            "selection_reason": node["selection_reason"],
            "reanalysed": bool(node["reanalysed"]),
            "job_id": node["job_id"],
            "job_state": job["state"] if job else None,
            "target_depth": job["settings"]["target_depth"] if job else None,
            "legal_moves": job["legal_moves"] if job else None,
            "lines": lines[:max_lines] if node["ply"] else lines,
        })
    settings = json.loads(tree["settings_json"])
    return {
        "id": tree["id"],
        "visibility": "full",
        "position_id": tree["position_id"],
        "session_id": tree["session_id"],
        "state": tree["state"],
        "revision": tree["revision"],
        "settings": settings,
        "spent_s": {"auto": round(spent_seconds(conn, tree["id"], "auto"), 1),
                    "user": round(spent_seconds(conn, tree["id"], "user"), 1)},
        "pruned_count": tree["pruned_count"],
        # Jamais exhaustif : arbre selectif, borne par la politique ci-dessus.
        "coverage": "selective",
        "nodes": out_nodes,
    }


def board_at(position: dict, path: tuple[str, ...]) -> chess.Board:
    return analysis_repo.job_board(position, path)

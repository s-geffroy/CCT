"""Travaux d'analyse : file persistante, cache, instantanes de lignes, visibilite.

Regle de visibilite (doc 08, anti-spoiler) : les resultats d'un travail ne sont
lisibles que si AUCUNE seance non revelee (active ou soumise) ne porte sur le
meme echiquier — quel que soit le demandeur du travail. Une seule regle, sans
exception : elle couvre aussi l'analyse d'etude lancee avant la seance et le
travail reutilise par le cache.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

import chess

from ..domain.errors import DomainError, NotFound
from ..engine.analysis import LineDTO, RootAnalysis
from .db import transaction, utc_now

ANALYSIS_POLICY_VERSION = 1
FINAL_STATES = ("complete_depth", "budget_exhausted", "incomplete", "cancelled", "failed", "interrupted", "terminal")
UNREVEALED = ("active", "submitted")

STATUS_TO_STATE = {
    "depth_met": "complete_depth",
    "budget_exhausted": "budget_exhausted",
    "incomplete": "incomplete",
    "cancelled": "cancelled",
    "terminal": "terminal",
}


class TooManyJobs(DomainError):
    status_code = 429


def board_key(fen: str) -> str:
    """Echiquier au sens de l'exercice : pieces, trait, roques, prise en passant."""
    return " ".join(fen.split()[:4])


def cache_key(context_key: str, engine: dict, settings: dict) -> str:
    payload = {
        "context": context_key,
        "engine": [engine.get("name"), engine.get("build", {}).get("net_sha256"), engine.get("threads"), engine.get("hash_mb")],
        "target_depth": settings["target_depth"],
        "multipv_max": settings["multipv_max"],
        "policy": ANALYSIS_POLICY_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------ visibilite

def unrevealed_session_on_board(conn: sqlite3.Connection, fen: str) -> str | None:
    key = board_key(fen)
    rows = conn.execute(
        "SELECT s.id, p.fen FROM sessions s JOIN positions p ON p.id = s.position_id WHERE s.state IN (?, ?)",
        UNREVEALED,
    ).fetchall()
    return next((r["id"] for r in rows if board_key(r["fen"]) == key), None)


def is_visible(conn: sqlite3.Connection, job: sqlite3.Row) -> bool:
    fen = conn.execute("SELECT fen FROM positions WHERE id = ?", (job["position_id"],)).fetchone()["fen"]
    return unrevealed_session_on_board(conn, fen) is None


# --------------------------------------------------------------- creation

def get(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise NotFound("JOB_NOT_FOUND", "Travail d'analyse inconnu.")
    return row


def create_or_reuse(conn: sqlite3.Connection, *, position_id: str, session_id: str | None, purpose: str,
                    priority: int, settings: dict, key: str, max_queued: int) -> tuple[sqlite3.Row, bool]:
    """Deduplique les demandes equivalentes ; reutilise un resultat a profondeur atteinte."""
    with transaction(conn):
        reusable = conn.execute(
            "SELECT * FROM analysis_jobs WHERE cache_key = ? AND state IN ('queued', 'running', 'complete_depth', 'terminal')"
            " ORDER BY created_at DESC LIMIT 1",
            (key,),
        ).fetchone()
        if reusable is not None:
            return reusable, True
        queued = conn.execute("SELECT COUNT(*) FROM analysis_jobs WHERE state = 'queued'").fetchone()[0]
        if queued >= max_queued:
            raise TooManyJobs("TOO_MANY_JOBS", "Trop de travaux d'analyse en attente.", {"queued": queued})
        job_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO analysis_jobs (id, position_id, session_id, purpose, scope, priority, state, settings_json,"
            " cache_key, created_at) VALUES (?, ?, ?, ?, 'root', ?, 'queued', ?, ?, ?)",
            (job_id, position_id, session_id, purpose, priority, json.dumps(settings), key, utc_now()),
        )
        return get(conn, job_id), False


def mark_interrupted_on_startup(conn: sqlite3.Connection) -> int:
    """Apres un arret brutal, un travail 'running' ne reprend pas magiquement."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE analysis_jobs SET state = 'interrupted', ended_at = ?, error = 'arret du serveur pendant le calcul'"
            " WHERE state = 'running'", (utc_now(),))
        return cur.rowcount


def claim_next(conn: sqlite3.Connection) -> sqlite3.Row | None:
    with transaction(conn):
        row = conn.execute(
            "SELECT * FROM analysis_jobs WHERE state = 'queued' ORDER BY priority DESC, created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE analysis_jobs SET state = 'running', started_at = ? WHERE id = ?", (utc_now(), row["id"]))
        return get(conn, row["id"])


def request_cancel(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row:
    """Idempotent : un travail termine reste tel quel ; en file, il est annule tout de suite."""
    with transaction(conn):
        row = get(conn, job_id)
        if row["state"] == "queued":
            conn.execute("UPDATE analysis_jobs SET state = 'cancelled', cancel_requested = 1, ended_at = ? WHERE id = ?",
                         (utc_now(), job_id))
        elif row["state"] == "running":
            conn.execute("UPDATE analysis_jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))
        return get(conn, job_id)


# -------------------------------------------------------------- resultats

def _line_rows(job_id: str, snapshot: int, stage: int | None, lines: list[LineDTO], final: bool) -> list[tuple]:
    return [
        (job_id, snapshot, stage, line.multipv, line.root_move_uci, json.dumps(line.pv_uci), line.depth,
         line.exact_depth, line.seldepth, line.nodes, line.score.kind, line.score.value, line.score.bound, int(final))
        for line in lines
    ]


_INSERT_LINE = (
    "INSERT INTO analysis_lines (job_id, snapshot, stage, multipv_index, root_move_uci, pv_uci_json, depth, exact_depth,"
    " seldepth, nodes, score_type, score_value, score_bound, is_final) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def save_stage(conn: sqlite3.Connection, job_id: str, stage: int, partial: RootAnalysis) -> None:
    with transaction(conn):
        revision = conn.execute("SELECT revision FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()[0] + 1
        conn.executemany(_INSERT_LINE, _line_rows(job_id, revision, stage, partial.lines, False))
        conn.execute(
            "UPDATE analysis_jobs SET revision = ?, stages_json = ?, legal_moves = ?, multipv = ?, elapsed_s = ?,"
            " nodes = ?, nps = ? WHERE id = ?",
            (revision, json.dumps(partial.stages_reached_s), partial.legal_moves_count, partial.multipv,
             partial.elapsed_s, partial.nodes, partial.nps, job_id),
        )


def finish(conn: sqlite3.Connection, job_id: str, result: RootAnalysis | None, *, error: str | None = None) -> None:
    with transaction(conn):
        revision = conn.execute("SELECT revision FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()[0] + 1
        if result is None:
            conn.execute("UPDATE analysis_jobs SET state = 'failed', error = ?, ended_at = ?, revision = ? WHERE id = ?",
                         (error, utc_now(), revision, job_id))
            return
        conn.executemany(_INSERT_LINE, _line_rows(job_id, revision, None, result.lines, True))
        conn.execute(
            "UPDATE analysis_jobs SET state = ?, revision = ?, stages_json = ?, legal_moves = ?, multipv = ?,"
            " elapsed_s = ?, nodes = ?, nps = ?, ended_at = ? WHERE id = ?",
            (STATUS_TO_STATE[result.status], revision, json.dumps(result.stages_reached_s), result.legal_moves_count,
             result.multipv, result.elapsed_s, result.nodes, result.nps, utc_now(), job_id),
        )


def latest_lines(conn: sqlite3.Connection, job_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM analysis_lines WHERE job_id = ? AND snapshot = (SELECT MAX(snapshot) FROM analysis_lines WHERE job_id = ?)"
        " ORDER BY multipv_index", (job_id, job_id),
    ).fetchall()


def jobs_for_position(conn: sqlite3.Connection, position_id: str, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM analysis_jobs WHERE position_id = ? ORDER BY created_at DESC LIMIT ?", (position_id, limit)
    ).fetchall()


# ------------------------------------------------------------------ vues

def _san_line(board: chess.Board, pv: list[str]) -> list[str]:
    sans = []
    b = board.copy(stack=False)
    for uci in pv:
        move = chess.Move.from_uci(uci)
        if move not in b.legal_moves:
            break  # par prudence : jamais de SAN invente
        sans.append(b.san(move))
        b.push(move)
    return sans


def line_view(board: chess.Board, *, rank: int, root_move: str, pv: list[str], depth: int, exact_depth: int,
              seldepth: int | None, score: dict, target_depth: int, final: bool, job_state: str) -> dict:
    pv_san = _san_line(board, pv)
    if exact_depth >= target_depth:
        status = "depth_met"
    elif not final:
        status = "provisional"
    else:
        status = {"budget_exhausted": "budget_exhausted", "cancelled": "cancelled"}.get(job_state, "incomplete")
    return {
        "rank": rank,
        "root_move_uci": root_move,
        "root_move_san": pv_san[0] if pv_san else None,
        "pv_uci": pv,
        "pv_san": pv_san,
        "depth": depth,
        "exact_depth": exact_depth,
        "seldepth": seldepth,
        "score": score,
        "status": status,
    }


def full_view(conn: sqlite3.Connection, job: sqlite3.Row, board: chess.Board, live: RootAnalysis | None = None) -> dict:
    """Vue complete : a n'appeler que si `is_visible` (le service le garantit)."""
    settings = json.loads(job["settings_json"])
    target = settings["target_depth"]
    if live is not None and job["state"] == "running":
        lines = [
            line_view(board, rank=l.multipv, root_move=l.root_move_uci, pv=l.pv_uci, depth=l.depth,
                      exact_depth=l.exact_depth, seldepth=l.seldepth, target_depth=target, final=False,
                      job_state="running",
                      score={"kind": l.score.kind, "value": l.score.value, "perspective": "white", "bound": l.score.bound})
            for l in live.lines
        ]
        stages, elapsed, nps, legal, multipv = live.stages_reached_s, live.elapsed_s, live.nps, live.legal_moves_count, live.multipv
    else:
        final = job["state"] in FINAL_STATES
        lines = [
            line_view(board, rank=r["multipv_index"], root_move=r["root_move_uci"], pv=json.loads(r["pv_uci_json"]),
                      depth=r["depth"], exact_depth=r["exact_depth"], seldepth=r["seldepth"], target_depth=target,
                      final=final and bool(r["is_final"]), job_state=job["state"],
                      score={"kind": r["score_type"], "value": r["score_value"], "perspective": "white",
                             "bound": r["score_bound"]})
            for r in latest_lines(conn, job["id"])
        ]
        stages = {int(k): v for k, v in json.loads(job["stages_json"]).items()}
        elapsed, nps, legal, multipv = job["elapsed_s"], job["nps"], job["legal_moves"], job["multipv"]
    min_exact = min((l["exact_depth"] for l in lines), default=0)
    return {
        "id": job["id"],
        "position_id": job["position_id"],
        "visibility": "full",
        "purpose": job["purpose"],
        "state": job["state"],
        "revision": job["revision"],
        "settings": settings,
        "stages_reached_s": stages,
        "target_depth_met": bool(lines) and min_exact >= target,
        "legal_moves": legal,
        "multipv": multipv,
        # Jamais « exhaustif » : au mieux tous les premiers coups, pas toutes les suites.
        "root_coverage": None if not legal else ("all_root_moves" if multipv == legal else "top_moves_only"),
        "elapsed_s": elapsed,
        "nps": nps,
        "error": job["error"],
        "cancel_requested": bool(job["cancel_requested"]),
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "ended_at": job["ended_at"],
        "lines": lines,
    }


def progress_category(state: str) -> str:
    if state == "queued":
        return "queued"
    if state == "running":
        return "running"
    if state in ("failed", "interrupted", "cancelled"):
        return "stopped"
    return "done"


def hidden_view(job: sqlite3.Row) -> dict:
    """Ce qu'un client voit pendant une seance non revelee : l'etat, rien d'autre."""
    category = progress_category(job["state"])
    return {"id": job["id"], "visibility": "hidden", "progress_category": category, "is_ready": category == "done"}

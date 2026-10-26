"""Seances d'entrainement B (mental) et C (arbre) : /api/v1/sessions.

Anti-spoiler : toute reponse de seance passe par `session_view()`, seul
endroit qui decide de ce qui sort. Avant la revelation, la section
`reference` n'existe pas (pas meme vide sous une cle cachee).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import Field

from ..domain import training
from ..domain.errors import DomainError
from ..log import get_logger
from ..persistence import analysis_repo, repo, sessions_repo
from ..persistence.db import utc_now
from .analysis import PRIORITY_SESSION_REFERENCE, default_settings, enqueue, job_view
from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")
log = get_logger("api.sessions")

Revision = Annotated[int, Field(ge=1)]
Assessment = Literal["white_better", "black_better", "equal", "initiative", "attack", "unclear"]
REVEALED_STATES = ("revealed", "reviewed")


class SessionIn(StrictModel):
    position_id: UUID
    mode: Literal["mental", "tree"]
    allow_text_notes: bool = True
    # Preparer la reference en arriere-plan pendant que le joueur calcule ;
    # rien n'en sort avant la revelation.
    start_analysis_in_background: bool = True


class NodeIn(StrictModel):
    parent_node_id: UUID | None = None  # None = depuis la position de la seance
    move: str = Field(max_length=16)
    expected_revision: Revision
    comment: str = Field(default="", max_length=training.MAX_COMMENT)


class NodePatch(StrictModel):
    expected_revision: Revision
    comment: str | None = Field(default=None, max_length=training.MAX_COMMENT)
    human_assessment: Assessment | None = None
    clear_assessment: bool = False
    promote: bool = False


class RevisionIn(StrictModel):
    expected_revision: Revision


class NotesIn(StrictModel):
    expected_revision: Revision
    notes: str | None = Field(default=None, max_length=20_000)
    lines_text: str | None = Field(default=None, max_length=training.MAX_LINES_TEXT)


class SelfAssessment(StrictModel):
    candidates: str = Field(default="", max_length=500)
    main_threat: str = Field(default="", max_length=500)
    evaluation: Assessment | None = None


class SubmitIn(StrictModel):
    expected_revision: Revision
    self_assessment: SelfAssessment | None = None


# ------------------------------------------------------------------- vue

def session_view(conn: sqlite3.Connection, row: sqlite3.Row, scheduler=None) -> dict:
    position = repo.get_position(conn, row["position_id"])
    can_undo, can_redo = sessions_repo.undo_redo_flags(conn, row)
    view = {
        "id": row["id"],
        "mode": row["mode"],
        "state": row["state"],
        "revision": row["revision"],
        "started_at": row["started_at"],
        "submitted_at": row["submitted_at"],
        "revealed_at": row["revealed_at"],
        "abandoned_at": row["abandoned_at"],
        "duration_ms": row["duration_ms"],
        "allow_text_notes": bool(row["allow_text_notes"]),
        "notes": row["notes"],
        "lines_text": row["lines_text"],
        "self_assessment": json.loads(row["self_assessment_json"]) if row["self_assessment_json"] else None,
        "position": position,
        "tree": {"nodes": sessions_repo.load_tree(conn, row["id"])},
        "can_undo": row["state"] == "active" and can_undo,
        "can_redo": row["state"] == "active" and can_redo,
        "attempt": sessions_repo.get_attempt(conn, row["id"]),
    }
    job = analysis_repo.get(conn, row["reference_job_id"]) if row["reference_job_id"] else None
    if row["state"] in REVEALED_STATES:
        # Seul endroit ou la reference est jointe. job_view applique encore la
        # regle d'echiquier : une autre seance non revelee sur la meme position
        # la masque.
        if job is None:
            view["reference"] = {"status": "not_available",
                                 "message": "Aucune analyse moteur : moteur indisponible lors de la seance."}
        else:
            view["reference"] = {"status": "available", "job": job_view(conn, scheduler, job)}
    elif job is not None:
        # Avant revelation : l'avancement seulement.
        hidden = analysis_repo.hidden_view(job)
        view["preparation"] = {"job_id": job["id"], "progress_category": hidden["progress_category"],
                               "is_ready": hidden["is_ready"]}
    return view


def _view(request: Request, session_id: str) -> dict:
    with request.app.state.db.session() as conn:
        return session_view(conn, sessions_repo.get(conn, session_id), request.app.state.scheduler)


def _mutate(request: Request, session_id: UUID, expected: int, action, **kwargs) -> dict:
    with request.app.state.db.session() as conn:
        sessions_repo.mutate(conn, str(session_id), expected, lambda row: action(conn, row), **kwargs)
        return session_view(conn, sessions_repo.get(conn, str(session_id)), request.app.state.scheduler)


def _start_reference(request: Request, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    """Lance (ou reutilise via le cache) l'analyse de reference de la seance."""
    if request.app.state.engine.info is None:
        return
    try:
        job, _ = enqueue(request, conn, position_id=row["position_id"], session_id=row["id"],
                         purpose="initial_reference", priority=PRIORITY_SESSION_REFERENCE,
                         settings=default_settings())
    except DomainError as exc:
        # Pas de reference (position terminale, file pleine...) : la seance reste possible.
        log.warning("seance %s : reference non lancee (%s)", row["id"][:8], exc.code)
        return
    conn.execute("UPDATE sessions SET reference_job_id = ? WHERE id = ?", (job["id"], row["id"]))


# ----------------------------------------------------------------- routes

@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, request: Request) -> dict:
    with request.app.state.db.session() as conn:
        session_id = sessions_repo.create(conn, str(body.position_id), body.mode, body.allow_text_notes)
        if body.start_analysis_in_background:
            _start_reference(request, conn, sessions_repo.get(conn, session_id))
        return session_view(conn, sessions_repo.get(conn, session_id), request.app.state.scheduler)


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID, request: Request) -> dict:
    return _view(request, str(session_id))


def _require_tree_mode(row: sqlite3.Row) -> None:
    if row["mode"] != "tree":
        raise sessions_repo.StateError(
            "MENTAL_MODE", "Seance de calcul mental : pas de coups joues sur l'echiquier.")


@router.post("/sessions/{session_id}/nodes", status_code=201)
def add_node(session_id: UUID, body: NodeIn, request: Request) -> dict:
    created: dict = {}

    def action(conn, row):
        _require_tree_mode(row)
        position = repo.get_position(conn, row["position_id"])
        state = sessions_repo.load_tree(conn, row["id"])
        parent = str(body.parent_node_id) if body.parent_node_id else None
        new_state, node = training.add_move(state, position["fen"], parent, body.move, body.comment, utc_now())
        sessions_repo.write_tree(conn, row, new_state)
        created.update(node)

    view = _mutate(request, session_id, body.expected_revision, action)
    return {"node": created, "session": view}


@router.patch("/sessions/{session_id}/nodes/{node_id}")
def patch_node(session_id: UUID, node_id: UUID, body: NodePatch, request: Request) -> dict:
    def action(conn, row):
        _require_tree_mode(row)
        state = sessions_repo.load_tree(conn, row["id"])
        assessment = None if body.clear_assessment else (body.human_assessment or training.UNSET)
        new_state = training.patch_node(state, str(node_id), comment=body.comment,
                                        assessment=assessment, promote=body.promote)
        sessions_repo.write_tree(conn, row, new_state)

    return _mutate(request, session_id, body.expected_revision, action)


@router.delete("/sessions/{session_id}/nodes/{node_id}")
def delete_node(session_id: UUID, node_id: UUID, request: Request,
                expected_revision: Annotated[int, Query(ge=1)]) -> dict:
    def action(conn, row):
        _require_tree_mode(row)
        state = sessions_repo.load_tree(conn, row["id"])
        sessions_repo.write_tree(conn, row, training.delete_subtree(state, str(node_id)))

    return _mutate(request, session_id, expected_revision, action)


@router.post("/sessions/{session_id}/undo")
def undo(session_id: UUID, body: RevisionIn, request: Request) -> dict:
    return _mutate(request, session_id, body.expected_revision,
                   lambda conn, row: sessions_repo.move_cursor(conn, row, -1))


@router.post("/sessions/{session_id}/redo")
def redo(session_id: UUID, body: RevisionIn, request: Request) -> dict:
    return _mutate(request, session_id, body.expected_revision,
                   lambda conn, row: sessions_repo.move_cursor(conn, row, +1))


@router.put("/sessions/{session_id}/notes")
def put_notes(session_id: UUID, body: NotesIn, request: Request) -> dict:
    def action(conn, row):
        if not row["allow_text_notes"] and (body.notes or body.lines_text):
            raise sessions_repo.StateError("NOTES_DISABLED", "Notes desactivees pour cette seance.")
        if body.lines_text is not None and row["mode"] != "mental":
            raise sessions_repo.StateError("LINES_MENTAL_ONLY", "Les variantes ecrites sont reservees au calcul mental.")
        # Aucune analyse des lignes ici : la legalite n'est jugee qu'au debriefing.
        sessions_repo.set_notes(conn, row, body.notes, body.lines_text)

    return _mutate(request, session_id, body.expected_revision, action)


@router.post("/sessions/{session_id}/submit")
def submit(session_id: UUID, body: SubmitIn, request: Request) -> dict:
    def action(conn, row):
        position = repo.get_position(conn, row["position_id"])
        assessment = body.self_assessment.model_dump() if body.self_assessment else None
        snapshot: dict = {"mode": row["mode"], "root_fen": position["fen"], "notes": row["notes"],
                          "self_assessment": assessment}
        if row["mode"] == "tree":
            snapshot["tree"] = sessions_repo.load_tree(conn, row["id"])
        else:
            lines = training.parse_lines(position["fen"], row["lines_text"])
            # « written_lines » et non « lines » : ce dernier nom est reserve aux
            # lignes moteur, interdites avant revelation (scanner anti-spoiler).
            snapshot["written_lines"] = [line.__dict__ for line in lines]
            snapshot["tree"] = training.lines_to_tree(position["fen"], lines)
        # Seance mentale sans restitution : seule l'autoevaluation existera.
        snapshot["no_trace"] = not snapshot["tree"] and not row["notes"].strip() and not (
            row["mode"] == "mental" and row["lines_text"].strip())
        sessions_repo.submit(conn, row, assessment, snapshot)

    return _mutate(request, session_id, body.expected_revision, action)


@router.post("/sessions/{session_id}/reveal")
def reveal(session_id: UUID, body: RevisionIn, request: Request) -> dict:
    view = _mutate(request, session_id, body.expected_revision,
                   lambda conn, row: sessions_repo.reveal(conn, row), require_state="submitted")
    with request.app.state.db.session() as conn:
        row = sessions_repo.get(conn, str(session_id))
        if row["reference_job_id"] is None:
            # Moteur indisponible au debut de la seance : on lance la reference maintenant.
            _start_reference(request, conn, row)
            view = session_view(conn, sessions_repo.get(conn, str(session_id)), request.app.state.scheduler)
        else:
            # Les flux SSE ouverts passent de « etat seul » a « lignes completes ».
            request.app.state.scheduler.notify_threadsafe(row["reference_job_id"])
    return view


@router.post("/sessions/{session_id}/abandon")
def abandon(session_id: UUID, body: RevisionIn, request: Request) -> dict:
    return _mutate(request, session_id, body.expected_revision,
                   lambda conn, row: sessions_repo.abandon(conn, row))


@router.get("/sessions/{session_id}/export")
def export(session_id: UUID, request: Request, format: Literal["json", "pgn"] = "json"):
    view = _view(request, str(session_id))
    if format == "json":
        return {"format": "cct-session", "format_version": 1, "session": view}
    # Tentative soumise si elle existe, sinon l'arbre en cours.
    tree = view["attempt"]["tree"] if view["attempt"] else view["tree"]["nodes"]
    headers = {"Event": "Chess Calculation Trainer", "Site": "local",
               "Date": view["started_at"][:10].replace("-", "."),
               "Annotator": "seance " + ("calcul mental" if view["mode"] == "mental" else "arbre personnel")}
    pgn_text = training.export_pgn(view["position"]["fen"], tree or {}, headers, view["notes"])
    return PlainTextResponse(pgn_text, media_type="application/x-chess-pgn",
                             headers={"Content-Disposition": f'attachment; filename="seance-{session_id}.pgn"'})


@router.get("/history")
def history(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0) -> dict:
    with request.app.state.db.session() as conn:
        return {"items": sessions_repo.history(conn, limit, offset), "limit": limit, "offset": offset}

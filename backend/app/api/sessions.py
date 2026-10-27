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

from ..domain import review as review_domain
from ..domain import training
from ..domain.errors import DomainError
from ..log import get_logger
from ..domain.scores import terminal_score
from ..persistence import analysis_repo, reference_repo, repo, review_repo, sessions_repo
from ..persistence.db import utc_now
from ..services import PRIORITY_SESSION_REFERENCE, default_settings
from .analysis import enqueue, job_view
from .reference import tree_view, tree_visible
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
    # Lancer tout de suite (equivalent du bouton Go) : clients d'API et tests.
    start: bool = False


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
        "go_at": row["go_at"],
        "started": row["go_at"] is not None,
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
    if row["state"] != "active":
        # Comparer ses durees de reflexion sur le meme probleme, une fois la seance finie.
        view["previous_attempts"] = sessions_repo.previous_attempts(conn, row, analysis_repo.board_key)
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
        if row["reference_tree_id"]:
            view["reference_tree"] = tree_view(conn, scheduler, reference_repo.get_tree(conn, row["reference_tree_id"]))
    elif job is not None:
        # Avant revelation : l'avancement seulement.
        hidden = analysis_repo.hidden_view(job)
        view["preparation"] = {"job_id": job["id"], "progress_category": hidden["progress_category"],
                               "is_ready": hidden["is_ready"]}
        if row["reference_tree_id"]:
            tree = reference_repo.hidden_view(reference_repo.get_tree(conn, row["reference_tree_id"]))
            view["preparation"]["tree_is_ready"] = tree["is_ready"]
            view["preparation"]["tree_progress_category"] = tree["progress_category"]
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
                         settings=default_settings(request.app.state.prefs))
    except DomainError as exc:
        # Pas de reference (position terminale, file pleine...) : la seance reste possible.
        log.warning("seance %s : reference non lancee (%s)", row["id"][:8], exc.code)
        return
    conn.execute("UPDATE sessions SET reference_job_id = ? WHERE id = ?", (job["id"], row["id"]))
    # Arbre de reference : defenses critiques pendant le calcul du joueur, puis
    # ses propres branches apres la soumission. Rien n'en sort avant la revelation.
    request.app.state.reference.create(conn, position_id=row["position_id"], session_id=row["id"], root_job=job)


# ----------------------------------------------------------------- routes

@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, request: Request) -> dict:
    with request.app.state.db.session() as conn:
        session_id = sessions_repo.create(conn, str(body.position_id), body.mode, body.allow_text_notes,
                                          analysis_on_go=body.start_analysis_in_background)
    if body.start:
        return _go(request, UUID(session_id), 1)
    return _view(request, session_id)


def _go(request: Request, session_id: UUID, expected: int) -> dict:
    _mutate(request, session_id, expected, lambda conn, row: sessions_repo.start(conn, row))
    with request.app.state.db.session() as conn:
        row = sessions_repo.get(conn, str(session_id))
        # Le moteur calcule pendant que le joueur reflechit, a partir du Go.
        if row["analysis_on_go"] and row["reference_job_id"] is None:
            _start_reference(request, conn, row)
        return session_view(conn, sessions_repo.get(conn, str(session_id)), request.app.state.scheduler)


@router.post("/sessions/{session_id}/start")
def start(session_id: UUID, body: RevisionIn, request: Request) -> dict:
    """Bouton Go : chronometre (non affiche) et calculs du moteur."""
    return _go(request, session_id, body.expected_revision)


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

    view = _mutate(request, session_id, body.expected_revision, action)
    if view.get("preparation") is not None:
        # Les branches du joueur sont connues : elles passent en tete de l'arbre.
        with request.app.state.db.session() as conn:
            tree_id = sessions_repo.get(conn, str(session_id))["reference_tree_id"]
        if tree_id:
            request.app.state.reference.advance(tree_id)
    return view


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
        payload = {"format": "cct-session", "format_version": 1, "session": view}
        if view["state"] in REVEALED_STATES:
            with request.app.state.db.session() as conn:
                stored = review_repo.latest(conn, str(session_id))
                # Meme regle que partout : une seance non revelee sur cet echiquier masque tout.
                hidden = analysis_repo.unrevealed_session_on_board(conn, view["position"]["fen"]) is not None
            payload["review"] = ({"status": "hidden"} if hidden
                                 else json.loads(stored["report_json"]) if stored is not None else None)
        return payload
    # Tentative soumise si elle existe, sinon l'arbre en cours.
    tree = view["attempt"]["tree"] if view["attempt"] else view["tree"]["nodes"]
    headers = {"Event": "Chess Calculation Trainer", "Site": "local",
               "Date": view["started_at"][:10].replace("-", "."),
               "Annotator": "seance " + ("calcul mental" if view["mode"] == "mental" else "arbre personnel")}
    pgn_text = training.export_pgn(view["position"]["fen"], tree or {}, headers, view["notes"])
    return PlainTextResponse(pgn_text, media_type="application/x-chess-pgn",
                             headers={"Content-Disposition": f'attachment; filename="seance-{session_id}.pgn"'})


def _reference_for_review(conn: sqlite3.Connection, tree: sqlite3.Row, position: dict) -> review_domain.Reference:
    nodes = {}
    for node in reference_repo.nodes(conn, tree["id"]):
        path = reference_repo.path_of(node)
        _job, lines = reference_repo.full_lines(conn, node, position)  # points stables enregistres seulement
        terminal = None
        if node["status"] == "terminal":
            outcome = reference_repo.board_at(position, path).outcome(claim_draw=False)
            terminal = terminal_score(outcome.result()) if outcome else None
        nodes[path] = review_domain.RefNode(
            node_id=node["id"], path=path, status=node["status"], reason=node["selection_reason"], lines=lines,
            final=node["status"] not in reference_repo.PENDING, terminal_score=terminal)
    return review_domain.Reference(nodes, position["fen"], building=tree["state"] == "building")


@router.get("/sessions/{session_id}/review")
def review(session_id: UUID, request: Request) -> dict:
    """Debriefing : diagnostics prudents, preuves et incertitudes (doc 07).

    Recalcule tant que l'arbre de reference evolue ; enregistre des que le
    rapport est stable (la seance passe alors `reviewed`)."""
    with request.app.state.db.session() as conn:
        row = sessions_repo.get(conn, str(session_id))
        if row["state"] not in REVEALED_STATES:
            raise sessions_repo.StateError("REVIEW_NOT_AVAILABLE",
                                           "Le debriefing n'est disponible qu'apres la revelation.",
                                           {"state": row["state"]})
        tree = reference_repo.get_tree(conn, row["reference_tree_id"]) if row["reference_tree_id"] else None
        if tree is not None and not tree_visible(conn, tree):
            return {"session_id": row["id"], "status": "hidden",
                    "message": "Reference masquee : une autre seance non revelee porte sur cette position."}
        revision = tree["revision"] if tree is not None else None
        stored = review_repo.latest(conn, row["id"])
        if stored is not None and stored["tree_revision"] == revision:
            return {"session_id": row["id"], "status": "available", "stored": True, "review_id": stored["id"],
                    "tree_state": tree["state"] if tree is not None else None, **json.loads(stored["report_json"])}
        position = repo.get_position(conn, row["position_id"])
        reference = _reference_for_review(conn, tree, position) if tree is not None else None
        report = review_domain.build_report(root_fen=position["fen"], attempt=sessions_repo.get_attempt(conn, row["id"]),
                                            reference=reference, tree_state=tree["state"] if tree else None)
        review_id = None
        if report["quality"] != "provisional":
            review_id = review_repo.save(conn, row, revision, report)
        return {"session_id": row["id"], "status": "available", "stored": review_id is not None,
                "review_id": review_id, "tree_state": tree["state"] if tree is not None else None, **report}


@router.get("/history")
def history(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0) -> dict:
    with request.app.state.db.session() as conn:
        return {"items": sessions_repo.history(conn, limit, offset), "limit": limit, "offset": offset}

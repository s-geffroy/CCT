"""Travaux d'analyse : /api/v1/analysis-jobs (REST + SSE).

Toute sortie passe par `job_view()` : vue complete si le travail est visible
(aucune seance non revelee sur le meme echiquier), etat seul sinon.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Annotated
from uuid import UUID

import chess
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field

from ..domain.errors import DomainError, NotFound
from ..log import get_logger
from ..persistence import analysis_repo, repo
from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")
log = get_logger("api.analysis")

HEARTBEAT_S = 15.0
PRIORITY_STUDY = 100           # demande explicite de l'utilisateur
PRIORITY_SESSION_REFERENCE = 50  # preparation de fond d'une seance


class EngineUnavailable(DomainError):
    status_code = 503


class SessionInProgress(DomainError):
    status_code = 409


class JobIn(StrictModel):
    position_id: UUID
    target_depth: int = Field(default=21, ge=8, le=32)
    multipv_max: int = Field(default=20, ge=1, le=20)
    budget_s: int = Field(default=300, ge=5, le=1800)


def default_settings() -> dict:
    return {"target_depth": 21, "multipv_max": 20, "budget_s": 300}


def enqueue(request: Request, conn: sqlite3.Connection, *, position_id: str, session_id: str | None,
            purpose: str, priority: int, settings: dict) -> tuple[sqlite3.Row, bool]:
    engine = request.app.state.engine
    if engine.info is None:
        raise EngineUnavailable("ENGINE_UNAVAILABLE", "Moteur indisponible : analyse impossible pour l'instant.")
    position = repo.get_position(conn, position_id)
    if position is None:
        raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
    if position["outcome"]:
        raise DomainError("TERMINAL_POSITION", "Partie terminee dans cette position : aucune variante a calculer.")
    engine_desc = {"name": engine.info.name, "build": engine.info.build,
                   "threads": engine.info.threads, "hash_mb": engine.info.hash_mb}
    context = conn.execute("SELECT context_key FROM positions WHERE id = ?", (position_id,)).fetchone()[0]
    full_settings = {**settings, "engine": engine_desc}
    key = analysis_repo.cache_key(context, engine_desc, settings)
    job, reused = analysis_repo.create_or_reuse(
        conn, position_id=position_id, session_id=session_id, purpose=purpose, priority=priority,
        settings=full_settings, key=key, max_queued=request.app.state.settings.max_queued_jobs)
    if not reused:
        request.app.state.scheduler.wake()
    return job, reused


def job_view(conn: sqlite3.Connection, scheduler, job: sqlite3.Row) -> dict:
    if not analysis_repo.is_visible(conn, job):
        return analysis_repo.hidden_view(job)
    fen = repo.get_position(conn, job["position_id"])["fen"]
    live = scheduler.live.get(job["id"]) if scheduler is not None else None
    return analysis_repo.full_view(conn, job, chess.Board(fen), live)


@router.post("/analysis-jobs", status_code=201)
def create_job(body: JobIn, request: Request, response: Response) -> dict:
    with request.app.state.db.session() as conn:
        position = repo.get_position(conn, str(body.position_id))
        if position is None:
            raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
        if analysis_repo.unrevealed_session_on_board(conn, position["fen"]):
            raise SessionInProgress(
                "SESSION_IN_PROGRESS",
                "Une seance d'entrainement non revelee porte sur cette position : la terminer ou l'abandonner avant de l'analyser.")
        job, reused = enqueue(request, conn, position_id=position["id"], session_id=None, purpose="study",
                              priority=PRIORITY_STUDY,
                              settings={"target_depth": body.target_depth, "multipv_max": body.multipv_max,
                                        "budget_s": body.budget_s})
        if reused:
            response.status_code = 200
        return {**job_view(conn, request.app.state.scheduler, job), "reused": reused}


@router.get("/analysis-jobs")
def list_jobs(request: Request, position_id: UUID, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    with request.app.state.db.session() as conn:
        rows = analysis_repo.jobs_for_position(conn, str(position_id), limit)
        return {"items": [job_view(conn, request.app.state.scheduler, r) for r in rows]}


@router.get("/analysis-jobs/{job_id}")
def get_job(job_id: UUID, request: Request) -> dict:
    with request.app.state.db.session() as conn:
        return job_view(conn, request.app.state.scheduler, analysis_repo.get(conn, str(job_id)))


@router.post("/analysis-jobs/{job_id}/cancel")
def cancel_job(job_id: UUID, request: Request) -> dict:
    scheduler = request.app.state.scheduler
    with request.app.state.db.session() as conn:
        row = analysis_repo.request_cancel(conn, str(job_id))
        if row["state"] == "running":
            scheduler.cancel_running(row["id"])
        scheduler.notify_threadsafe(row["id"])
        return job_view(conn, scheduler, row)


def _sse(event: str, data: dict, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


@router.get("/analysis-jobs/{job_id}/events")
async def job_events(job_id: UUID, request: Request,
                     max_seconds: Annotated[float, Query(ge=1, le=3600)] = 600):
    """Flux SSE. A chaque (re)connexion, l'etat courant complet est renvoye :
    pas d'historique de deltas a rejouer (Last-Event-ID inutile). Le flux se
    ferme apres `max_seconds` : EventSource se reconnecte seul, sans rien perdre,
    et aucune connexion ne vit indefiniment."""
    app = request.app
    jid = str(job_id)

    def build() -> dict:
        with app.state.db.session() as conn:
            return job_view(conn, app.state.scheduler, analysis_repo.get(conn, jid))

    first = await asyncio.to_thread(build)  # 404 avant d'ouvrir le flux
    queue = app.state.scheduler.broker.subscribe(jid)

    async def stream():
        counter = 0
        view = first
        deadline = asyncio.get_running_loop().time() + max_seconds
        try:
            while True:
                counter += 1
                if view["visibility"] == "full":
                    yield _sse("analysis-snapshot", view, counter)
                    done = view["state"] in analysis_repo.FINAL_STATES
                else:
                    yield _sse("analysis-status", {"job_id": view["id"], "progress_category": view["progress_category"],
                                                   "is_ready": view["is_ready"]}, counter)
                    done = False  # la revelation peut survenir : on reste a l'ecoute
                if done:
                    return
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        return
                    try:
                        await asyncio.wait_for(queue.get(), timeout=min(HEARTBEAT_S, remaining))
                        break
                    except TimeoutError:
                        if await request.is_disconnected():
                            return
                        yield _sse("heartbeat", {})
                if await request.is_disconnected():
                    return
                view = await asyncio.to_thread(build)
        finally:
            app.state.scheduler.broker.unsubscribe(jid, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

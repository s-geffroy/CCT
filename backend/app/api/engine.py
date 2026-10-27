"""Moteur : etat, recherche d'un Stockfish existant, telechargement (Lot 7).

GET /api/v1/engine              etat, moteur utilise, candidats ecartes, telechargement
POST /api/v1/engine/rescan      relit le reglage `engine_path`, recherche, redemarre
POST /api/v1/engine/download    telecharge la release officielle (empreinte verifiee)
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response

from ..domain.errors import DomainError
from ..engine import download as downloader
from ..engine.catalog import RELEASE, asset_for_this_machine
from ..log import get_logger

router = APIRouter(prefix="/api/v1")
log = get_logger("api.engine")
_tasks: set[asyncio.Task] = set()


class DownloadUnavailable(DomainError):
    status_code = 409


def _view(request: Request) -> dict:
    engine = request.app.state.engine
    state = request.app.state.engine_download
    asset = asset_for_this_machine()
    info = engine.info
    return {
        "status": "ready" if info else "absent",
        "current": None if not info else {
            "name": info.name, "source": engine.source, "path": engine.path,
            "threads": info.threads, "hash_mb": info.hash_mb,
        },
        "rejected": [{"path": r.path, "source": r.source, "reason": r.reason} for r in engine.rejected],
        "error": engine.last_error if not info else None,
        "download": state.view(),
        "offer": None if asset is None else {"release": RELEASE, "file": asset.file, "size": asset.size,
                                              "sha256": asset.sha256},
    }


async def _relocate_and_restart(app) -> None:
    engine = app.state.engine
    async with engine.lock:  # jamais au milieu d'une recherche
        await engine.stop()
        await engine.locate(app.state.prefs["engine_path"] or None)
        await engine.start()
    app.state.scheduler.wake()


@router.get("/engine")
def get_engine(request: Request) -> dict:
    return _view(request)


@router.post("/engine/rescan")
async def rescan(request: Request) -> dict:
    await _relocate_and_restart(request.app)
    return _view(request)


@router.post("/engine/download", status_code=202)
async def start_download(request: Request, response: Response) -> dict:
    app = request.app
    state = app.state.engine_download
    asset = asset_for_this_machine()
    if asset is None:
        raise DownloadUnavailable("NO_ENGINE_FOR_PLATFORM",
                                  "Pas de Stockfish officiel pour cette plateforme : indiquez le chemin d'un moteur.")
    if state.status in ("downloading", "verifying", "installing"):
        response.status_code = 200
        return _view(request)

    async def run() -> None:
        try:
            await asyncio.to_thread(downloader.download, asset, app.state.settings.data_dir, state)
            await _relocate_and_restart(app)
            state.status = "done" if app.state.engine.info else "failed"
            if state.status == "failed":
                state.error = "moteur telecharge mais ne demarre pas : " + (app.state.engine.last_error or "?")
            log.info("Stockfish %s telecharge et verifie : %s", RELEASE, state.path)
        except Exception:
            pass  # l'erreur est dans `state`, deja journalisee

    state.status = "downloading"
    task = asyncio.create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _view(request)

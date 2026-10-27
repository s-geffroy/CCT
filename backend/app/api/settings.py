"""Reglages bornes : GET/PUT /api/v1/settings (doc 08).

Threads et hash s'appliquent au moteur apres la recherche en cours (jamais
au milieu) ; les autres reglages valent pour les prochaines analyses.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import ConfigDict

from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")
_background: set[asyncio.Task] = set()  # garder une reference aux taches en cours


class SettingsPatch(StrictModel):
    # Cles validees par `Preferences.update` (bornes et choix au meme endroit).
    model_config = ConfigDict(extra="allow")
    reset: bool = False


def _view(request: Request) -> dict:
    prefs = request.app.state.prefs
    engine = request.app.state.engine
    return {
        "values": prefs.values,
        "fields": prefs.describe(),
        "engine": {
            "applied": {"threads": engine.info.threads, "hash_mb": engine.info.hash_mb} if engine.info else None,
            "pending": engine.pending,
        },
    }


@router.get("/settings")
def get_settings(request: Request) -> dict:
    return _view(request)


@router.put("/settings")
async def put_settings(body: SettingsPatch, request: Request) -> dict:
    app = request.app
    patch = dict(body.model_extra or {})

    def store() -> dict:
        with app.state.db.session() as conn:
            if body.reset:
                app.state.prefs.reset(conn)
            return app.state.prefs.update(conn, patch) if patch else app.state.prefs.values

    values = await asyncio.to_thread(store)
    engine = app.state.engine
    if (values["engine_threads"], values["engine_hash_mb"]) != (engine.threads, engine.hash_mb):
        engine.pending = {"threads": values["engine_threads"], "hash_mb": values["engine_hash_mb"]}
        # En tache de fond : la recherche en cours peut durer plusieurs minutes.
        task = asyncio.create_task(engine.apply(values["engine_threads"], values["engine_hash_mb"]))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return _view(request)

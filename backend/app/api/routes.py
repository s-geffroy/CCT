"""Routes REST /api/v1 : sante, meta, validation, coups (sans etat)."""
from __future__ import annotations

import os
from dataclasses import asdict
from importlib.metadata import version

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from ..domain import moves, positions
from ..settings import APP_VERSION
from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")


class FenIn(StrictModel):
    fen: str = Field(max_length=200)
    variant: str = Field(default="standard", pattern="^standard$")


class MoveIn(StrictModel):
    fen: str = Field(max_length=200)
    # UCI (e2e4, e7e8q) ou SAN anglais (Nf3, exd8=Q).
    move: str = Field(max_length=32)


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request):
    manager = request.app.state.engine
    data_dir = request.app.state.settings.data_dir
    checks = {
        "engine": await manager.is_ready(),
        "database": request.app.state.db.is_ready(),
        "data_dir_writable": data_dir.is_dir() and os.access(data_dir, os.W_OK),
    }
    ok = all(checks.values())
    body = {"status": "ready" if ok else "degraded", "checks": checks}
    if not checks["engine"] and manager.last_error:
        body["engine_error"] = "moteur indisponible"
    return JSONResponse(body, status_code=200 if ok else 503)


@router.get("/meta")
async def meta(request: Request) -> dict:
    info = request.app.state.engine.info
    db = request.app.state.db
    return {
        "app_version": APP_VERSION,
        "python_chess_version": version("chess"),
        "schema_version": db.version,
        "engine": asdict(info) if info else None,
        "capabilities": {
            "variants": ["standard"],
            "multipv_max": 20,
            "target_depth_default": 21,
        },
    }


@router.post("/positions/validate")
async def validate_position(body: FenIn) -> dict:
    return asdict(positions.validate_fen(body.fen))


@router.post("/moves/play")
async def play_move(body: MoveIn) -> dict:
    """Aide sans etat : le serveur arbitre la legalite et calcule le SAN."""
    board = positions.parse_fen(body.fen)
    return asdict(moves.play(board, body.move))

"""Routes REST /api/v1 du Lot 0 : sante, meta, positions, PGN, coups."""
from __future__ import annotations

import os
from dataclasses import asdict
from importlib.metadata import version

import chess
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..domain import moves, pgn, positions
from ..settings import APP_VERSION

router = APIRouter(prefix="/api/v1")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FenIn(StrictModel):
    fen: str = Field(max_length=200)
    variant: str = Field(default="standard", pattern="^standard$")


class PgnIn(StrictModel):
    pgn: str


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
        "data_dir_writable": data_dir.is_dir() and _writable(data_dir),
    }
    body = {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}
    if not checks["engine"] and manager.last_error:
        body["engine_error"] = "moteur indisponible"
    return JSONResponse(body, status_code=200 if all(checks.values()) else 503)


def _writable(path) -> bool:
    return os.access(path, os.W_OK)


@router.get("/meta")
async def meta(request: Request) -> dict:
    info = request.app.state.engine.info
    return {
        "app_version": APP_VERSION,
        "python_chess_version": version("chess"),
        "engine": asdict(info) if info else None,
        "capabilities": {
            "variants": ["standard"],
            "multipv_max": 20,
            "target_depth_default": 21,
        },
    }


@router.post("/positions/validate")
async def validate_position(body: FenIn) -> dict:
    result = positions.validate_fen(body.fen)
    return asdict(result)


@router.post("/games/import-pgn")
async def import_pgn(body: PgnIn, request: Request) -> dict:
    s = request.app.state.settings
    result = pgn.import_pgn(body.pgn, max_bytes=s.max_pgn_bytes, max_games=s.max_pgn_games, max_nodes=s.max_pgn_nodes)
    return asdict(result)


@router.post("/moves/play")
async def play_move(body: MoveIn) -> dict:
    """Aide sans etat (spike Lot 0) : le serveur arbitre la legalite et calcule le SAN."""
    board = positions.parse_fen(body.fen)
    return asdict(moves.play(board, body.move))


@router.get("/positions/start")
async def start_position() -> dict:
    return {"fen": chess.STARTING_FEN}

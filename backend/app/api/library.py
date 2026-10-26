"""Routes de la bibliotheque : imports PGN, parties, arbres, instantanes de position.

Routes synchrones : FastAPI les execute dans son pool de threads, avec une
connexion SQLite par requete.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import Field

from ..domain import pgn, snapshots
from ..domain.errors import InvalidInput, NotFound
from ..domain.positions import HISTORY_UNKNOWN_WARNING
from ..persistence import repo
from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")

Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]

EDITOR_WARNING = "position modifiee librement : elle ne prolonge aucun historique de partie"
PARTIAL_HISTORY_WARNING = (
    "historique connu seulement depuis la position de depart du PGN (en-tete FEN) : "
    "les repetitions anterieures ne sont pas connues"
)

PARTIAL_FEN_HISTORY_WARNING = (
    "historique connu seulement depuis la FEN saisie : les repetitions anterieures ne sont pas connues"
)


class PgnIn(StrictModel):
    pgn: str


class FenPositionIn(StrictModel):
    source: Literal["fen", "editor"]
    fen: str = Field(max_length=200)
    # Coups joues depuis cette FEN (exploration sur l'echiquier) : l'historique
    # est alors connu depuis la FEN, pas avant.
    history_uci: list[Annotated[str, Field(max_length=5)]] = Field(default_factory=list, max_length=2000)


class PgnPositionIn(StrictModel):
    source: Literal["pgn"]
    game_id: UUID
    node_id: UUID


def _db(request: Request):
    return request.app.state.db.session()


# ----------------------------------------------------------------- parties

@router.post("/games/import-pgn", status_code=201)
def import_pgn(body: PgnIn, request: Request) -> dict:
    s = request.app.state.settings
    result = pgn.import_pgn(body.pgn, max_bytes=s.max_pgn_bytes, max_games=s.max_pgn_games, max_nodes=s.max_pgn_nodes)
    with _db(request) as conn:
        import_id, games = repo.save_import(conn, body.pgn, result)
    return {"import_id": import_id, "games": games, "truncated": result.truncated}


@router.get("/games")
def list_games(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    with _db(request) as conn:
        return {"items": repo.list_games(conn, limit, offset), "limit": limit, "offset": offset}


@router.get("/games/{game_id}")
def get_game(game_id: UUID, request: Request) -> dict:
    with _db(request) as conn:
        game = repo.get_game(conn, str(game_id))
    if game is None:
        raise NotFound("GAME_NOT_FOUND", "Partie inconnue.")
    return game


@router.get("/games/{game_id}/tree")
def get_tree(
    game_id: UUID, request: Request,
    root: UUID | None = None,
    max_nodes: Annotated[int, Query(ge=1, le=10_000)] = 2000,
) -> dict:
    with _db(request) as conn:
        game = repo.get_game(conn, str(game_id))
        if game is None:
            raise NotFound("GAME_NOT_FOUND", "Partie inconnue.")
        page = repo.get_tree(conn, str(game_id), str(root) if root else game["root_node_id"], max_nodes)
    if page is None:
        raise NotFound("NODE_NOT_FOUND", "Ce noeud n'appartient pas a cette partie.")
    return {"game_id": game["id"], **asdict(page)}


# --------------------------------------------------------------- positions

PositionIn = Annotated[FenPositionIn | PgnPositionIn, Field(discriminator="source")]


@router.post("/positions", status_code=201)
def create_position(body: PositionIn, request: Request, response: Response) -> dict:
    warnings: list[str] = []
    with _db(request) as conn:
        if isinstance(body, PgnPositionIn):
            game = repo.get_game(conn, str(body.game_id))
            node = repo.get_node(conn, str(body.node_id))
            if game is None or node is None or node["game_id"] != game["id"]:
                raise NotFound("NODE_NOT_FOUND", "Noeud inconnu dans cette partie.")
            root = repo.get_node(conn, game["root_node_id"])
            history = repo.path_from_root(conn, node["id"])
            snap = snapshots.from_history(root["fen"], history, starts_from_initial=game["history_known"])
            if not snap.history_complete:
                warnings.append(PARTIAL_HISTORY_WARNING)
            position, created = repo.create_position(conn, snap, "pgn", game["id"], node["id"])
        elif body.history_uci:
            if body.source == "editor":
                raise InvalidInput("EDITOR_HISTORY", "Une position d'editeur n'a pas d'historique.")
            snap = snapshots.from_history(body.fen, body.history_uci, starts_from_initial=True)
            if not snap.history_complete:
                warnings.append(PARTIAL_FEN_HISTORY_WARNING)
            position, created = repo.create_position(conn, snap, body.source)
        else:
            snap = snapshots.from_fen(body.fen)
            warnings.append(HISTORY_UNKNOWN_WARNING)
            if body.source == "editor":
                warnings.append(EDITOR_WARNING)
            position, created = repo.create_position(conn, snap, body.source)
    if not created:
        response.status_code = 200
    return {**position, "created": created, "warnings": warnings}


@router.get("/positions")
def list_positions(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    with _db(request) as conn:
        return {"items": repo.list_positions(conn, limit, offset), "limit": limit, "offset": offset}


@router.get("/positions/{position_id}")
def get_position(position_id: UUID, request: Request) -> dict:
    with _db(request) as conn:
        position = repo.get_position(conn, str(position_id))
    if position is None:
        raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
    return position

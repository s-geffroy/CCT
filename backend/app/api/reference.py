"""Arbres de reference : /api/v1/reference-trees.

Meme regle de visibilite que les travaux : un arbre n'est lisible que si
aucune seance non revelee ne porte sur l'echiquier de sa racine (sinon l'etat
seul). Toute sortie passe par `tree_view()`.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import Field

from ..domain.errors import NotFound
from ..domain.reference_policy import TreeSettings
from ..persistence import analysis_repo, reference_repo, repo
from ..services import PRIORITY_STUDY
from .analysis import JobIn, enqueue, require_no_session_in_progress
from .schemas import StrictModel

router = APIRouter(prefix="/api/v1")

UciMove = Annotated[str, Field(min_length=4, max_length=5)]


class TreeIn(JobIn):
    """Analyse racine (comme une etude) puis expansions sous plafonds."""
    tree_budget_s: int = Field(default=300, ge=10, le=1800)
    max_nodes: int = Field(default=80, ge=1, le=200)
    max_children: int = Field(default=3, ge=1, le=5)
    node_depth: int = Field(default=21, ge=8, le=32)


class ExpandIn(StrictModel):
    path_uci: list[UciMove] = Field(default_factory=list, max_length=60)


def tree_visible(conn: sqlite3.Connection, tree: sqlite3.Row) -> bool:
    fen = repo.get_position(conn, tree["position_id"])["fen"]
    return analysis_repo.unrevealed_session_on_board(conn, fen) is None


def tree_view(conn: sqlite3.Connection, scheduler, tree: sqlite3.Row) -> dict:
    if not tree_visible(conn, tree):
        return reference_repo.hidden_view(tree)
    return reference_repo.full_view(conn, tree, scheduler)


@router.post("/reference-trees", status_code=201)
def create_tree(body: TreeIn, request: Request, response: Response) -> dict:
    """Etude libre (A) : arbre de reference d'une position, hors seance."""
    with request.app.state.db.session() as conn:
        position = repo.get_position(conn, str(body.position_id))
        if position is None:
            raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
        require_no_session_in_progress(conn, position["fen"])
        root_job, _ = enqueue(request, conn, position_id=position["id"], session_id=None, purpose="study",
                              priority=PRIORITY_STUDY,
                              settings={"target_depth": body.target_depth, "multipv_max": body.multipv_max,
                                        "budget_s": body.budget_s})
        settings = TreeSettings(budget_s=body.tree_budget_s, max_nodes=body.max_nodes,
                                max_children=body.max_children, node_depth=body.node_depth)
        existing = reference_repo.tree_for_root_job(conn, root_job["id"], settings.to_dict())
        if existing is not None:
            response.status_code = 200
            return {**tree_view(conn, request.app.state.scheduler, existing), "reused": True}
        tree_id = request.app.state.reference.create(conn, position_id=position["id"], session_id=None,
                                                     root_job=root_job, settings=settings)
        return {**tree_view(conn, request.app.state.scheduler, reference_repo.get_tree(conn, tree_id)), "reused": False}


@router.get("/reference-trees")
def list_trees(request: Request, position_id: UUID, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    with request.app.state.db.session() as conn:
        rows = reference_repo.study_trees(conn, str(position_id), limit)
        return {"items": [tree_view(conn, request.app.state.scheduler, r) for r in rows]}


@router.get("/reference-trees/{tree_id}")
def get_tree(tree_id: UUID, request: Request) -> dict:
    with request.app.state.db.session() as conn:
        return tree_view(conn, request.app.state.scheduler, reference_repo.get_tree(conn, str(tree_id)))


@router.post("/reference-trees/{tree_id}/expand")
def expand(tree_id: UUID, body: ExpandIn, request: Request) -> dict:
    """Reanalyse d'un noeud (plus profond) ou analyse d'un coup qui prolonge
    un noeud de l'arbre : refusee tant qu'une seance non revelee porte sur la
    racine (sinon ce serait un moyen de lire la reference avant l'heure)."""
    with request.app.state.db.session() as conn:
        tree = reference_repo.get_tree(conn, str(tree_id))
        require_no_session_in_progress(conn, repo.get_position(conn, tree["position_id"])["fen"])
        request.app.state.reference.expand(conn, tree["id"], body.path_uci)
        return tree_view(conn, request.app.state.scheduler, reference_repo.get_tree(conn, tree["id"]))

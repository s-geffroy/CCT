"""Seances B/C : arbre utilisateur, lignes ecrites, export.

L'arbre utilisateur est un etat pur (dict de noeuds) que les operations
transforment en un nouvel etat : la persistance garde chaque etat pour
annuler/retablir. Le serveur arbitre toute legalite et calcule le SAN.
"""
from __future__ import annotations

import copy
import io
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import chess
import chess.pgn

from .errors import DomainError, InvalidInput, NotFound
from .moves import parse_move

ASSESSMENTS = ("white_better", "black_better", "equal", "initiative", "attack", "unclear")
MAX_TREE_NODES = 2000
MAX_COMMENT = 2000
MAX_LINES_TEXT = 20_000
MAX_LINES = 100
MAX_LINE_PLIES = 60

TreeState = dict[str, dict[str, Any]]  # id -> noeud
UNSET: Any = object()  # « champ non fourni », distinct de None (« effacer »)


class Conflict(DomainError):
    status_code = 409


# ------------------------------------------------------------------ arbre

def children_of(state: TreeState, parent_id: str | None) -> list[dict]:
    return sorted((n for n in state.values() if n["parent_id"] == parent_id), key=lambda n: n["order_index"])


def _fen_at(state: TreeState, root_fen: str, node_id: str | None) -> str:
    if node_id is None:
        return root_fen
    if node_id not in state:
        raise NotFound("NODE_NOT_FOUND", "Noeud inconnu dans cet arbre.")
    return state[node_id]["fen_after"]


def add_move(state: TreeState, root_fen: str, parent_id: str | None, move_text: str,
             comment: str = "", now: str = "") -> tuple[TreeState, dict]:
    if len(state) >= MAX_TREE_NODES:
        raise InvalidInput("TREE_TOO_LARGE", f"Arbre limite a {MAX_TREE_NODES} coups.")
    if len(comment) > MAX_COMMENT:
        raise InvalidInput("COMMENT_TOO_LONG", "Commentaire trop long.")
    board = chess.Board(_fen_at(state, root_fen, parent_id))
    move = parse_move(board, move_text)
    siblings = children_of(state, parent_id)
    for sibling in siblings:
        if sibling["move_uci"] == move.uci():
            raise Conflict("DUPLICATE_MOVE", "Ce coup existe deja a cet endroit de l'arbre.", {"node_id": sibling["id"]})
    san = board.san(move)
    board.push(move)
    node = {
        "id": str(uuid.uuid4()),
        "parent_id": parent_id,
        "order_index": len(siblings),
        "move_uci": move.uci(),
        "move_san": san,
        "fen_after": board.fen(),
        "comment": comment,
        "human_assessment": None,
        "created_at": now,
    }
    new_state = copy.deepcopy(state)
    new_state[node["id"]] = node
    return new_state, node


def delete_subtree(state: TreeState, node_id: str) -> TreeState:
    if node_id not in state:
        raise NotFound("NODE_NOT_FOUND", "Noeud inconnu dans cet arbre.")
    doomed = {node_id}
    changed = True
    while changed:
        changed = False
        for n in state.values():
            if n["parent_id"] in doomed and n["id"] not in doomed:
                doomed.add(n["id"])
                changed = True
    parent_id = state[node_id]["parent_id"]
    new_state = {k: copy.deepcopy(v) for k, v in state.items() if k not in doomed}
    for i, sibling in enumerate(children_of(new_state, parent_id)):
        sibling["order_index"] = i
    return new_state


def patch_node(state: TreeState, node_id: str, *, comment: str | None = None,
               assessment: str | None = UNSET, promote: bool = False) -> TreeState:
    if node_id not in state:
        raise NotFound("NODE_NOT_FOUND", "Noeud inconnu dans cet arbre.")
    new_state = copy.deepcopy(state)
    node = new_state[node_id]
    if comment is not None:
        if len(comment) > MAX_COMMENT:
            raise InvalidInput("COMMENT_TOO_LONG", "Commentaire trop long.")
        node["comment"] = comment
    if assessment is not UNSET:
        if assessment is not None and assessment not in ASSESSMENTS:
            raise InvalidInput("BAD_ASSESSMENT", "Appreciation inconnue.")
        node["human_assessment"] = assessment
    if promote:
        # Promotion en suite principale : premier parmi ses freres.
        siblings = [s for s in children_of(new_state, node["parent_id"]) if s["id"] != node_id]
        for i, s in enumerate([node, *siblings]):
            s["order_index"] = i
    return new_state


# ------------------------------------------------- lignes ecrites (mode B)

_NUMBER = re.compile(r"^\d+\.(\.\.)?$|^\d+\.{3}$")
_INLINE_NUMBER = re.compile(r"^\d+\.+(?=\S)")
_ANNOTATION = re.compile(r"[!?]+$")


@dataclass
class ParsedLine:
    text: str
    moves_uci: list[str] = field(default_factory=list)
    moves_san: list[str] = field(default_factory=list)
    # Premier probleme rencontre : la suite est conservee en texte, non jouee.
    error: dict | None = None


def tokenize(line: str) -> list[str]:
    tokens = []
    for raw in line.replace(",", " ").split():
        if _NUMBER.match(raw):
            continue
        token = _INLINE_NUMBER.sub("", raw)
        token = _ANNOTATION.sub("", token)
        if token:
            tokens.append(token)
    return tokens


def parse_lines(root_fen: str, text: str) -> list[ParsedLine]:
    """Analyse des variantes ecrites, une par ligne (SAN ou UCI).

    Utilise A LA SOUMISSION seulement : signaler un coup illegal pendant une
    seance mentale serait deja un diagnostic de calcul.
    """
    if len(text) > MAX_LINES_TEXT:
        raise InvalidInput("LINES_TOO_LONG", "Texte des variantes trop long.")
    results = []
    for raw in [ln.strip() for ln in text.splitlines() if ln.strip()][:MAX_LINES]:
        parsed = ParsedLine(text=raw)
        board = chess.Board(root_fen)
        for ply, token in enumerate(tokenize(raw)[:MAX_LINE_PLIES], start=1):
            try:
                move = parse_move(board, token)
            except InvalidInput as exc:
                parsed.error = {"ply": ply, "token": token, "code": exc.code, "message": exc.message}
                break
            parsed.moves_san.append(board.san(move))
            parsed.moves_uci.append(move.uci())
            board.push(move)
        results.append(parsed)
    return results


def lines_to_tree(root_fen: str, lines: list[ParsedLine]) -> TreeState:
    """Fusionne les prefixes communs des lignes legales en un arbre."""
    state: TreeState = {}
    for line in lines:
        parent: str | None = None
        for uci in line.moves_uci:
            existing = next((n for n in children_of(state, parent) if n["move_uci"] == uci), None)
            if existing is None:
                state, existing = add_move(state, root_fen, parent, uci)
            parent = existing["id"]
    return state


# ------------------------------------------------------------------ export

def export_pgn(root_fen: str, state: TreeState, headers: dict[str, str], notes: str = "") -> str:
    game = chess.pgn.Game()
    if root_fen != chess.STARTING_FEN:
        game.setup(chess.Board(root_fen))
    for key, value in headers.items():
        game.headers[key] = value
    if notes:
        game.comment = notes

    # Parcours iteratif : un arbre peut depasser la profondeur de recursion de Python.
    stack: list[tuple[chess.pgn.GameNode, str | None]] = [(game, None)]
    while stack:
        pgn_node, parent_id = stack.pop()
        for child in children_of(state, parent_id):
            variation = pgn_node.add_variation(chess.Move.from_uci(child["move_uci"]))
            if child["comment"]:
                variation.comment = child["comment"]
            stack.append((variation, child["id"]))
    out = io.StringIO()
    game.accept(chess.pgn.FileExporter(out))
    return out.getvalue()

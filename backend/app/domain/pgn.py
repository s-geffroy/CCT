"""Import PGN avec variantes (RAV), commentaires et NAG, via python-chess.

Le PGN est conserve tel quel ; l'arbre renvoye est une forêt legale (python-chess
refuse les coups illegaux et les signale dans game.errors, que l'on remonte).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import chess
import chess.pgn

from .errors import InvalidInput, TooLarge


@dataclass
class PgnNode:
    id: str
    parent_id: str | None
    ply: int
    uci: str | None
    san: str | None
    fen: str
    comment: str
    starting_comment: str
    nags: list[int]
    children: list[str] = field(default_factory=list)


@dataclass
class PgnGame:
    index: int
    headers: dict[str, str]
    root_id: str
    nodes: dict[str, PgnNode]
    warnings: list[str]
    history_known: bool


@dataclass
class PgnImport:
    games: list[PgnGame]
    truncated: bool


def _game_tree(game: chess.pgn.Game, index: int, budget: list[int]) -> PgnGame:
    nodes: dict[str, PgnNode] = {}
    counter = 0

    def new_id() -> str:
        nonlocal counter
        counter += 1
        budget[0] -= 1
        if budget[0] < 0:
            raise TooLarge("PGN_TOO_MANY_NODES", "Le PGN contient trop de coups et variantes.")
        return f"g{index}n{counter}"

    root_board = game.board()
    root_id = new_id()
    nodes[root_id] = PgnNode(
        id=root_id, parent_id=None, ply=0, uci=None, san=None, fen=root_board.fen(),
        comment=game.comment, starting_comment="", nags=[],
    )
    # Parcours explicite (pas de recursion : un PGN peut etre tres profond).
    stack: list[tuple[chess.pgn.GameNode, str, chess.Board, int]] = [(game, root_id, root_board, 0)]
    while stack:
        node, node_id, board, ply = stack.pop()
        child_entries = []
        for variation in node.variations:
            child_board = board.copy(stack=False)
            san = child_board.san(variation.move)
            child_board.push(variation.move)
            child_id = new_id()
            nodes[child_id] = PgnNode(
                id=child_id, parent_id=node_id, ply=ply + 1, uci=variation.move.uci(), san=san,
                fen=child_board.fen(), comment=variation.comment,
                starting_comment=variation.starting_comment, nags=sorted(variation.nags),
            )
            nodes[node_id].children.append(child_id)
            child_entries.append((variation, child_id, child_board, ply + 1))
        stack.extend(reversed(child_entries))

    headers = {k: v for k, v in game.headers.items()}
    warnings = [str(err) for err in game.errors]
    # Sans en-tete FEN/SetUp, la partie part de la position initiale : l'historique
    # depuis la racine est alors complet.
    history_known = "FEN" not in game.headers
    return PgnGame(index=index, headers=headers, root_id=root_id, nodes=nodes,
                   warnings=warnings, history_known=history_known)


def import_pgn(text: str, *, max_bytes: int, max_games: int, max_nodes: int) -> PgnImport:
    if len(text.encode("utf-8")) > max_bytes:
        raise TooLarge("PGN_TOO_LARGE", f"PGN de plus de {max_bytes} octets.")
    if not text.strip():
        raise InvalidInput("EMPTY_PGN", "PGN vide.")

    stream = io.StringIO(text)
    games: list[PgnGame] = []
    budget = [max_nodes]
    truncated = False
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        if len(games) >= max_games:
            truncated = True
            break
        games.append(_game_tree(game, len(games), budget))

    if not games:
        raise InvalidInput("PGN_NO_GAME", "Aucune partie lisible dans ce PGN.")
    return PgnImport(games=games, truncated=truncated)

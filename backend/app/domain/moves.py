"""Jouer un coup saisi en UCI ou en SAN ; le SAN renvoye est toujours recalcule ici."""
from __future__ import annotations

from dataclasses import dataclass

import chess

from .errors import InvalidInput
from .positions import outcome_code

MAX_MOVE_TEXT = 16


@dataclass
class PlayedMove:
    uci: str
    san: str
    fen_after: str
    outcome: str | None


def _needs_promotion(board: chess.Board, move: chess.Move) -> bool:
    if move.promotion is not None:
        return False
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False
    rank = chess.square_rank(move.to_square)
    return (piece.color == chess.WHITE and rank == 7) or (piece.color == chess.BLACK and rank == 0)


def parse_move(board: chess.Board, text: str) -> chess.Move:
    """UCI d'abord, puis SAN. Une promotion sans piece choisie est refusee :
    jamais de promotion silencieuse en dame."""
    text = text.strip()
    if not text or len(text) > MAX_MOVE_TEXT:
        raise InvalidInput("MOVE_SYNTAX", "Coup vide ou trop long.")
    if not any(board.generate_legal_moves()):
        raise InvalidInput("NO_LEGAL_MOVE", "Aucun coup legal : la partie est terminee dans cette position.")

    move: chess.Move | None = None
    try:
        move = chess.Move.from_uci(text)
    except chess.InvalidMoveError:
        move = None

    if move is not None:
        if _needs_promotion(board, move) and chess.Move(move.from_square, move.to_square, chess.QUEEN) in board.legal_moves:
            raise InvalidInput("PROMOTION_REQUIRED", "Choisir la piece de promotion.", {"uci": text})
        if move not in board.legal_moves:
            raise InvalidInput("ILLEGAL_MOVE", "Ce coup n'est pas legal dans cette position.", {"move": text})
        return move

    try:
        return board.parse_san(text)
    except chess.AmbiguousMoveError:
        raise InvalidInput("AMBIGUOUS_MOVE", "Coup ambigu : preciser la piece ou la case de depart.", {"move": text})
    except chess.IllegalMoveError:
        raise InvalidInput("ILLEGAL_MOVE", "Ce coup n'est pas legal dans cette position.", {"move": text})
    except chess.InvalidMoveError:
        raise InvalidInput("MOVE_SYNTAX", "Notation de coup illisible (UCI ou SAN attendu).", {"move": text})


def play(board: chess.Board, text: str) -> PlayedMove:
    move = parse_move(board, text)
    san = board.san(move)
    after = board.copy(stack=True)
    after.push(move)
    return PlayedMove(uci=move.uci(), san=san, fen_after=after.fen(), outcome=outcome_code(after))

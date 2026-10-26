"""Validation de positions FEN avec python-chess, source de verite des regles."""
from __future__ import annotations

from dataclasses import dataclass, field

import chess

from .errors import InvalidInput

MAX_FEN_LENGTH = 100

# Defauts de position rapportes par Board.status(), avec un message lisible.
_STATUS_MESSAGES: list[tuple[chess.Status, str, str]] = [
    (chess.STATUS_NO_WHITE_KING, "NO_WHITE_KING", "Il manque le roi blanc."),
    (chess.STATUS_NO_BLACK_KING, "NO_BLACK_KING", "Il manque le roi noir."),
    (chess.STATUS_TOO_MANY_KINGS, "TOO_MANY_KINGS", "Il y a plus d'un roi d'une meme couleur."),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS, "TOO_MANY_WHITE_PAWNS", "Plus de 8 pions blancs."),
    (chess.STATUS_TOO_MANY_BLACK_PAWNS, "TOO_MANY_BLACK_PAWNS", "Plus de 8 pions noirs."),
    (chess.STATUS_PAWNS_ON_BACKRANK, "PAWNS_ON_BACKRANK", "Un pion se trouve sur la 1re ou la 8e rangee."),
    (chess.STATUS_TOO_MANY_WHITE_PIECES, "TOO_MANY_WHITE_PIECES", "Plus de 16 pieces blanches."),
    (chess.STATUS_TOO_MANY_BLACK_PIECES, "TOO_MANY_BLACK_PIECES", "Plus de 16 pieces noires."),
    (chess.STATUS_BAD_CASTLING_RIGHTS, "BAD_CASTLING_RIGHTS", "Droits au roque incompatibles avec la position des rois et des tours."),
    (chess.STATUS_INVALID_EP_SQUARE, "INVALID_EP_SQUARE", "Case de prise en passant impossible."),
    (chess.STATUS_OPPOSITE_CHECK, "OPPOSITE_CHECK", "Le camp qui n'a pas le trait est en echec."),
    (chess.STATUS_EMPTY, "EMPTY", "L'echiquier est vide."),
    (chess.STATUS_RACE_CHECK, "RACE_CHECK", "Echec impossible dans cette variante."),
    (chess.STATUS_RACE_OVER, "RACE_OVER", "Partie deja terminee dans cette variante."),
    (chess.STATUS_RACE_MATERIAL, "RACE_MATERIAL", "Materiel impossible dans cette variante."),
    (chess.STATUS_TOO_MANY_CHECKERS, "TOO_MANY_CHECKERS", "Le roi au trait est attaque par plus de deux pieces."),
    (chess.STATUS_IMPOSSIBLE_CHECK, "IMPOSSIBLE_CHECK", "Configuration d'echec impossible a atteindre."),
]

HISTORY_UNKNOWN_WARNING = (
    "historique anterieur inconnu pour une FEN isolee : les repetitions passees ne sont pas connues"
)


@dataclass
class Problem:
    code: str
    message: str


@dataclass
class FenValidation:
    valid: bool
    normalized_fen: str | None = None
    turn: str | None = None
    legal_moves_count: int | None = None
    outcome: str | None = None
    errors: list[Problem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def outcome_code(board: chess.Board) -> str | None:
    """Etat terminal connu depuis cette position (sans historique pour les repetitions)."""
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.is_seventyfive_moves():
        return "seventyfive_moves"
    if board.is_fivefold_repetition():
        return "fivefold_repetition"
    return None


def parse_fen(fen: str) -> chess.Board:
    """Board orthodoxe depuis une FEN ; leve InvalidInput si syntaxe ou position invalide."""
    result = validate_fen(fen)
    if not result.valid:
        first = result.errors[0]
        raise InvalidInput(first.code, first.message, {"errors": [e.__dict__ for e in result.errors]})
    return chess.Board(result.normalized_fen)


def validate_fen(fen: str) -> FenValidation:
    fen = fen.strip()
    if not fen:
        return FenValidation(valid=False, errors=[Problem("EMPTY_FEN", "FEN vide.")])
    if len(fen) > MAX_FEN_LENGTH:
        return FenValidation(valid=False, errors=[Problem("FEN_TOO_LONG", f"FEN de plus de {MAX_FEN_LENGTH} caracteres.")])
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        return FenValidation(valid=False, errors=[Problem("FEN_SYNTAX", f"FEN illisible : {exc}")])

    status = board.status()
    errors = [Problem(code, msg) for flag, code, msg in _STATUS_MESSAGES if status & flag]
    if errors:
        return FenValidation(valid=False, errors=errors)

    return FenValidation(
        valid=True,
        normalized_fen=board.fen(),
        turn="white" if board.turn == chess.WHITE else "black",
        legal_moves_count=board.legal_moves.count(),
        outcome=outcome_code(board),
        warnings=[HISTORY_UNKNOWN_WARNING],
    )

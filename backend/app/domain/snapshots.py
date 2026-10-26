"""Instantanes de position : la position ET son contexte de regles.

Une FEN ne porte pas l'historique : sans lui, impossible de connaitre les
repetitions passees. Un instantane garde donc la FEN de depart et la suite UCI
qui y mene (rejouee et verifiee ici), ou declare l'historique inconnu.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import chess

from .errors import InvalidInput
from .positions import outcome_code, parse_fen

# Change si la semantique de l'empreinte change : les anciens instantanes ne
# sont alors jamais confondus avec les nouveaux.
SNAPSHOT_POLICY_VERSION = 1
MAX_HISTORY_PLIES = 2000


@dataclass(frozen=True)
class Snapshot:
    fen: str
    initial_fen: str
    history_uci: tuple[str, ...] | None  # None = historique inconnu
    history_complete: bool  # True seulement si l'historique part de la position initiale
    turn: str
    legal_moves_count: int
    outcome: str | None
    claimable_draw: str | None
    context_key: str
    variant: str = "standard"

    def board(self) -> chess.Board:
        """Board reconstruit avec sa pile : repetitions connues si l'historique l'est."""
        board = chess.Board(self.initial_fen)
        for uci in self.history_uci or ():
            board.push_uci(uci)
        return board


def _claimable(board: chess.Board) -> str | None:
    if board.can_claim_threefold_repetition():
        return "threefold_repetition"
    if board.can_claim_fifty_moves():
        return "fifty_moves"
    return None


def _context_key(initial_fen: str, history: tuple[str, ...] | None, fen: str) -> str:
    payload = {
        "variant": "standard",
        "initial_fen": initial_fen,
        # Espace de noms separe : un historique inconnu n'est jamais confondu
        # avec un historique vide.
        "history": list(history) if history is not None else "history_unknown",
        "fen": fen,
        "policy": SNAPSHOT_POLICY_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _build(board: chess.Board, initial_fen: str, history: tuple[str, ...] | None, complete: bool) -> Snapshot:
    fen = board.fen()
    return Snapshot(
        fen=fen,
        initial_fen=initial_fen,
        history_uci=history,
        history_complete=complete,
        turn="white" if board.turn == chess.WHITE else "black",
        legal_moves_count=board.legal_moves.count(),
        outcome=outcome_code(board),
        # Sans historique, seule la regle des 50 coups (compteur de la FEN) est connue.
        claimable_draw=_claimable(board),
        context_key=_context_key(initial_fen, history, fen),
    )


def from_fen(fen: str) -> Snapshot:
    """FEN isolee (saisie ou editeur) : historique inconnu."""
    board = parse_fen(fen)
    normalized = board.fen()
    return _build(board, normalized, None, False)


def from_history(initial_fen: str, history_uci: list[str], *, starts_from_initial: bool) -> Snapshot:
    """Position atteinte en rejouant `history_uci` depuis `initial_fen`."""
    if len(history_uci) > MAX_HISTORY_PLIES:
        raise InvalidInput("HISTORY_TOO_LONG", f"Historique de plus de {MAX_HISTORY_PLIES} demi-coups.")
    board = parse_fen(initial_fen)
    start = board.fen()
    for ply, uci in enumerate(history_uci, start=1):
        try:
            move = chess.Move.from_uci(uci)
        except chess.InvalidMoveError:
            raise InvalidInput("HISTORY_SYNTAX", "Coup illisible dans l'historique.", {"ply": ply, "move": uci})
        if move not in board.legal_moves:
            raise InvalidInput("HISTORY_ILLEGAL", "Coup illegal dans l'historique.", {"ply": ply, "move": uci})
        board.push(move)
    return _build(board, start, tuple(history_uci), starts_from_initial and start == chess.STARTING_FEN)


def history_san(initial_fen: str, history_uci: list[str] | None) -> list[str] | None:
    """Historique en notation algebrique (calcule ici, jamais par le client)."""
    if history_uci is None:
        return None
    board = chess.Board(initial_fen)
    sans = []
    for uci in history_uci:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)
    return sans

from __future__ import annotations

import chess
import pytest

from app.domain import moves, pgn, positions
from app.domain.errors import InvalidInput, TooLarge

USER_FEN = "rb1qkb1r/pp3ppp/2n1pn2/2pp4/3P4/2NQPN2/PPP2PPP/R1B1K2R w KQkq - 0 1"


# --- FEN -------------------------------------------------------------------

def test_user_example_fen_is_valid_and_counts_are_computed():
    result = positions.validate_fen(USER_FEN)
    assert result.valid, result.errors
    assert result.turn == "white"
    # Le nombre n'est pas ecrit en dur : python-chess est la reference.
    assert result.legal_moves_count == chess.Board(USER_FEN).legal_moves.count()
    assert result.outcome is None
    assert positions.HISTORY_UNKNOWN_WARNING in result.warnings


@pytest.mark.parametrize("fen, code", [
    ("8/8/8/8/8/8/8/8 w - - 0 1", "NO_WHITE_KING"),
    ("4k3/8/8/8/8/8/8/4KK2 w - - 0 1", "TOO_MANY_KINGS"),
    ("4k3/8/8/8/8/8/8/P3K3 w - - 0 1", "PAWNS_ON_BACKRANK"),
    ("4k3/4R3/8/8/8/8/8/4K3 w - - 0 1", "OPPOSITE_CHECK"),
    ("4k3/8/8/8/8/8/8/4K3 w KQ - 0 1", "BAD_CASTLING_RIGHTS"),
    ("pas une fen", "FEN_SYNTAX"),
    ("", "EMPTY_FEN"),
])
def test_invalid_positions_are_explained(fen, code):
    result = positions.validate_fen(fen)
    assert not result.valid
    assert code in [e.code for e in result.errors]


@pytest.mark.parametrize("fen, outcome", [
    ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", "checkmate"),
    ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "stalemate"),
    ("7k/8/6K1/8/8/8/8/8 w - - 0 1", "insufficient_material"),
])
def test_terminal_positions(fen, outcome):
    result = positions.validate_fen(fen)
    assert result.valid
    assert result.outcome == outcome


def test_en_passant_square_is_kept_only_when_meaningful():
    fen = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
    result = positions.validate_fen(fen)
    assert result.valid and " f6 " in result.normalized_fen


# --- coups -----------------------------------------------------------------

def test_play_uci_and_san_give_server_side_san():
    board = chess.Board()
    assert moves.play(board, "g1f3").san == "Nf3"
    assert moves.play(board, "Nf3").uci == "g1f3"


def test_illegal_move_is_refused():
    with pytest.raises(InvalidInput) as err:
        moves.play(chess.Board(), "e2e5")
    assert err.value.code == "ILLEGAL_MOVE"


def test_promotion_must_be_explicit():
    board = chess.Board("8/4P3/8/8/8/8/8/k6K w - - 0 1")
    with pytest.raises(InvalidInput) as err:
        moves.play(board, "e7e8")
    assert err.value.code == "PROMOTION_REQUIRED"
    assert moves.play(board, "e7e8n").san == "e8=N"
    with pytest.raises(InvalidInput):
        moves.play(board, "e8")  # SAN sans piece de promotion


def test_castling_and_en_passant():
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert moves.play(board, "e1g1").san == "O-O"
    assert moves.play(board, "O-O-O").uci == "e1c1"
    ep = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    assert moves.play(ep, "e5f6").san == "exf6"


def test_no_move_in_terminal_position():
    with pytest.raises(InvalidInput) as err:
        moves.play(chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"), "h8g8")
    assert err.value.code == "NO_LEGAL_MOVE"


# --- PGN -------------------------------------------------------------------

PGN_WITH_VARIATIONS = """[Event "Test"]
[White "A"]
[Black "B"]
[Result "*"]

{Avant le premier coup} 1. e4 e5 (1... c5 2. Nf3 (2. c3 d5) 2... d6 $1 {Najdorf ?}) 2. Nf3 {main} Nc6 $2 (2... Nf6 3. Nxe5) 3. Bb5 *
"""


def _by_san(game):
    return {n.san: n for n in game.nodes.values() if n.san}


def test_pgn_keeps_variations_comments_and_nags():
    result = pgn.import_pgn(PGN_WITH_VARIATIONS, max_bytes=10_000, max_games=10, max_nodes=1000)
    assert len(result.games) == 1
    game = result.games[0]
    root = game.nodes[game.root_id]
    assert root.comment == "Avant le premier coup"
    assert game.history_known
    e4 = game.nodes[root.children[0]]
    assert e4.san == "e4"
    # 1...e5 (ligne principale) puis 1...c5 (variante), dans l'ordre du PGN.
    assert [game.nodes[c].san for c in e4.children] == ["e5", "c5"]
    sans = _by_san(game)
    assert sans["d6"].nags == [1] and sans["d6"].comment == "Najdorf ?"
    assert sans["Nc6"].nags == [2]
    c5 = sans["c5"]
    assert [game.nodes[c].san for c in c5.children] == ["Nf3", "c3"]
    # Chaque noeud porte la FEN resultante, verifiee par python-chess.
    assert sans["Bb5"].fen == chess.Board("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3").fen()
    assert not game.warnings


def test_pgn_illegal_move_is_reported_not_hidden():
    text = '[Event "x"]\n\n1. e4 e5 2. Ke3 Nc6 *\n'
    game = pgn.import_pgn(text, max_bytes=10_000, max_games=10, max_nodes=1000).games[0]
    assert game.warnings, "l'erreur de parsing doit remonter"
    assert {n.san for n in game.nodes.values() if n.san} == {"e4", "e5"}


def test_pgn_with_fen_header_marks_history_unknown():
    text = '[SetUp "1"]\n[FEN "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"]\n\n1. e4 *\n'
    game = pgn.import_pgn(text, max_bytes=10_000, max_games=10, max_nodes=1000).games[0]
    assert not game.history_known


def test_pgn_multiple_games_and_limits():
    two = PGN_WITH_VARIATIONS + "\n" + PGN_WITH_VARIATIONS
    assert len(pgn.import_pgn(two, max_bytes=10_000, max_games=10, max_nodes=1000).games) == 2
    assert pgn.import_pgn(two, max_bytes=10_000, max_games=1, max_nodes=1000).truncated
    with pytest.raises(TooLarge):
        pgn.import_pgn(two, max_bytes=100, max_games=10, max_nodes=1000)
    with pytest.raises(TooLarge):
        pgn.import_pgn(two, max_bytes=10_000, max_games=10, max_nodes=5)


def test_pgn_comment_with_script_is_kept_as_plain_text():
    text = '[Event "x"]\n\n1. e4 {<script>alert(1)</script>} *\n'
    game = pgn.import_pgn(text, max_bytes=10_000, max_games=10, max_nodes=1000).games[0]
    # Stocke tel quel : l'echappement est la responsabilite du rendu (texte React).
    assert "<script>" in _by_san(game)["e4"].comment

"""Integration UCI avec le vrai Stockfish de l'image (profondeurs faibles)."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import chess
import pytest

from app.engine.analysis import analyse_root
from app.engine.uci import EngineManager
from app.settings import get_settings
from conftest import STOCKFISH, requires_engine

pytestmark = requires_engine


def _analyse(fen: str, **kwargs):
    async def go():
        manager = EngineManager(replace(get_settings(), stockfish_path=STOCKFISH, engine_threads=1, engine_hash_mb=16))
        await manager.locate(None)
        await manager.start()
        assert manager.info is not None, manager.last_error
        try:
            return manager.info, await analyse_root(manager.engine, chess.Board(fen), **kwargs)
        finally:
            await manager.stop()
    return asyncio.run(go())


def test_engine_identity_and_build_info():
    info, _ = _analyse(chess.STARTING_FEN, target_depth=1, multipv_max=1)
    assert info.name.startswith("Stockfish 19")
    assert info.build.get("tag") == "sf_19"


def test_more_than_20_moves_gives_at_most_20_distinct_roots():
    board = chess.Board()
    assert board.legal_moves.count() == 20
    kiwipete = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert chess.Board(kiwipete).legal_moves.count() > 20
    _, result = _analyse(kiwipete, target_depth=8, multipv_max=20, stages=(4, 8))
    roots = [line.root_move_uci for line in result.lines]
    assert result.multipv == 20 and len(roots) == 20 and len(set(roots)) == 20
    assert result.status == "depth_met"
    assert all(line.exact_depth >= 8 for line in result.lines)
    assert set(result.stages_reached_s) == {4, 8}


def test_fewer_than_20_moves_no_fictitious_lines():
    fen = "8/8/8/8/8/4k3/8/4K2R w K - 0 1"
    legal = chess.Board(fen).legal_moves.count()
    assert legal < 20
    _, result = _analyse(fen, target_depth=6, multipv_max=20)
    assert result.multipv == legal == len(result.lines)
    assert len({line.root_move_uci for line in result.lines}) == legal


def test_terminal_position_has_no_line():
    _, result = _analyse("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", target_depth=8)
    assert result.status == "terminal" and result.lines == []


def test_mate_is_typed_not_converted_to_centipawns():
    # Mat en 1 pour les Blancs : Qf8#.
    _, result = _analyse("7k/8/6K1/8/8/8/8/5Q2 w - - 0 1", target_depth=6, multipv_max=1)
    best = result.lines[0]
    assert best.score.kind == "mate" and best.score.value == 1 and best.score.perspective == "white"


def test_black_to_move_scores_are_white_pov():
    # Les Noirs matent en 1 : le score cote Blancs doit etre un mat negatif.
    _, result = _analyse("6k1/8/8/8/8/8/5qPP/7K b - - 0 1", target_depth=6, multipv_max=1)
    assert result.lines[0].score.kind == "mate" and result.lines[0].score.value < 0


def test_budget_interrupts_without_claiming_target_depth():
    _, result = _analyse(chess.STARTING_FEN, target_depth=40, multipv_max=20, budget_s=0.5)
    assert result.status == "budget_exhausted"
    assert result.elapsed_s < 5
    assert not any(line.exact_depth >= 40 for line in result.lines)


def test_invalid_position_never_reaches_the_engine():
    # Roi noir en echec avec le trait aux Blancs : Stockfish planterait.
    with pytest.raises(ValueError):
        _analyse("7k/8/5QK1/8/8/8/8/8 w - - 0 1", target_depth=4)


def test_ready_endpoint_with_engine(engine_client):
    r = engine_client.get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    assert engine_client.get("/api/v1/meta").json()["engine"]["name"].startswith("Stockfish")

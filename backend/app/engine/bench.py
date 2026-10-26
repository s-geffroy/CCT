"""Banc d'essai Stockfish (Lot 0) : mesure avant de figer les budgets par defaut.

    sudo appctl run tests python -m app.engine.bench [--budget 300] [--threads 2] [--hash 128]

Une ligne de journal par palier atteint ; un resume JSON en fin de sortie.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, replace

import chess

from ..log import get_logger, setup_logging
from ..settings import get_settings
from .analysis import analyse_root
from .uci import EngineManager

log = get_logger("bench")

POSITIONS = {
    "startpos": chess.STARTING_FEN,
    # FEN d'exemple fournie par l'utilisateur (doc 14).
    "user_example": "rb1qkb1r/pp3ppp/2n1pn2/2pp4/3P4/2NQPN2/PPP2PPP/R1B1K2R w KQkq - 0 1",
    # Milieu de jeu tactique classique (Kiwipete, positions de test de perft).
    "kiwipete": "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    # Finale : moins de 20 coups legaux, test de la cardinalite MultiPV.
    "few_moves": "8/8/8/8/8/4k3/8/4K2R w K - 0 1",
}


async def run(budget: float, positions: list[str], threads: int | None, hash_mb: int | None) -> dict:
    settings = get_settings()
    if threads is not None:
        settings = replace(settings, engine_threads=threads)
    if hash_mb is not None:
        settings = replace(settings, engine_hash_mb=hash_mb)
    manager = EngineManager(settings)
    await manager.start()
    if manager.info is None:
        raise SystemExit(f"moteur indisponible : {manager.last_error}")
    report: dict = {"engine": asdict(manager.info), "cpu_count": os.cpu_count(), "budget_s": budget, "results": []}

    try:
        for name in positions:
            board = chess.Board(POSITIONS[name])
            for multipv_max in (1, 20):
                label = f"{name} multipv<={multipv_max}"
                log.info("debut %s (coups legaux=%d)", label, board.legal_moves.count())
                t0 = time.monotonic()
                result = await analyse_root(
                    manager.engine, board, target_depth=21, multipv_max=multipv_max, budget_s=budget,
                    on_stage=lambda d, t, label=label: log.info("%s : palier %d atteste a %.1f s", label, d, t),
                )
                log.info("fin %s : statut=%s lignes=%d duree=%.1f s nps=%s", label, result.status,
                         len(result.lines), time.monotonic() - t0, result.nps)
                report["results"].append({
                    "position": name, "multipv_max": multipv_max, "multipv": result.multipv,
                    "legal_moves": result.legal_moves_count, "status": result.status,
                    "stages_reached_s": result.stages_reached_s, "elapsed_s": result.elapsed_s,
                    "nodes": result.nodes, "nps": result.nps,
                    "min_exact_depth": min((l.exact_depth for l in result.lines), default=0),
                    "best": result.lines[0].root_move_uci if result.lines else None,
                })
    finally:
        await manager.stop()
    return report


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=300.0)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--hash", type=int, dest="hash_mb")
    parser.add_argument("--positions", default=",".join(POSITIONS))
    args = parser.parse_args()
    report = asyncio.run(run(args.budget, args.positions.split(","), args.threads, args.hash_mb))
    print("BENCH_JSON " + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

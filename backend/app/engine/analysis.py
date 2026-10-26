"""Recherche racine MultiPV progressive, avec paliers de profondeur attestes.

Un palier `d` n'est atteste pour une ligne que par une information *exacte*
(sans borne lower/upper) de profondeur >= d. « Profondeur 21 atteinte » n'est
declare que si toutes les lignes demandees l'ont attestee.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import chess
import chess.engine

DEFAULT_STAGES = (8, 12, 16, 21)


@dataclass
class ScoreDTO:
    kind: str  # 'cp' | 'mate' | 'unknown'
    value: int | None = None  # centipions ou nombre de coups jusqu'au mat
    perspective: str = "white"
    bound: str | None = None  # 'lower' | 'upper' | None


@dataclass
class LineDTO:
    multipv: int
    root_move_uci: str
    pv_uci: list[str]
    depth: int
    seldepth: int | None
    score: ScoreDTO
    nodes: int | None
    exact_depth: int  # derniere profondeur atteinte sans borne


@dataclass
class RootAnalysis:
    legal_moves_count: int
    multipv: int
    target_depth: int
    status: str  # 'terminal' | 'depth_met' | 'budget_exhausted' | 'incomplete' | 'cancelled'
    lines: list[LineDTO]
    stages_reached_s: dict[int, float] = field(default_factory=dict)
    elapsed_s: float = 0.0
    nodes: int | None = None
    nps: int | None = None


def score_dto(info: chess.engine.InfoDict) -> ScoreDTO:
    pov = info.get("score")
    bound = "lower" if info.get("lowerbound") else "upper" if info.get("upperbound") else None
    if pov is None:
        return ScoreDTO(kind="unknown")
    white = pov.white()
    if white.is_mate():
        return ScoreDTO(kind="mate", value=white.mate(), bound=bound)
    return ScoreDTO(kind="cp", value=white.score(), bound=bound)


async def analyse_root(
    engine: chess.engine.UciProtocol,
    board: chess.Board,
    *,
    target_depth: int = 21,
    multipv_max: int = 20,
    budget_s: float = 300.0,
    stages: tuple[int, ...] = DEFAULT_STAGES,
    on_stage=None,
    on_progress: Callable[[str, RootAnalysis], None] | None = None,
    stop_event: asyncio.Event | None = None,
) -> RootAnalysis:
    """Recherche racine progressive.

    `on_progress(kind, partiel)` est appele a chaque info utile (`kind="info"`)
    et a chaque palier atteste (`kind="stage"`) ; `stop_event` interrompt la
    recherche (annulation), meme si Stockfish n'emet rien pendant longtemps.
    """
    if not board.is_valid():
        # Une position invalide n'est jamais envoyee au moteur (T06).
        raise ValueError("position invalide : analyse refusee")
    legal = board.legal_moves.count()
    if legal == 0:
        return RootAnalysis(legal_moves_count=0, multipv=0, target_depth=target_depth,
                            status="terminal", lines=[])
    k = min(multipv_max, legal)
    lines: dict[int, LineDTO] = {}
    stages = tuple(s for s in stages if s <= target_depth)
    reached: dict[int, float] = {}
    last_nodes = last_nps = None
    status = "budget_exhausted"
    t0 = time.monotonic()

    def partial(current_status: str) -> RootAnalysis:
        return RootAnalysis(
            legal_moves_count=legal, multipv=k, target_depth=target_depth, status=current_status,
            lines=[lines[i] for i in sorted(lines)], stages_reached_s=dict(reached),
            elapsed_s=round(time.monotonic() - t0, 3), nodes=last_nodes, nps=last_nps,
        )

    with await engine.analysis(board, chess.engine.Limit(depth=target_depth), multipv=k) as analysis:
        stopper = None
        if stop_event is not None:
            async def watch() -> None:
                await stop_event.wait()
                analysis.stop()
            stopper = asyncio.create_task(watch())
        try:
            async with asyncio.timeout(budget_s):
                async for info in analysis:
                    pv = info.get("pv")
                    idx = info.get("multipv", 1)
                    if not pv or "depth" not in info:
                        continue
                    depth = info["depth"]
                    score = score_dto(info)
                    previous = lines.get(idx)
                    prev_exact = previous.exact_depth if previous else 0
                    exact = max(prev_exact, depth) if score.bound is None else prev_exact
                    lines[idx] = LineDTO(
                        multipv=idx, root_move_uci=pv[0].uci(), pv_uci=[m.uci() for m in pv],
                        depth=depth, seldepth=info.get("seldepth"), score=score,
                        nodes=info.get("nodes"), exact_depth=exact,
                    )
                    last_nodes = info.get("nodes", last_nodes)
                    last_nps = info.get("nps", last_nps)
                    if len(lines) == k:
                        floor = min(line.exact_depth for line in lines.values())
                        for stage in stages:
                            if stage not in reached and floor >= stage:
                                reached[stage] = round(time.monotonic() - t0, 3)
                                if on_stage:
                                    on_stage(stage, reached[stage])
                                if on_progress:
                                    on_progress("stage", partial("provisional"))
                    if on_progress:
                        on_progress("info", partial("provisional"))
            # Iteration terminee sans timeout : Stockfish a fini sa recherche.
            floor = min((line.exact_depth for line in lines.values()), default=0)
            # Fin sans profondeur attestee pour toutes les lignes : on ne
            # pretend ni succes ni budget epuise.
            status = "depth_met" if len(lines) == k and floor >= target_depth else "incomplete"
            if stop_event is not None and stop_event.is_set():
                status = "cancelled"
        except TimeoutError:
            analysis.stop()
            status = "budget_exhausted"
        finally:
            if stopper is not None:
                stopper.cancel()

    ordered = [lines[i] for i in sorted(lines)]
    return RootAnalysis(
        legal_moves_count=legal, multipv=k, target_depth=target_depth, status=status,
        lines=ordered, stages_reached_s=reached, elapsed_s=round(time.monotonic() - t0, 3),
        nodes=last_nodes, nps=last_nps,
    )

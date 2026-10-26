"""Scanner anti-spoiler reutilisable (P01/P02, doc 08 « Interdit avant revelation »).

Un client hostile lit TOUT ce que le serveur renvoie ; il ne doit y trouver
aucune donnee moteur, sous aucune cle, avant la revelation.
"""
from __future__ import annotations

from typing import Any

FORBIDDEN_KEYS = {
    "pv", "pv_uci", "pv_san", "score", "best_move", "bestmove", "rank", "multipv", "multipv_index",
    "mate", "depth", "seldepth", "target_move", "reference", "reference_tree", "analysis",
    "lines", "engine_lines", "evaluation_cp", "correct_moves_count",
}


def keys_in(payload: Any, path: str = "$") -> list[str]:
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.append(f"{path}.{key}")
            found.extend(keys_in(value, f"{path}.{key}"))
    elif isinstance(payload, list):
        for i, value in enumerate(payload):
            found.extend(keys_in(value, f"{path}[{i}]"))
    return found


def leaks(payload: Any) -> list[str]:
    return [p for p in keys_in(payload) if p.rsplit(".", 1)[-1] in FORBIDDEN_KEYS]

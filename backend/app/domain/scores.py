"""Comparaison d'evaluations moteur, sans jamais convertir un mat en centipions
affiches : les cles ci-dessous servent a ORDONNER, pas a montrer.

Les scores sont stockes au point de vue des Blancs (doc 06) ; on compare au
point de vue du camp qui joue le coup, une seule fois.
"""
from __future__ import annotations

MATE_BASE = 100_000
# Classes qualitatives prudentes (au point de vue du camp au trait), a calibrer :
# un ecart de centipions seul ne fait jamais un verdict (doc 07).
WINNING_CP = 300


def white_key(score: dict | None) -> int | None:
    """Cle d'ordre au point de vue des Blancs ; None si inconnue."""
    if not score:
        return None
    kind = score.get("kind")
    if kind == "cp" and score.get("value") is not None:
        return int(score["value"])
    if kind == "mate" and score.get("value") is not None:
        n = int(score["value"])
        if n == 0:  # position deja matee : le resultat dit qui a gagne
            return {"1-0": MATE_BASE, "0-1": -MATE_BASE}.get(score.get("result"), None)
        return MATE_BASE - n if n > 0 else -MATE_BASE - n
    if kind == "draw":
        return 0
    return None


def mover_key(score: dict | None, mover_white: bool) -> int | None:
    key = white_key(score)
    if key is None:
        return None
    return key if mover_white else -key


def outcome_class(key: int) -> int:
    """2 = gagnant, 1 = equilibre/incertain, 0 = perdant (camp au trait)."""
    if key >= WINNING_CP:
        return 2
    if key <= -WINNING_CP:
        return 0
    return 1


CLASS_LABEL = {2: "gagnant", 1: "equilibre", 0: "perdant"}


def format_score(score: dict | None) -> str:
    """Affichage au point de vue des Blancs, bornes conservees."""
    if not score or score.get("kind") == "unknown":
        return "?"
    prefix = {"lower": ">=", "upper": "<="}.get(score.get("bound") or "", "")
    kind, value = score.get("kind"), score.get("value")
    if kind == "draw":
        return "nulle"
    if kind == "mate":
        if value == 0:
            return {"1-0": "mat (1-0)", "0-1": "mat (0-1)"}.get(score.get("result"), "mat")
        return f"{prefix}M{'+' if value > 0 else '-'}{abs(value)}"
    return f"{prefix}{value / 100:+.2f}"


def terminal_score(outcome_result: str) -> dict:
    """Position terminale (mat, pat...) : pas de recherche, un resultat."""
    if outcome_result == "1/2-1/2":
        return {"kind": "draw", "value": 0, "perspective": "white", "bound": None, "result": outcome_result}
    return {"kind": "mate", "value": 0, "perspective": "white", "bound": None, "result": outcome_result}

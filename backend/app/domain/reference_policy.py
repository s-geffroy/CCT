"""Politique d'expansion de l'arbre de reference (doc 06, « algorithme borne »).

Fonction de classement exploratoire, pas oracle. A partir des noeuds deja
analyses, elle propose les prochains noeuds a analyser, dans l'ordre :

1. les branches du joueur absentes de l'arbre (`user_branch`), y compris un
   premier coup hors des 20 retenus ;
2. les defenses adverses critiques : apres chacun des meilleurs coups racine
   (`top_rank`), les reponses adverses les plus fortes (`opponent_best_defense`,
   puis `opponent_alternative` si elles restent proches de la meilleure), puis
   la meilleure riposte, jusqu'a `auto_max_ply` demi-coups.

Plafonds : `max_nodes`, budget de temps de l'arbre, `max_children` par noeud.
Ce qui n'est pas explore garde ce statut ; jamais « mauvaise variante ».
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .scores import mover_key

POLICY_VERSION = 1

PRIORITY_USER_BRANCH = 45
PRIORITY_AUTO = 40  # moins le demi-coup : les noeuds proches de la racine d'abord


@dataclass(frozen=True)
class TreeSettings:
    budget_s: int = 300          # plafond additionnel pour les expansions automatiques
    max_nodes: int = 80          # anti-explosion (racine comprise)
    max_children: int = 3        # largeur auto, et MultiPV des noeuds
    node_depth: int = 21         # profondeur locale visee a chaque noeud
    node_budget_s: int = 30      # plafond par noeud
    auto_max_ply: int = 4        # profondeur des expansions automatiques depuis la racine
    inflight: int = 2            # travaux de l'arbre en file a la fois (equite avec le reste)
    critical_reply_margin: int = 150  # cp : reponse adverse « proche » de la meilleure

    @classmethod
    def from_dict(cls, data: dict) -> TreeSettings:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self) -> dict:
        return {**asdict(self), "policy_version": POLICY_VERSION}


@dataclass
class PlanNode:
    path: tuple[str, ...]
    status: str
    lines: list[dict] = field(default_factory=list)  # vues de lignes : rank, root_move_uci, score...
    analysed: bool = False  # analyse terminee (resultat final ou partiel exploitable)


@dataclass(frozen=True)
class Candidate:
    path: tuple[str, ...]
    reason: str
    priority: int


def root_side_to_move(ply: int) -> bool:
    """Le camp de l'exercice a le trait aux demi-coups pairs."""
    return ply % 2 == 0


def candidates(settings: TreeSettings, nodes: dict[tuple[str, ...], PlanNode],
               user_paths: list[tuple[str, ...]], root_white: bool) -> list[Candidate]:
    """Noeuds a creer, du plus prioritaire au moins prioritaire (deterministe)."""
    out: list[Candidate] = []
    seen: set[tuple[str, ...]] = set(nodes)

    # 1. Branches du joueur : prefixes d'abord (un parent avant ses enfants).
    for path in sorted(user_paths, key=len):
        if path not in seen:
            out.append(Candidate(path, "user_branch", PRIORITY_USER_BRANCH))
            seen.add(path)

    # 2. Defenses critiques et meilleures ripostes, en largeur.
    for path in sorted(nodes, key=lambda p: (len(p), p)):
        node = nodes[path]
        ply = len(path)
        if not node.analysed or not node.lines or ply >= settings.auto_max_ply:
            continue
        ranked = sorted(node.lines, key=lambda line: line["rank"])
        if ply == 0:
            chosen = [(line, "top_rank") for line in ranked[: settings.max_children]]
        elif root_side_to_move(ply):
            chosen = [(ranked[0], "top_rank")]
        else:
            mover_white = root_white if root_side_to_move(ply) else not root_white
            best = mover_key(ranked[0]["score"], mover_white)
            chosen = [(ranked[0], "opponent_best_defense")]
            for line in ranked[1:]:
                key = mover_key(line["score"], mover_white)
                if len(chosen) >= settings.max_children or best is None or key is None:
                    break
                if best - key <= settings.critical_reply_margin:
                    chosen.append((line, "opponent_alternative"))
        for line, reason in chosen:
            child = (*path, line["root_move_uci"])
            if child not in seen:
                out.append(Candidate(child, reason, PRIORITY_AUTO - ply))
                seen.add(child)

    # Les branches du joueur passent devant ; puis les noeuds proches de la racine.
    user = [c for c in out if c.reason == "user_branch"]
    auto = sorted((c for c in out if c.reason != "user_branch"), key=lambda c: len(c.path))
    return user + auto

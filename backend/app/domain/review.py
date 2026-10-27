"""Debriefing : comparaison prudente de la tentative avec la reference (doc 07).

Projection pure : ni l'arbre du joueur ni l'arbre de reference ne sont modifies.

1. L'arbre du joueur (deja normalise en UCI par le serveur a la saisie) est
   parcouru par chemins depuis la racine.
2. Chaque coup est rapproche du noeud de reference de meme chemin ; une
   transposition (meme echiquier par un autre chemin) est annotee, jamais
   fusionnee ni utilisee comme preuve.
3. Une evaluation n'est une preuve que si elle est exacte (sans borne) et
   atteste une profondeur suffisante (`min_verdict_depth`) ; sinon le verdict
   est « non determine ».
4. Hierarchie : legalite > refutation concrete > ecart robuste > divergence de
   PV seule (jamais un verdict).

Les seuils sont des valeurs de conception, prudentes et versionnees : un ecart
de centipions seul ne fait pas de verdict, il faut en plus un changement de
classe (gagnant / equilibre / perdant) pour parler de refutation.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import chess

from .scores import CLASS_LABEL, format_score, mover_key, outcome_class, white_key

POLICY = {
    "version": 1,
    "min_verdict_depth": 12,     # profondeur attestee minimale pour conclure
    "equivalent_cp": 30,         # ecart negligeable : coup equivalent
    "refutation_cp": 200,        # ecart minimal d'une refutation (avec changement de classe)
    "critical_defense_cp": 100,  # ecart minimal d'une defense critique oubliee
    "assessment_cp": 100,        # appreciation « avantage » contredite au-dela
    "equal_assessment_cp": 200,  # appreciation « egalite » contredite au-dela
    "max_omitted_listed": 3,     # candidats non envisages cites (les meilleurs d'abord)
}

CATEGORY_ORDER = [
    "no_trace", "illegal_continuation", "tactical_refutation", "critical_defense_omitted",
    "evaluation_mismatch", "candidate_omitted", "unverified", "acceptable_alternative", "candidate_found",
]


@dataclass
class RefNode:
    """Ce que le debriefing sait d'un noeud de reference."""
    node_id: str
    path: tuple[str, ...]
    status: str
    reason: str
    lines: list[dict] = field(default_factory=list)  # lignes de l'analyse du noeud (vue `line_view`)
    final: bool = False
    terminal_score: dict | None = None


@dataclass
class Eval:
    score: dict
    depth: int
    pv_uci: list[str]
    pv_san: list[str]
    source: str  # 'parent_search' (meme recherche que les alternatives) | 'targeted' | 'terminal'
    node_id: str | None

    def robust(self, min_depth: int) -> bool:
        if self.source == "terminal":
            return True
        return (white_key(self.score) is not None and not self.score.get("bound")
                and self.depth >= min_depth)


class Reference:
    def __init__(self, nodes: dict[tuple[str, ...], RefNode], root_fen: str, building: bool):
        self.nodes = nodes
        self.root_fen = root_fen
        self.building = building
        self._by_board: dict[str, tuple[str, ...]] = {}
        for path in sorted(nodes, key=len):
            self._by_board.setdefault(_board_key(_board_after(root_fen, path)), path)

    def lines_at(self, path: tuple[str, ...]) -> list[dict]:
        node = self.nodes.get(path)
        return sorted(node.lines, key=lambda l: l["rank"]) if node else []

    def eval_of_move(self, path: tuple[str, ...], move: str) -> Eval | None:
        """Evaluation du coup `move` joue depuis `path` (point de vue des Blancs).

        De preference la recherche du parent (comparable aux alternatives) ;
        sinon l'analyse ciblee de la position apres le coup.
        """
        parent = self.nodes.get(path)
        for line in self.lines_at(path):
            if line["root_move_uci"] == move:
                return Eval(line["score"], line["exact_depth"], line["pv_uci"], line["pv_san"], "parent_search",
                            parent.node_id if parent else None)
        child = self.nodes.get((*path, move))
        if child is None:
            return None
        san = _san(self.root_fen, path, move)
        if child.terminal_score is not None:
            return Eval(child.terminal_score, 0, [move], [san], "terminal", child.node_id)
        lines = self.lines_at(child.path)
        if not lines:
            return None
        best = lines[0]
        return Eval(best["score"], best["exact_depth"] + 1, [move, *best["pv_uci"]], [san, *best["pv_san"]],
                    "targeted", child.node_id)

    def best_at(self, path: tuple[str, ...]) -> tuple[str, Eval] | None:
        lines = self.lines_at(path)
        if not lines:
            return None
        best = lines[0]
        node = self.nodes[path]
        return best["root_move_uci"], Eval(best["score"], best["exact_depth"], best["pv_uci"], best["pv_san"],
                                            "parent_search", node.node_id)

    def transposition(self, path: tuple[str, ...]) -> tuple[str, ...] | None:
        if path in self.nodes:
            return None
        other = self._by_board.get(_board_key(_board_after(self.root_fen, path)))
        return other if other is not None and other != path else None

    def why_missing(self, path: tuple[str, ...]) -> str:
        node = self.nodes.get(path)
        if node is None:
            return "position non analysee"
        if node.status == "pruned_by_policy":
            return "branche ecartee par les plafonds d'analyse (noeuds ou budget)"
        if node.status in ("queued", "provisional"):
            return "analyse en cours"
        if node.status == "failed":
            return "analyse en echec"
        return "analyse sans resultat exploitable"


# ------------------------------------------------------------------ outils

def _board_after(root_fen: str, path: tuple[str, ...]) -> chess.Board:
    board = chess.Board(root_fen)
    for uci in path:
        board.push_uci(uci)
    return board


def _board_key(board: chess.Board) -> str:
    return " ".join(board.fen().split()[:4])


def _san(root_fen: str, path: tuple[str, ...], move: str) -> str:
    board = _board_after(root_fen, path)
    return board.san(chess.Move.from_uci(move))


def _line_text(root_fen: str, path: tuple[str, ...], sans: list[str]) -> str:
    """« 12. Cf3 Cf6 13. ... » depuis la position atteinte par `path`."""
    board = _board_after(root_fen, path)
    number, white = board.fullmove_number, board.turn == chess.WHITE
    out = []
    for i, san in enumerate(sans):
        if white:
            out.append(f"{number}. {san}")
        else:
            out.append(f"{number}... {san}" if i == 0 else san)
            number += 1
        white = not white
    return " ".join(out)


def node_paths(tree: dict) -> dict[str, tuple[str, ...]]:
    """id de noeud du joueur -> chemin UCI depuis la racine."""
    paths: dict[str, tuple[str, ...]] = {}
    for node_id in tree:
        chain, current = [], node_id
        while current is not None and current not in paths:
            chain.append(current)
            current = tree[current]["parent_id"]
        base = paths[current] if current is not None else ()
        for nid in reversed(chain):
            base = (*base, tree[nid]["move_uci"])
            paths[nid] = base
    return paths


def _children(tree: dict, parent: str | None) -> list[dict]:
    return sorted((n for n in tree.values() if n["parent_id"] == parent), key=lambda n: n["order_index"])


def _diag(category: str, *, verdict: str, explanation: str, certainty: str, evidence: dict | None = None,
          user_node_id: str | None = None, reference_node_id: str | None = None) -> dict:
    return {"category": category, "verdict": verdict, "explanation": explanation, "certainty": certainty,
            "evidence": evidence or {}, "user_node_id": user_node_id, "reference_node_id": reference_node_id}


def _depth_note(e: Eval) -> str:
    return "position terminale" if e.source == "terminal" else f"profondeur {e.depth}"


# ------------------------------------------------------------------ rapport

def build_report(*, root_fen: str, attempt: dict, reference: Reference | None, tree_state: str | None,
                 policy: dict = POLICY) -> dict:
    min_depth = policy["min_verdict_depth"]
    root_white = chess.Board(root_fen).turn == chess.WHITE
    tree: dict = attempt.get("tree") or {}
    diagnostics: list[dict] = []
    verdicts: dict[str, dict] = {}

    # Qualite declaree de la reference.
    quality_notes = []
    root_best = reference.best_at(()) if reference else None
    if reference is None:
        quality, quality_notes = "insufficient", ["aucune analyse moteur pour cette seance"]
    elif root_best is None:
        quality = "provisional" if reference.building else "insufficient"
        quality_notes = ["analyse racine " + ("en cours" if reference.building else "sans resultat")]
    elif not root_best[1].robust(min_depth):
        quality = "provisional" if reference.building else "insufficient"
        quality_notes = [f"analyse racine insuffisante ({_depth_note(root_best[1])}, minimum {min_depth} pour conclure)"]
    else:
        quality = "provisional" if reference.building else "final"
        if reference.building:
            quality_notes = ["arbre de reference en cours de construction : rapport provisoire"]

    # Traces non verifiables : autoevaluation seulement (P10).
    if attempt.get("no_trace"):
        diagnostics.append(_diag(
            "no_trace", verdict="no_trace", certainty="certain",
            explanation="Seance mentale sans transcription : seule votre autoevaluation est disponible, "
                        "aucun diagnostic de calcul n'est possible."))
        return _finish(quality, quality_notes, diagnostics, verdicts, policy, dimensions={
            "coverage": None, "anticipation": None, "accuracy": None, "horizon": None, "evaluation": None})

    # Legalite des lignes ecrites (certain : regles et position connues).
    legal_moves = sum(len(line["moves_uci"]) for line in attempt.get("written_lines") or [])
    moves_total = legal_moves
    for i, line in enumerate(attempt.get("written_lines") or []):
        err = line.get("error")
        if err:
            moves_total += 1
            diagnostics.append(_diag(
                "illegal_continuation", verdict="illegal", certainty="certain",
                explanation=f"Ligne {i + 1}, coup {err['ply']} « {err['token']} » : {err['message']}",
                evidence={"line_index": i, "text": line["text"], **err}))
    if attempt.get("mode") == "tree":
        legal_moves = moves_total = len(tree)  # chaque coup a ete valide par le serveur a la saisie

    paths = node_paths(tree)
    usable = reference is not None and quality != "insufficient"

    def mover_white_at(path: tuple[str, ...]) -> bool:
        return root_white if len(path) % 2 == 0 else not root_white

    # Verdict par coup du joueur.
    refuted_nodes: set[str] = set()
    for node_id, path in sorted(paths.items(), key=lambda kv: (len(kv[1]), kv[1])):
        node = tree[node_id]
        parent_path, move = path[:-1], path[-1]
        own_move = len(parent_path) % 2 == 0  # coup du camp de l'exercice
        verdict: dict = {"path_uci": list(path), "own_move": own_move}
        verdicts[node_id] = verdict
        transposed = reference.transposition(path) if reference else None
        if transposed:
            verdict["transposition_of"] = list(transposed)
        if not usable:
            verdict["verdict"] = "unverified"
            continue
        best = reference.best_at(parent_path)
        e_move = reference.eval_of_move(parent_path, move)
        if best is None or e_move is None or not best[1].robust(min_depth) or not e_move.robust(min_depth):
            verdict["verdict"] = "unverified"
            missing = parent_path if best is None else (*parent_path, move)
            verdict["reason"] = (reference.why_missing(missing) if (best is None or e_move is None)
                                 else f"profondeur attestee insuffisante (minimum {min_depth})")
            if own_move:
                diagnostics.append(_diag(
                    "unverified", verdict="move_unverified", certainty="undetermined", user_node_id=node_id,
                    explanation=f"{node['move_san']} : variante non verifiee ({verdict['reason']}), "
                                "aucune conclusion definitive.",
                    evidence={"path_uci": list(path), "reason": verdict["reason"]}))
            continue
        best_move, e_best = best
        mw = mover_white_at(parent_path)
        k_best, k_move = mover_key(e_best.score, mw), mover_key(e_move.score, mw)
        loss = 0 if move == best_move else max(0, k_best - k_move)
        verdict.update({"score": e_move.score, "depth": e_move.depth, "source": e_move.source,
                        "best_move_uci": best_move, "best_move_san": e_best.pv_san[0] if e_best.pv_san else None,
                        "best_score": e_best.score, "loss_cp": loss if abs(loss) < 50_000 else None})
        class_drop = outcome_class(k_move) < outcome_class(k_best)
        if own_move:
            if loss <= policy["equivalent_cp"]:
                verdict["verdict"] = "concordant"
            elif loss >= policy["refutation_cp"] and class_drop:
                verdict["verdict"] = "refuted"
                refuted_nodes.add(node_id)
                diagnostics.append(_refutation(root_fen, node, parent_path, e_move, e_best, k_move, k_best))
            else:
                verdict["verdict"] = "acceptable"
                if len(parent_path) > 0:
                    diagnostics.append(_acceptable(root_fen, node, parent_path, e_move, e_best, k_move, k_best))
        else:
            if loss <= policy["equivalent_cp"]:
                verdict["verdict"] = "best_defense"
            elif loss >= policy["critical_defense_cp"]:
                verdict["verdict"] = "weaker_reply"
            else:
                verdict["verdict"] = "plausible_reply"

    # Couverture des candidats a la racine.
    root_moves = [n["move_uci"] for n in _children(tree, None)]
    coverage: dict = {"status": "undetermined", "found": None, "known_relevant": None,
                      "user_candidates": [n["move_san"] for n in _children(tree, None)]}
    if usable and root_best is not None:
        mw = mover_white_at(())
        k_top = mover_key(root_best[1].score, mw)
        relevant = [l for l in reference.lines_at(())
                    if Eval(l["score"], l["exact_depth"], [], [], "parent_search", None).robust(min_depth)
                    and k_top - mover_key(l["score"], mw) <= policy["equivalent_cp"]]
        # Trouve = coup du joueur equivalent au meilleur, qu'il soit ou non dans
        # les lignes de la recherche racine (analyse ciblee sinon).
        found_ids = [n["id"] for n in _children(tree, None) if verdicts[n["id"]].get("verdict") == "concordant"]
        relevant_moves = {l["root_move_uci"] for l in relevant} | {tree[i]["move_uci"] for i in found_ids}
        coverage.update({"status": "determined", "found": len(found_ids), "known_relevant": len(relevant_moves),
                         "relevant": [l["root_move_san"] for l in relevant]})
        root_node = reference.nodes.get(())
        for n in _children(tree, None):
            v = verdicts[n["id"]]
            if n["id"] in found_ids:
                diagnostics.append(_diag(
                    "candidate_found", verdict="found", certainty="verified", user_node_id=n["id"],
                    reference_node_id=root_node.node_id if root_node else None,
                    explanation=f"Vous avez envisage {n['move_san']}, parmi les meilleurs coups de la reference "
                                f"({format_score(v.get('score'))}, profondeur {v.get('depth')}).",
                    evidence={"move_uci": n["move_uci"], "score": v.get("score"), "depth": v.get("depth")}))
            elif v.get("verdict") == "acceptable":
                diagnostics.append(_acceptable(root_fen, n, (), *_evals(reference, (), n["move_uci"], mw)))
        if root_moves:
            omitted = [l for l in relevant if l["root_move_uci"] not in root_moves]
            for line in omitted[: policy["max_omitted_listed"]]:
                diagnostics.append(_diag(
                    "candidate_omitted", verdict="omitted", certainty="verified",
                    reference_node_id=root_node.node_id if root_node else None,
                    explanation=f"Candidat de premier plan non envisage : {line['root_move_san']} "
                                f"({format_score(line['score'])}, profondeur {line['exact_depth']}). "
                                "Ce n'est pas une faute en soi.",
                    evidence={"move_uci": line["root_move_uci"], "pv_san": line["pv_san"][:10],
                              "score": line["score"], "depth": line["exact_depth"]}))
    elif root_moves or tree:
        diagnostics.append(_diag(
            "unverified", verdict="reference_insufficient", certainty="undetermined",
            explanation="Reference insuffisante : aucun verdict sur vos coups. " + "; ".join(quality_notes),
            evidence={"notes": quality_notes}))

    # Anticipation adverse : apres chacun de vos coups, la defense critique.
    anticipation = {"found": 0, "missed": 0, "unverified": 0}
    if usable:
        for node_id, path in paths.items():
            node = tree[node_id]
            if not verdicts[node_id]["own_move"]:
                continue
            replies = _children(tree, node_id)
            if not replies:
                continue  # horizon : vous vous etes arrete ici, ce n'est pas une omission
            best = reference.best_at(path)
            if best is None or not best[1].robust(min_depth):
                anticipation["unverified"] += 1
                continue
            defense, e_def = best
            if any(r["move_uci"] == defense for r in replies):
                anticipation["found"] += 1
                continue
            mw = mover_white_at(path)
            e_replies = [reference.eval_of_move(path, r["move_uci"]) for r in replies]
            if any(e is None or not e.robust(min_depth) for e in e_replies):
                anticipation["unverified"] += 1
                diagnostics.append(_diag(
                    "unverified", verdict="defense_unverified", certainty="undetermined", user_node_id=node_id,
                    explanation=f"Apres {node['move_san']}, la defense {e_def.pv_san[0]} n'a pas ete envisagee ; "
                                "l'importance de cet oubli n'a pas pu etre verifiee.",
                    evidence={"defense_uci": defense, "pv_san": e_def.pv_san[:10]}))
                continue
            k_def = mover_key(e_def.score, mw)
            k_user = max(mover_key(e.score, mw) for e in e_replies)
            if k_def - k_user >= policy["critical_defense_cp"]:
                anticipation["missed"] += 1
                diagnostics.append(_diag(
                    "critical_defense_omitted", verdict="missed", certainty="verified", user_node_id=node_id,
                    reference_node_id=reference.nodes[path].node_id if path in reference.nodes else None,
                    explanation=f"Apres {node['move_san']}, vous avez envisage "
                                f"{', '.join(r['move_san'] for r in replies)}, mais pas la defense "
                                f"{e_def.pv_san[0]} ({format_score(e_def.score)}, {_depth_note(e_def)}).",
                    evidence={"after_path_uci": list(path), "defense_uci": defense,
                              "line": _line_text(root_fen, path, e_def.pv_san[:10]), "score": e_def.score,
                              "depth": e_def.depth, "fen": _board_after(root_fen, path).fen()}))
            else:
                anticipation["found"] += 1  # defense equivalente envisagee

    # Appreciations humaines (qualitatives) contre une reference robuste.
    evaluation = {"concordant": 0, "mismatch": 0, "not_comparable": 0}
    assessed = [(nid, paths[nid], tree[nid]["human_assessment"], tree[nid]["move_san"])
                for nid in paths if tree[nid].get("human_assessment")]
    sa = attempt.get("self_assessment") or {}
    if sa.get("evaluation"):
        assessed.append((None, (), sa["evaluation"], None))
    for node_id, path, assessment, san in assessed:
        if not usable or assessment not in ("white_better", "black_better", "equal"):
            evaluation["not_comparable"] += 1
            continue
        e = root_best[1] if not path else reference.eval_of_move(path[:-1], path[-1])
        if e is None or not e.robust(min_depth):
            evaluation["not_comparable"] += 1
            continue
        key = white_key(e.score)
        mismatch = ((assessment == "white_better" and key <= -policy["assessment_cp"])
                    or (assessment == "black_better" and key >= policy["assessment_cp"])
                    or (assessment == "equal" and abs(key) >= policy["equal_assessment_cp"]))
        if not mismatch:
            evaluation["concordant"] += 1
            continue
        evaluation["mismatch"] += 1
        where = f"apres {san}" if san else "dans la position de depart"
        diagnostics.append(_diag(
            "evaluation_mismatch", verdict="mismatch", certainty="verified", user_node_id=node_id,
            explanation=f"Votre appreciation {where} ({assessment}) contredit la reference "
                        f"({format_score(e.score)}, {_depth_note(e)}). Appreciation qualitative : seuils prudents.",
            evidence={"path_uci": list(path), "assessment": assessment, "score": e.score, "depth": e.depth}))

    # Horizon et exactitude des lignes restituees.
    leaves = [nid for nid in paths if not _children(tree, nid)]
    plies = [len(paths[nid]) for nid in leaves]
    horizon = {"lines": len(leaves), "max_plies": max(plies, default=0),
               "median_plies": statistics.median(plies) if plies else 0}

    def leaf_status(nid: str) -> str:
        chain = []
        current = nid
        while current is not None:
            chain.append(current)
            current = tree[current]["parent_id"]
        if any(c in refuted_nodes for c in chain):
            return "refuted"
        if any(verdicts[c].get("verdict") == "unverified" for c in chain if verdicts[c]["own_move"]):
            return "unverified"
        return "sound"

    statuses = [leaf_status(nid) for nid in leaves]
    accuracy = {"legal_moves": legal_moves, "moves_total": moves_total,
                "lines_total": len(leaves), "lines_refuted": statuses.count("refuted"),
                "lines_without_refutation": statuses.count("sound"), "lines_unverified": statuses.count("unverified")}

    return _finish(quality, quality_notes, diagnostics, verdicts, policy, dimensions={
        "coverage": coverage, "anticipation": anticipation if usable else None, "accuracy": accuracy,
        "horizon": horizon, "evaluation": evaluation})


def _evals(reference: Reference, path: tuple[str, ...], move: str, mw: bool):
    e_move = reference.eval_of_move(path, move)
    _best_move, e_best = reference.best_at(path)
    return e_move, e_best, mover_key(e_move.score, mw), mover_key(e_best.score, mw)


def _refutation(root_fen: str, node: dict, parent_path: tuple[str, ...], e_move: Eval, e_best: Eval,
                k_move: int, k_best: int) -> dict:
    after = (*parent_path, node["move_uci"])
    return _diag(
        "tactical_refutation", verdict="refuted", certainty="verified", user_node_id=node["id"],
        reference_node_id=e_move.node_id,
        explanation=f"{node['move_san']} est refute : {_line_text(root_fen, parent_path, e_move.pv_san[:10])} "
                    f"({format_score(e_move.score)}, {_depth_note(e_move)}) ; la position passe de "
                    f"« {CLASS_LABEL[outcome_class(k_best)]} » a « {CLASS_LABEL[outcome_class(k_move)]} ». "
                    f"Meilleur : {e_best.pv_san[0]} ({format_score(e_best.score)}).",
        evidence={"path_uci": list(after), "refutation_pv_uci": e_move.pv_uci[:12],
                  "refutation_pv_san": e_move.pv_san[:12], "turning_point_fen": _board_after(root_fen, after).fen(),
                  "score": e_move.score, "best_move_san": e_best.pv_san[0], "best_score": e_best.score,
                  "depth": e_move.depth, "best_depth": e_best.depth})


def _acceptable(root_fen: str, node: dict, parent_path: tuple[str, ...], e_move: Eval, e_best: Eval,
                k_move: int, k_best: int) -> dict:
    return _diag(
        "acceptable_alternative", verdict="acceptable", certainty="verified", user_node_id=node["id"],
        explanation=f"{node['move_san']} differe du premier choix de la reference ({e_best.pv_san[0]}), "
                    f"sans perte determinante etablie ({format_score(e_move.score)} contre "
                    f"{format_score(e_best.score)}, {_depth_note(e_move)}).",
        evidence={"path_uci": [*parent_path, node["move_uci"]], "score": e_move.score, "best_score": e_best.score,
                  "best_move_san": e_best.pv_san[0], "depth": e_move.depth})


def _finish(quality: str, notes: list[str], diagnostics: list[dict], verdicts: dict, policy: dict,
            dimensions: dict) -> dict:
    diagnostics.sort(key=lambda d: CATEGORY_ORDER.index(d["category"]))
    return {"quality": quality, "quality_notes": notes, "policy": policy, "dimensions": dimensions,
            "diagnostics": diagnostics, "node_verdicts": verdicts}

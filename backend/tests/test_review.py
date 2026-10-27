"""Lot 4 : politique d'expansion et debriefing, sur des references synthetiques
(sans moteur) — chaque categorie du doc 07 et chaque abstention."""
from __future__ import annotations

import chess

from app.domain.reference_policy import PlanNode, TreeSettings, candidates
from app.domain.review import RefNode, Reference, build_report
from app.domain.scores import format_score, mover_key, white_key

START = chess.STARTING_FEN


def cp(v, bound=None):
    return {"kind": "cp", "value": v, "perspective": "white", "bound": bound}


def lines_at(fen_path: tuple[str, ...], spec: list[tuple[str, dict, int]], root=START) -> list[dict]:
    """spec : (coup uci, score blanc, profondeur attestee) dans l'ordre des rangs."""
    board = chess.Board(root)
    for uci in fen_path:
        board.push_uci(uci)
    out = []
    for rank, (uci, score, depth) in enumerate(spec, start=1):
        san = board.san(chess.Move.from_uci(uci))
        out.append({"rank": rank, "root_move_uci": uci, "root_move_san": san, "pv_uci": [uci], "pv_san": [san],
                    "score": score, "exact_depth": depth})
    return out


def ref(nodes: dict[tuple[str, ...], list], building=False, root=START) -> Reference:
    return Reference({p: RefNode(f"r{i}", p, "depth_met", "x", lines_at(p, spec, root), True)
                      for i, (p, spec) in enumerate(nodes.items())}, root, building)


def attempt(paths: list[tuple[str, ...]], assessments: dict | None = None, root=START, **extra) -> dict:
    tree, ids = {}, {}
    for path in sorted(paths, key=len):
        board = chess.Board(root)
        for uci in path[:-1]:
            board.push_uci(uci)
        node_id = "u" + "-".join(path)
        parent = ids.get(path[:-1])
        siblings = [n for n in tree.values() if n["parent_id"] == parent]
        tree[node_id] = {"id": node_id, "parent_id": parent, "order_index": len(siblings), "move_uci": path[-1],
                         "move_san": board.san(chess.Move.from_uci(path[-1])),
                         "human_assessment": (assessments or {}).get(path)}
        ids[path] = node_id
    return {"mode": "tree", "tree": tree, "no_trace": False, "self_assessment": None, **extra}


ROOT_LINES = [("e2e4", cp(30), 20), ("d2d4", cp(25), 20), ("g1f3", cp(20), 20), ("c2c4", cp(15), 20),
              ("f2f3", cp(-80), 20)]


def cats(report):
    return [d["category"] for d in report["diagnostics"]]


# ------------------------------------------------------------------ scores

def test_score_keys_order_mates_without_turning_them_into_centipawns():
    assert white_key({"kind": "mate", "value": 1}) > white_key({"kind": "mate", "value": 5}) > white_key(cp(900))
    assert white_key({"kind": "mate", "value": -1}) < white_key({"kind": "mate", "value": -5}) < white_key(cp(-900))
    assert mover_key(cp(120), mover_white=False) == -120
    assert format_score({"kind": "mate", "value": -3, "bound": None}) == "M-3"
    assert format_score(cp(25, "lower")) == ">=+0.25"
    assert white_key({"kind": "unknown"}) is None


# ---------------------------------------------------------------- politique

def test_policy_puts_user_branches_first_then_critical_defenses_breadth_first():
    settings = TreeSettings(max_children=3, auto_max_ply=4)
    root = PlanNode((), "depth_met", lines_at((), ROOT_LINES), analysed=True)
    after_e4 = PlanNode(("e2e4",), "depth_met", lines_at(("e2e4",), [
        ("c7c5", cp(20), 18), ("e7e5", cp(60), 18), ("e7e6", cp(400), 18)]), analysed=True)
    out = candidates(settings, {(): root, ("e2e4",): after_e4}, [("b2b3",), ("b2b3", "e7e5")], root_white=True)
    assert [c.path for c in out[:2]] == [("b2b3",), ("b2b3", "e7e5")]
    assert all(c.reason == "user_branch" for c in out[:2])
    auto = {c.path: c.reason for c in out[2:]}
    assert auto[("d2d4",)] == auto[("g1f3",)] == "top_rank" and ("c2c4",) not in auto       # 3 meilleurs coups
    # Reponses adverses : la meilleure, puis celles a moins de 150 cp ; e6 (400) est ecartee.
    assert auto[("e2e4", "c7c5")] == "opponent_best_defense"
    assert auto[("e2e4", "e7e5")] == "opponent_alternative" and ("e2e4", "e7e6") not in auto
    assert [len(c.path) for c in out[2:]] == sorted(len(c.path) for c in out[2:])


def test_policy_stops_at_auto_max_ply_and_ignores_unanalysed_nodes():
    settings = TreeSettings(auto_max_ply=1)
    root = PlanNode((), "depth_met", lines_at((), ROOT_LINES), analysed=True)
    e4 = PlanNode(("e2e4",), "queued")
    out = candidates(settings, {(): root, ("e2e4",): e4}, [], root_white=True)
    assert {c.path for c in out} == {("d2d4",), ("g1f3",)}


# ----------------------------------------------------------------- rapport

def test_refutation_candidates_and_critical_defense():
    reference = ref({
        (): ROOT_LINES,
        ("g2g4",): [("d7d5", cp(-350), 18)],                       # analyse ciblee du coup du joueur
        ("e2e4",): [("c7c5", cp(20), 18), ("e7e5", cp(35), 18)],
        ("e2e4", "a7a6"): [("d2d4", cp(150), 17)],
    })
    report = build_report(root_fen=START, attempt=attempt([("e2e4",), ("e2e4", "a7a6"), ("g2g4",)]),
                          reference=reference, tree_state="complete")
    assert report["quality"] == "final"
    c = cats(report)
    assert c.index("tactical_refutation") < c.index("critical_defense_omitted") < c.index("candidate_found")
    refutation = next(d for d in report["diagnostics"] if d["category"] == "tactical_refutation")
    assert refutation["user_node_id"] == "ug2g4" and refutation["evidence"]["refutation_pv_san"] == ["g4", "d5"]
    assert "« equilibre » a « perdant »" in refutation["explanation"]
    assert refutation["evidence"]["turning_point_fen"].startswith("rnbqkbnr/pppppppp/8/8/6P1/")
    critical = next(d for d in report["diagnostics"] if d["category"] == "critical_defense_omitted")
    assert critical["evidence"]["defense_uci"] == "c7c5" and "c5" in critical["explanation"]
    assert report["dimensions"]["coverage"] == {
        "status": "determined", "found": 1, "known_relevant": 4, "user_candidates": ["e4", "g4"],
        "relevant": ["e4", "d4", "Nf3", "c4"]}
    assert c.count("candidate_omitted") == 3
    assert report["dimensions"]["anticipation"] == {"found": 0, "missed": 1, "unverified": 0}
    assert report["node_verdicts"]["ug2g4"]["verdict"] == "refuted"
    assert report["node_verdicts"]["ue2e4"]["verdict"] == "concordant"
    assert report["node_verdicts"]["ue2e4-a7a6"]["verdict"] == "weaker_reply"
    assert report["dimensions"]["accuracy"]["lines_refuted"] == 1


def test_equivalent_defense_counts_as_found_and_different_move_is_not_punished():
    reference = ref({(): ROOT_LINES, ("d2d4",): [("g8f6", cp(25), 18), ("d7d5", cp(30), 18)]})
    report = build_report(root_fen=START, attempt=attempt([("d2d4",), ("d2d4", "d7d5")]), reference=reference,
                          tree_state="complete")
    assert "critical_defense_omitted" not in cats(report) and "tactical_refutation" not in cats(report)
    assert report["dimensions"]["anticipation"]["found"] == 1
    assert report["node_verdicts"]["ud2d4"]["verdict"] == "concordant"                      # P08


def test_losing_less_without_class_change_is_an_acceptable_alternative():
    lines = [("e2e4", cp(30), 20), ("f2f3", cp(-80), 20)]
    report = build_report(root_fen=START, attempt=attempt([("f2f3",)]), reference=ref({(): lines}),
                          tree_state="complete")
    assert "acceptable_alternative" in cats(report) and "tactical_refutation" not in cats(report)


def test_shallow_reference_abstains():
    shallow = [(m, s, 8) for m, s, _ in ROOT_LINES]
    report = build_report(root_fen=START, attempt=attempt([("g2g4",)]), reference=ref({(): shallow}),
                          tree_state="complete")
    assert report["quality"] == "insufficient"
    assert cats(report) == ["unverified"] and "minimum 12" in report["diagnostics"][0]["explanation"]
    assert report["node_verdicts"]["ug2g4"]["verdict"] == "unverified"


def test_bounded_scores_are_not_evidence():
    lines = [("e2e4", cp(30, "lower"), 20), ("g2g4", cp(-350, "upper"), 20)]
    report = build_report(root_fen=START, attempt=attempt([("g2g4",)]), reference=ref({(): lines}),
                          tree_state="complete")
    assert report["quality"] == "insufficient" and "tactical_refutation" not in cats(report)


def test_missing_branch_is_unverified_with_its_reason():
    reference = ref({(): ROOT_LINES})
    reference.nodes[("h2h4",)] = RefNode("p", ("h2h4",), "pruned_by_policy", "user_branch")
    report = build_report(root_fen=START, attempt=attempt([("h2h4",)]), reference=reference, tree_state="node_limit")
    diag = next(d for d in report["diagnostics"] if d["category"] == "unverified")
    assert "plafonds" in diag["explanation"] and diag["certainty"] == "undetermined"


def test_building_tree_gives_a_provisional_report():
    report = build_report(root_fen=START, attempt=attempt([("e2e4",)]), reference=ref({(): ROOT_LINES}, building=True),
                          tree_state="building")
    assert report["quality"] == "provisional"


def test_no_trace_and_no_reference():
    report = build_report(root_fen=START, attempt={"mode": "mental", "tree": {}, "no_trace": True},
                          reference=ref({(): ROOT_LINES}), tree_state="complete")
    assert cats(report) == ["no_trace"] and report["dimensions"]["coverage"] is None                 # P10
    report = build_report(root_fen=START, attempt=attempt([("e2e4",)]), reference=None, tree_state=None)
    assert report["quality"] == "insufficient" and cats(report) == ["unverified"]


def test_illegal_written_line_is_certain_even_without_reference():
    a = attempt([("e2e4",)], mode="mental", written_lines=[
        {"text": "e4 Ke7 Kxe8", "moves_uci": ["e2e4", "e8e7"], "moves_san": ["e4", "Ke7"],
         "error": {"ply": 3, "token": "Kxe8", "code": "ILLEGAL_MOVE", "message": "coup illegal"}}])
    report = build_report(root_fen=START, attempt=a, reference=None, tree_state=None)
    diag = next(d for d in report["diagnostics"] if d["category"] == "illegal_continuation")
    assert diag["certainty"] == "certain" and diag["evidence"]["ply"] == 3
    assert report["dimensions"]["accuracy"]["legal_moves"] == 2 and report["dimensions"]["accuracy"]["moves_total"] == 3


def test_evaluation_mismatch_and_transposition_annotation():
    reference = ref({(): ROOT_LINES, ("g2g4",): [("d7d5", cp(-350), 18)],
                     ("g1f3", "g8f6", "d2d4"): [("d7d5", cp(30), 16)]})
    a = attempt([("g2g4",), ("d2d4",), ("d2d4", "g8f6"), ("d2d4", "g8f6", "g1f3")],
                assessments={("g2g4",): "white_better", ("d2d4",): "unclear"})
    report = build_report(root_fen=START, attempt=a, reference=reference, tree_state="complete")
    mismatch = [d for d in report["diagnostics"] if d["category"] == "evaluation_mismatch"]
    assert len(mismatch) == 1 and mismatch[0]["user_node_id"] == "ug2g4"
    assert report["dimensions"]["evaluation"] == {"concordant": 0, "mismatch": 1, "not_comparable": 1}
    v = report["node_verdicts"]["ud2d4-g8f6-g1f3"]
    assert v["transposition_of"] == ["g1f3", "g8f6", "d2d4"] and v["verdict"] == "unverified"     # annotee, pas fusionnee


def test_horizon_counts_restituted_plies_only():
    report = build_report(root_fen=START, attempt=attempt([("e2e4",), ("e2e4", "e7e5"), ("e2e4", "e7e5", "g1f3"),
                                                            ("d2d4",)]),
                          reference=ref({(): ROOT_LINES}), tree_state="complete")
    assert report["dimensions"]["horizon"] == {"lines": 2, "max_plies": 3, "median_plies": 2}

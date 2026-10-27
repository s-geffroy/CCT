"""Lot 4, DoD : le corpus annote donne les diagnostics attendus, et
l'abstention quand la reference est insuffisante.

Chaque cas suit le parcours complet de l'API : seance, coups du joueur,
soumission, arbre de reference, revelation, debriefing. Le moteur est le vrai,
a profondeur reduite (racine 14, noeuds 12 ; « shallow » : 8).
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings
from conftest import STOCKFISH, requires_engine

CORPUS = json.loads((Path(__file__).parent / "corpus" / "positions.json").read_text(encoding="utf-8"))
CASES = CORPUS["cases"]
ENGINE_PROFILES = {
    "standard": {"reference_depth": 14, "tree_node_depth": 12},
    "shallow": {"reference_depth": 8, "tree_node_depth": 8},
}


def test_corpus_is_large_enough_and_every_fixture_is_legal():
    assert CORPUS["corpus_version"] >= 1 and len(CASES) >= 20
    assert len({c["id"] for c in CASES}) == len(CASES)
    assert {cid for ids in CORPUS["distribution"].values() for cid in ids} == {c["id"] for c in CASES}
    for case in CASES:
        board = chess.Board(case["fen"])
        assert board.is_valid(), case["id"]
        for path in case.get("moves", []):
            b = board.copy()
            for uci in path:
                assert chess.Move.from_uci(uci) in b.legal_moves, (case["id"], path)
                b.push_uci(uci)


@pytest.fixture(scope="module")
def clients(tmp_path_factory):
    if not Path(STOCKFISH).is_file():
        pytest.skip("Stockfish absent")
    out = {}
    with_clients = []
    for name, profile in ENGINE_PROFILES.items():
        root = tmp_path_factory.mktemp(name)
        (root / "static").mkdir()
        (root / "static" / "index.html").write_text("<!doctype html><title>cct</title>")
        (root / "data").mkdir()
        s = replace(get_settings(), data_dir=root / "data", static_dir=root / "static",
                    allowed_hosts=["testserver"], engine_enabled=True, engine_threads=1, engine_hash_mb=16,
                    reference_budget_s=60, tree_budget_s=60, tree_max_nodes=20, tree_node_budget_s=10,
                    tree_auto_max_ply=2, **profile)
        client = TestClient(create_app(s))
        client.__enter__()
        out[name] = client
        with_clients.append(client)
    yield out
    for client in with_clients:
        client.__exit__(None, None, None)


def _run(client: TestClient, case: dict) -> tuple[dict, dict[str, str]]:
    position = client.post("/api/v1/positions", json={"source": "fen", "fen": case["fen"]}).json()
    s = client.post("/api/v1/sessions", json={"position_id": position["id"],
                                             "mode": case.get("mode", "tree")}).json()
    revealed = False
    try:
        ids: dict[tuple[str, ...], str] = {}
        for path in sorted((tuple(p) for p in case.get("moves", [])), key=len):
            r = client.post(f"/api/v1/sessions/{s['id']}/nodes", json={
                "move": path[-1], "parent_node_id": ids.get(path[:-1]), "expected_revision": s["revision"]})
            assert r.status_code == 201, r.text
            ids[path] = r.json()["node"]["id"]
            s = r.json()["session"]
        if case.get("lines_text"):
            s = client.put(f"/api/v1/sessions/{s['id']}/notes",
                           json={"lines_text": case["lines_text"], "expected_revision": s["revision"]}).json()
        s = client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]}).json()
        if "preparation" in s:
            deadline = time.monotonic() + 180
            while client.get(f"/api/v1/sessions/{s['id']}").json()["preparation"]["tree_progress_category"] == "running":
                assert time.monotonic() < deadline, f"{case['id']} : arbre non termine"
                time.sleep(0.3)
        s = client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
        revealed = True
        review = client.get(f"/api/v1/sessions/{s['id']}/review").json()
        return review, {" ".join(path): node_id for path, node_id in ids.items()}
    finally:
        if not revealed:  # ne pas laisser une seance ouverte masquer les cas suivants
            current = client.get(f"/api/v1/sessions/{s['id']}").json()
            if current["state"] == "active":
                client.post(f"/api/v1/sessions/{s['id']}/abandon", json={"expected_revision": current["revision"]})


@requires_engine
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_corpus_case(clients, case):
    review, ids = _run(clients[case.get("engine", "standard")], case)
    expect = case["expect"]
    categories = [d["category"] for d in review["diagnostics"]]
    summary = [(d["category"], d["explanation"]) for d in review["diagnostics"]]
    print(f"\n[{case['id']}] {review['quality']}", *(f"  - {c} : {e}" for c, e in summary), sep="\n")
    assert review["status"] == "available"
    assert review["quality"] == expect["quality"], (review["quality_notes"], summary)
    for category in expect.get("present", []):
        assert category in categories, (category, summary)
    if expect.get("present_any"):
        assert set(expect["present_any"]) & set(categories), summary
    for category in expect.get("absent", []):
        assert category not in categories, (category, summary)
    for path, verdict in expect.get("verdicts", {}).items():
        assert review["node_verdicts"][ids[path]]["verdict"] == verdict, (path, review["node_verdicts"][ids[path]], summary)
    for path in expect.get("determined", []):
        assert review["node_verdicts"][ids[path]]["verdict"] != "unverified", (path, review["node_verdicts"][ids[path]])
    for category, needle in expect.get("evidence", {}).items():
        evidence = [json.dumps(d["evidence"], ensure_ascii=False) for d in review["diagnostics"] if d["category"] == category]
        assert any(needle in e for e in evidence), (category, needle, evidence)
    # Toute affirmation de refutation se justifie par une suite legale montrable (P11).
    for d in review["diagnostics"]:
        if d["category"] == "tactical_refutation":
            board = chess.Board(d["evidence"]["turning_point_fen"])
            assert d["evidence"]["refutation_pv_uci"] and board.is_valid()

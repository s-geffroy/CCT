"""Lot 4 : arbre de reference ramifie et debriefing, avec le vrai moteur
(profondeurs faibles, plafonds reduits)."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_engine
from spoiler import leaks

pytestmark = requires_engine

BLUNDER_FEN = "rnbqkbnr/ppp2ppp/8/3pp3/4P3/5Q2/PPPP1PPP/RNB1KBNR w KQkq - 0 3"


@pytest.fixture
def tree_client(settings):
    s = replace(settings, engine_enabled=True, engine_threads=1, engine_hash_mb=16, reference_depth=12,
                reference_budget_s=60, tree_budget_s=60, tree_max_nodes=12, tree_node_depth=12,
                tree_node_budget_s=10, tree_auto_max_ply=2)
    with TestClient(create_app(s)) as c:
        yield c


def _position(client, fen):
    return client.post("/api/v1/positions", json={"source": "fen", "fen": fen}).json()


def _wait(predicate, timeout=120.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.2)
    raise AssertionError(f"delai depasse : {what}")


def _tree_done(client, tree_id):
    view = client.get(f"/api/v1/reference-trees/{tree_id}").json()
    return view if view.get("state") not in (None, "building") else None


def _db(client):
    return sqlite3.connect(client.app.state.settings.data_dir / "app.sqlite")


def test_session_tree_is_hidden_then_branches_and_review_after_reveal(tree_client):
    c = tree_client
    recorded = []

    def rec(r):
        if r.headers.get("content-type", "").startswith("application/json"):
            recorded.append((r.request.url.path, r.json()))
        return r

    position = _position(c, BLUNDER_FEN)
    s = rec(c.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "tree"})).json()
    with _db(c) as conn:
        tree_id = conn.execute("SELECT reference_tree_id FROM sessions WHERE id = ?", (s["id"],)).fetchone()[0]
    assert tree_id
    for move, parent in (("Qxf7+", None), ("exd5", None)):
        s = rec(c.post(f"/api/v1/sessions/{s['id']}/nodes",
                       json={"move": move, "parent_node_id": parent, "expected_revision": s["revision"]})).json()["session"]
    exd5 = next(n for n in s["tree"]["nodes"].values() if n["move_san"] == "exd5")
    s = rec(c.post(f"/api/v1/sessions/{s['id']}/nodes",
                   json={"move": "Qxd5", "parent_node_id": exd5["id"], "expected_revision": s["revision"]})).json()["session"]

    # Client hostile : l'arbre, sa reanalyse et le debriefing avant revelation.
    hidden = rec(c.get(f"/api/v1/reference-trees/{tree_id}")).json()
    assert hidden["visibility"] == "hidden"
    r = rec(c.post(f"/api/v1/reference-trees/{tree_id}/expand", json={"path_uci": []}))
    assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_IN_PROGRESS"
    r = rec(c.get(f"/api/v1/sessions/{s['id']}/review"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_NOT_AVAILABLE"
    r = rec(c.post("/api/v1/reference-trees", json={"position_id": position["id"], "target_depth": 8}))
    assert r.status_code == 409

    s = rec(c.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]})).json()
    _wait(lambda: rec(c.get(f"/api/v1/sessions/{s['id']}")).json()["preparation"]["tree_is_ready"],
          what="arbre de la seance")
    rec(c.get(f"/api/v1/reference-trees/{tree_id}"))
    for path, body in recorded:
        assert leaks(body) == [], f"fuite dans {path} : {leaks(body)}"

    s = c.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
    tree = s["reference_tree"]
    assert tree["visibility"] == "full" and tree["coverage"] == "selective"
    by_path = {" ".join(n["path_uci"]): n for n in tree["nodes"]}
    # Les branches du joueur sont analysees, et distinguees de la preselection.
    for path in ("f3f7", "e4d5", "e4d5 d8d5"):
        assert by_path[path]["selection_reason"] in ("user_branch", "top_rank", "opponent_best_defense",
                                                     "opponent_alternative")
        assert by_path[path]["status"] in ("depth_met", "budget_exhausted", "incomplete")
    assert by_path["f3f7"]["selection_reason"] == "user_branch"
    # Deux enveloppes : la preparation automatique et la verification des branches du joueur.
    assert sum(1 for n in tree["nodes"] if n["selection_reason"] != "user_branch") <= 12
    assert by_path[""]["selection_reason"] == "root"

    review = c.get(f"/api/v1/sessions/{s['id']}/review").json()
    assert review["status"] == "available" and review["quality"] == "final" and review["stored"]
    refutation = next(d for d in review["diagnostics"] if d["category"] == "tactical_refutation")
    assert "Kxf7" in refutation["evidence"]["refutation_pv_san"]
    assert review["node_verdicts"][next(n["id"] for n in s["attempt"]["tree"].values()
                                        if n["move_uci"] == "f3f7")]["verdict"] == "refuted"
    assert c.get(f"/api/v1/sessions/{s['id']}").json()["state"] == "reviewed"
    again = c.get(f"/api/v1/sessions/{s['id']}/review").json()
    assert again["review_id"] == review["review_id"] and again["stored"]
    with _db(c) as conn:
        stored = conn.execute("SELECT COUNT(*) FROM review_diagnostics WHERE review_id = ?",
                              (review["review_id"],)).fetchone()[0]
    assert stored == len(review["diagnostics"])
    export = c.get(f"/api/v1/sessions/{s['id']}/export").json()
    assert export["review"]["quality"] == "final"
    item = next(i for i in c.get("/api/v1/history").json()["items"] if i["id"] == s["id"])
    assert item["review_quality"] == "final" and item["state"] == "reviewed"

    # Une nouvelle seance sur le meme echiquier masque de nouveau tout, y compris
    # le debriefing et l'export de la seance deja revelee.
    other = c.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "mental"}).json()
    for body in (c.get(f"/api/v1/sessions/{s['id']}/review").json(), c.get(f"/api/v1/reference-trees/{tree_id}").json()):
        assert leaks(body) == [], leaks(body)
    for view in (c.get(f"/api/v1/sessions/{s['id']}").json(), c.get(f"/api/v1/sessions/{s['id']}/export").json()["session"]):
        assert view["reference"]["job"]["visibility"] == view["reference_tree"]["visibility"] == "hidden"
        assert leaks(view["reference"]["job"]) == leaks(view["reference_tree"]) == []
    assert c.get(f"/api/v1/sessions/{s['id']}/export").json()["review"] == {"status": "hidden"}
    c.post(f"/api/v1/sessions/{other['id']}/abandon", json={"expected_revision": other["revision"]})


def test_study_tree_respects_node_limit_and_is_reused(tree_client):
    c = tree_client
    position = _position(c, BLUNDER_FEN)
    params = {"position_id": position["id"], "target_depth": 10, "multipv_max": 5, "max_nodes": 4, "node_depth": 10}
    r = c.post("/api/v1/reference-trees", json=params)
    assert r.status_code == 201
    tree = _wait(lambda: _tree_done(c, r.json()["id"]), what="arbre d'etude")
    assert tree["state"] == "node_limit" and tree["pruned_count"] > 0
    assert len(tree["nodes"]) == 4 and len(tree["nodes"][0]["lines"]) == 5
    assert {n["selection_reason"] for n in tree["nodes"][1:]} <= {"top_rank", "opponent_best_defense",
                                                                    "opponent_alternative"}
    assert all(n["status"] == "depth_met" for n in tree["nodes"])
    again = c.post("/api/v1/reference-trees", json=params)
    assert again.status_code == 200 and again.json()["id"] == tree["id"] and again.json()["reused"]
    listed = c.get("/api/v1/reference-trees", params={"position_id": position["id"]}).json()["items"]
    assert [t["id"] for t in listed] == [tree["id"]]


def test_study_tree_stops_on_its_time_budget(tree_client):
    c = tree_client
    position = _position(c, BLUNDER_FEN)
    r = c.post("/api/v1/reference-trees", json={"position_id": position["id"], "target_depth": 8, "multipv_max": 3,
                                                "tree_budget_s": 10, "node_depth": 32})
    tree = _wait(lambda: _tree_done(c, r.json()["id"]), timeout=60, what="budget de l'arbre")
    assert tree["state"] == "budget_exhausted" and tree["pruned_count"] > 0
    assert tree["spent_s"]["auto"] <= 10 + 1 and tree["spent_s"]["user"] == 0
    assert [n["status"] for n in tree["nodes"][1:]] == ["budget_exhausted"]


def test_expand_reanalyses_deeper_or_adds_a_move(tree_client):
    c = tree_client
    position = _position(c, BLUNDER_FEN)
    r = c.post("/api/v1/reference-trees", json={"position_id": position["id"], "target_depth": 10, "multipv_max": 3,
                                                "max_nodes": 2, "node_depth": 10})
    tree = _wait(lambda: _tree_done(c, r.json()["id"]), what="arbre")
    child = tree["nodes"][1]
    deeper = c.post(f"/api/v1/reference-trees/{tree['id']}/expand", json={"path_uci": child["path_uci"]})
    assert deeper.status_code == 200
    node = next(n for n in deeper.json()["nodes"] if n["id"] == child["id"])
    assert node["reanalysed"] and node["selection_reason"] == child["selection_reason"]
    assert node["lines"]  # l'analyse precedente reste lisible pendant la nouvelle
    tree = _wait(lambda: _tree_done(c, tree["id"]), what="reanalyse")
    node = next(n for n in tree["nodes"] if n["id"] == child["id"])
    assert node["status"] == "depth_met" and node["target_depth"] == 14

    added = c.post(f"/api/v1/reference-trees/{tree['id']}/expand", json={"path_uci": ["h2h4"]}).json()
    assert any(n["path_uci"] == ["h2h4"] and n["selection_reason"] == "user_requested_reanalysis"
               for n in added["nodes"])
    r = c.post(f"/api/v1/reference-trees/{tree['id']}/expand", json={"path_uci": ["e1e3"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ILLEGAL_PATH"
    r = c.post(f"/api/v1/reference-trees/{tree['id']}/expand", json={"path_uci": ["a2a3", "a7a6"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PARENT_NOT_IN_TREE"


def test_interrupted_analysis_is_restarted_once(tree_client):
    c = tree_client
    position = _position(c, BLUNDER_FEN)
    r = c.post("/api/v1/reference-trees", json={"position_id": position["id"], "target_depth": 8, "multipv_max": 2,
                                                "max_nodes": 1})
    tree = _wait(lambda: _tree_done(c, r.json()["id"]), what="arbre")
    old_job = tree["nodes"][0]["job_id"]
    with _db(c) as conn:  # simule un arret du serveur pendant le calcul
        conn.execute("UPDATE analysis_jobs SET state = 'interrupted' WHERE id = ?", (old_job,))
        conn.execute("UPDATE reference_trees SET state = 'building' WHERE id = ?", (tree["id"],))
    c.app.state.reference.advance(tree["id"])
    tree = _wait(lambda: _tree_done(c, tree["id"]), what="relance")
    root = tree["nodes"][0]
    assert root["job_id"] != old_job and root["status"] == "depth_met" and tree["state"] in ("complete", "node_limit")
    with _db(c) as conn:
        assert conn.execute("SELECT previous_job_id FROM reference_nodes WHERE id = ?",
                            (root["id"],)).fetchone()[0] == old_job
    assert json.loads(json.dumps(tree))  # vue serialisable

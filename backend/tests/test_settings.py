"""Lot 5 : reglages bornes (GET/PUT /api/v1/settings)."""
from __future__ import annotations

import sqlite3
import time

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_engine


def test_settings_describe_bounds_and_defaults(client):
    body = client.get("/api/v1/settings").json()
    fields = {f["key"]: f for f in body["fields"]}
    assert fields["study_depth"] == {"key": "study_depth", "group": "etude", "label": "Profondeur cible (etude libre)",
                                     "default": 21, "minimum": 8, "maximum": 32, "unit": None}
    assert fields["score_perspective"]["choices"] == ["white", "side_to_move"]
    assert fields["engine_threads"]["minimum"] == 1 and fields["engine_threads"]["maximum"] >= 1
    assert body["values"]["study_depth"] == 21 and body["values"]["score_perspective"] == "white"


def test_settings_are_validated_and_persisted(settings):
    with TestClient(create_app(settings)) as c:
        r = c.put("/api/v1/settings", json={"study_depth": 33})
        assert r.status_code == 422 and r.json()["error"]["code"] == "SETTING_OUT_OF_RANGE"
        assert r.json()["error"]["details"] == {"key": "study_depth", "minimum": 8, "maximum": 32}
        assert c.put("/api/v1/settings", json={"nope": 1}).json()["error"]["code"] == "SETTING_UNKNOWN"
        assert c.put("/api/v1/settings", json={"study_depth": "12"}).json()["error"]["code"] == "SETTING_INVALID"
        assert c.put("/api/v1/settings", json={"study_depth": True}).status_code == 422
        assert c.put("/api/v1/settings", json={"score_perspective": "black"}).status_code == 422
        r = c.put("/api/v1/settings", json={"study_depth": 18, "score_perspective": "side_to_move"},
                  headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        r = c.put("/api/v1/settings", json={"study_depth": 18, "score_perspective": "side_to_move"})
        assert r.status_code == 200 and r.json()["values"]["study_depth"] == 18
        assert c.get("/api/v1/meta").json()["capabilities"]["target_depth_default"] == 18
    with TestClient(create_app(settings)) as c:  # redemarrage : les reglages sont relus
        values = c.get("/api/v1/settings").json()["values"]
        assert values["study_depth"] == 18 and values["score_perspective"] == "side_to_move"
        values = c.put("/api/v1/settings", json={"reset": True}).json()["values"]
        assert values["study_depth"] == 21 and values["score_perspective"] == "white"


def test_invalid_stored_value_falls_back_to_default(settings):
    with TestClient(create_app(settings)):
        pass
    conn = sqlite3.connect(settings.data_dir / "app.sqlite")
    conn.execute("INSERT INTO settings VALUES ('study_depth', '99', 'x'), ('tree_max_nodes', 'oops', 'x')")
    conn.commit()
    conn.close()
    with TestClient(create_app(settings)) as c:
        values = c.get("/api/v1/settings").json()["values"]
        assert values["study_depth"] == 21 and values["tree_max_nodes"] == settings.tree_max_nodes


@requires_engine
def test_engine_settings_apply_without_restart_and_drive_new_references(engine_client):
    c = engine_client
    r = c.put("/api/v1/settings", json={"engine_hash_mb": 32, "reference_depth": 9, "tree_budget_s": 0})
    assert r.status_code == 200
    deadline = time.monotonic() + 10
    while c.get("/api/v1/settings").json()["engine"]["applied"] != {"threads": 1, "hash_mb": 32}:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert c.get("/api/v1/settings").json()["engine"]["pending"] is None
    assert c.get("/api/v1/meta").json()["engine"]["hash_mb"] == 32
    position = c.post("/api/v1/positions", json={"source": "fen", "fen": "8/8/8/8/8/4k3/8/4K2R w K - 0 1"}).json()
    s = c.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "tree", "start": True}).json()
    with sqlite3.connect(c.app.state.settings.data_dir / "app.sqlite") as conn:
        depth = conn.execute("SELECT json_extract(settings_json, '$.target_depth'), json_extract(settings_json,"
                             " '$.engine.hash_mb') FROM analysis_jobs WHERE id = (SELECT reference_job_id FROM sessions"
                             " WHERE id = ?)", (s["id"],)).fetchone()
        tree = conn.execute("SELECT json_extract(settings_json, '$.budget_s') FROM reference_trees WHERE session_id = ?",
                            (s["id"],)).fetchone()
    assert depth == (9, 32) and tree == (0,)
    c.post(f"/api/v1/sessions/{s['id']}/abandon", json={"expected_revision": s["revision"]})

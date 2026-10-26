"""Lot 3 : orchestrateur Stockfish (vrai moteur, profondeurs faibles).

T07-T12 du doc 11 et anti-spoiler P01/P02 avec analyses reelles.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import time
from dataclasses import replace

import chess
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_engine
from spoiler import leaks
from test_domain import USER_FEN

pytestmark = requires_engine
FEW_MOVES = "8/8/8/8/8/4k3/8/4K2R w K - 0 1"
FINAL = {"complete_depth", "budget_exhausted", "incomplete", "cancelled", "failed", "interrupted", "terminal"}


def _position(client, fen=USER_FEN, source="fen"):
    return client.post("/api/v1/positions", json={"source": source, "fen": fen}).json()


def _job(client, position_id, **params):
    r = client.post("/api/v1/analysis-jobs", json={"position_id": position_id, **params})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _wait(client, job_id, until, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = client.get(f"/api/v1/analysis-jobs/{job_id}").json()
        if until(view):
            return view
        time.sleep(0.1)
    summary = {k: view.get(k) for k in ("state", "visibility", "progress_category", "error", "stages_reached_s")}
    raise AssertionError(f"delai depasse : {summary}")


def _done(view):
    return view.get("state") in FINAL or view.get("is_ready") or view.get("progress_category") == "stopped"


def test_study_job_runs_to_target_depth(engine_client):
    position = _position(engine_client)
    job = _job(engine_client, position["id"], target_depth=8, multipv_max=20, budget_s=60)
    assert job["visibility"] == "full" and job["state"] in ("queued", "running")
    view = _wait(engine_client, job["id"], _done)
    legal = chess.Board(USER_FEN).legal_moves.count()
    assert view["state"] == "complete_depth" and view["target_depth_met"]
    assert view["multipv"] == min(20, legal) == len(view["lines"])                      # T08
    assert view["root_coverage"] == "top_moves_only"                                    # jamais « exhaustif »
    roots = [line["root_move_uci"] for line in view["lines"]]
    assert len(set(roots)) == len(roots)
    assert [line["rank"] for line in view["lines"]] == list(range(1, len(roots) + 1))
    first = view["lines"][0]
    assert first["status"] == "depth_met" and first["exact_depth"] >= 8
    assert first["pv_san"][0] == chess.Board(USER_FEN).san(chess.Move.from_uci(first["root_move_uci"]))
    assert first["score"]["perspective"] == "white" and first["score"]["kind"] in ("cp", "mate")
    assert "8" in {str(k) for k in view["stages_reached_s"]}


def test_fewer_than_20_moves_covers_all_root_moves(engine_client):
    position = _position(engine_client, FEW_MOVES)
    view = _wait(engine_client, _job(engine_client, position["id"], target_depth=8)["id"], _done)
    legal = chess.Board(FEW_MOVES).legal_moves.count()
    assert view["multipv"] == legal == len(view["lines"]) and view["root_coverage"] == "all_root_moves"   # T07


def test_duplicate_requests_are_deduplicated_and_results_cached(engine_client):
    position = _position(engine_client)
    a = _job(engine_client, position["id"], target_depth=10)
    b = _job(engine_client, position["id"], target_depth=10)
    assert a["id"] == b["id"] and b["reused"]
    _wait(engine_client, a["id"], _done)
    r = engine_client.post("/api/v1/analysis-jobs", json={"position_id": position["id"], "target_depth": 10})
    assert r.status_code == 200 and r.json()["id"] == a["id"] and r.json()["reused"]
    other = _job(engine_client, position["id"], target_depth=9)                           # autres reglages
    assert other["id"] != a["id"]


def test_cancel_stops_the_engine_and_a_new_job_can_run(engine_client):
    position = _position(engine_client)
    long_job = _job(engine_client, position["id"], target_depth=32, budget_s=600)
    _wait(engine_client, long_job["id"], lambda v: v["state"] == "running")
    t0 = time.monotonic()
    cancelled = engine_client.post(f"/api/v1/analysis-jobs/{long_job['id']}/cancel").json()
    assert cancelled["cancel_requested"]
    view = _wait(engine_client, long_job["id"], _done, timeout=10)
    assert view["state"] == "cancelled" and time.monotonic() - t0 < 5                   # T10
    assert not view["target_depth_met"]
    again = engine_client.post(f"/api/v1/analysis-jobs/{long_job['id']}/cancel")         # idempotent
    assert again.status_code == 200 and again.json()["state"] == "cancelled"
    nxt = _wait(engine_client, _job(engine_client, position["id"], target_depth=8)["id"], _done)
    assert nxt["state"] == "complete_depth"


def test_budget_never_claims_the_target_depth(engine_client):
    position = _position(engine_client)
    view = _wait(engine_client, _job(engine_client, position["id"], target_depth=30, budget_s=5)["id"], _done, timeout=20)
    assert view["state"] == "budget_exhausted" and not view["target_depth_met"]           # T09
    assert all(line["status"] != "depth_met" for line in view["lines"] if line["exact_depth"] < 30)


def test_terminal_position_is_not_sent_to_the_engine(engine_client):
    position = _position(engine_client, "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    r = engine_client.post("/api/v1/analysis-jobs", json={"position_id": position["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TERMINAL_POSITION"


def test_engine_crash_marks_job_failed_and_engine_restarts(engine_client):
    position = _position(engine_client)
    job = _job(engine_client, position["id"], target_depth=32, budget_s=600)
    _wait(engine_client, job["id"], lambda v: v["state"] == "running")
    manager = engine_client.app.state.engine
    os.kill(manager.engine.transport.get_pid(), signal.SIGKILL)                          # T12
    view = _wait(engine_client, job["id"], _done, timeout=15)
    assert view["state"] == "failed" and "moteur" in view["error"]
    nxt = _wait(engine_client, _job(engine_client, position["id"], target_depth=8)["id"], _done, timeout=30)
    assert nxt["state"] == "complete_depth"
    assert engine_client.get("/api/v1/health/ready").status_code == 200


def test_running_jobs_become_interrupted_after_restart(settings):
    s = replace(settings, engine_enabled=True, engine_threads=1, engine_hash_mb=16)
    with TestClient(create_app(s)) as first:
        position = _position(first)
    conn = sqlite3.connect(s.data_dir / "app.sqlite")
    conn.execute(
        "INSERT INTO analysis_jobs (id, position_id, purpose, scope, priority, state, settings_json, cache_key, created_at)"
        " VALUES ('11111111-1111-1111-1111-111111111111', ?, 'study', 'root', 1, 'running', ?, 'k', '2026-01-01')",
        (position["id"], json.dumps({"target_depth": 8, "multipv_max": 1, "budget_s": 5})))
    conn.commit()
    conn.close()
    with TestClient(create_app(s)) as second:
        view = second.get("/api/v1/analysis-jobs/11111111-1111-1111-1111-111111111111").json()
        assert view["state"] == "interrupted"


def test_queue_is_bounded(settings):
    s = replace(settings, engine_enabled=True, engine_threads=1, engine_hash_mb=16, max_queued_jobs=1)
    with TestClient(create_app(s)) as client:
        position = _position(client)
        busy = _job(client, position["id"], target_depth=32, budget_s=600)
        _wait(client, busy["id"], lambda v: v["state"] == "running")
        _job(client, position["id"], target_depth=9)
        r = client.post("/api/v1/analysis-jobs", json={"position_id": position["id"], "target_depth": 10})
        assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_JOBS"
        client.post(f"/api/v1/analysis-jobs/{busy['id']}/cancel")


def test_sse_streams_provisional_then_final_snapshots(engine_client):
    position = _position(engine_client)
    job = _job(engine_client, position["id"], target_depth=14, budget_s=60)
    events = []
    with engine_client.stream("GET", f"/api/v1/analysis-jobs/{job['id']}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name == "analysis-snapshot":
                events.append(json.loads(line[6:]))
    assert events and events[-1]["state"] == "complete_depth"
    assert any(e["state"] == "running" and e["lines"] for e in events[:-1])              # resultats provisoires
    assert all(e["id"] == job["id"] for e in events)                                     # T11 : jamais d'autre travail


# ------------------------------------------------------------ anti-spoiler

def test_session_reference_is_hidden_until_reveal(engine_client):
    recorded = []

    def rec(r):
        if r.headers.get("content-type", "").startswith("application/json"):
            recorded.append((r.request.url.path, r.json()))
        return r

    position = _position(engine_client)
    s = rec(engine_client.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "tree"})).json()
    job_id = s["preparation"]["job_id"]
    # Le travail progresse en arriere-plan ; le client hostile insiste.
    deadline = time.monotonic() + 90
    while not rec(engine_client.get(f"/api/v1/sessions/{s['id']}")).json()["preparation"]["is_ready"]:
        rec(engine_client.get(f"/api/v1/analysis-jobs/{job_id}"))
        assert time.monotonic() < deadline
        time.sleep(0.3)
    rec(engine_client.get(f"/api/v1/analysis-jobs/{job_id}"))
    rec(engine_client.get("/api/v1/analysis-jobs", params={"position_id": position["id"]}))
    rec(engine_client.post(f"/api/v1/analysis-jobs/{job_id}/cancel"))
    # Contournements : meme position, meme echiquier via un autre instantane (editeur).
    for pid in (position["id"], _position(engine_client, USER_FEN, source="editor")["id"]):
        r = rec(engine_client.post("/api/v1/analysis-jobs", json={"position_id": pid, "target_depth": 8}))
        assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_IN_PROGRESS"
    # Flux SSE avant revelation : l'etat seul.
    # max_seconds : le TestClient attend la fin du flux (il ne diffuse pas reellement).
    with engine_client.stream("GET", f"/api/v1/analysis-jobs/{job_id}/events", params={"max_seconds": 1}) as r:
        for line in r.iter_lines():
            if line.startswith("event: "):
                assert line == "event: analysis-status"
            if line.startswith("data: "):
                recorded.append(("sse", json.loads(line[6:])))
                break
    s = rec(engine_client.post(f"/api/v1/sessions/{s['id']}/nodes", json={"move": "e4", "expected_revision": s["revision"]})).json()["session"]
    s = rec(engine_client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]})).json()

    assert len(recorded) > 8
    for path, body in recorded:
        assert leaks(body) == [], f"fuite dans {path} : {leaks(body)}"

    revealed = engine_client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
    reference = revealed["reference"]
    assert reference["status"] == "available" and reference["job"]["visibility"] == "full"
    assert reference["job"]["lines"] and reference["job"]["state"] == "complete_depth"


def test_existing_study_results_are_hidden_once_a_session_starts(engine_client):
    position = _position(engine_client)
    study = _wait(engine_client, _job(engine_client, position["id"], target_depth=8)["id"], _done)
    assert study["visibility"] == "full" and study["lines"]
    s = engine_client.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "mental"}).json()
    hidden = engine_client.get(f"/api/v1/analysis-jobs/{study['id']}").json()
    assert hidden["visibility"] == "hidden" and leaks(hidden) == []
    engine_client.post(f"/api/v1/sessions/{s['id']}/abandon", json={"expected_revision": s["revision"]})
    assert engine_client.get(f"/api/v1/analysis-jobs/{study['id']}").json()["visibility"] == "full"


def test_engine_disabled_keeps_sessions_usable(client):
    position = _position(client)
    r = client.post("/api/v1/analysis-jobs", json={"position_id": position["id"]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ENGINE_UNAVAILABLE"
    s = client.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "tree"}).json()
    assert "preparation" not in s
    s = client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]}).json()
    s = client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
    assert s["reference"]["status"] == "not_available"

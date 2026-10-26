"""Lot 2 : seances B (mental) et C (arbre), sans moteur, sans fuite."""
from __future__ import annotations

import sqlite3

import chess
import pytest

from spoiler import leaks
from test_domain import USER_FEN


def _position(client, fen=chess.STARTING_FEN):
    return client.post("/api/v1/positions", json={"source": "fen", "fen": fen}).json()


def _session(client, mode="tree", fen=chess.STARTING_FEN, **extra):
    r = client.post("/api/v1/sessions", json={"position_id": _position(client, fen)["id"], "mode": mode, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _add(client, s, move, parent=None, expect=201):
    r = client.post(f"/api/v1/sessions/{s['id']}/nodes",
                    json={"parent_node_id": parent, "move": move, "expected_revision": s["revision"]})
    assert r.status_code == expect, r.text
    return r.json()


def _sans(view):
    return sorted(n["move_san"] for n in view["tree"]["nodes"].values())


# --------------------------------------------------------- mode C : arbre

def test_tree_mode_builds_branches_from_a_legal_parent(client):
    s = _session(client)
    assert s["state"] == "active" and s["revision"] == 1 and not s["can_undo"]
    e4 = _add(client, s, "e4")
    s = e4["session"]
    # SAN calcule par le serveur, meme si le client envoie de l'UCI.
    assert e4["node"]["move_san"] == "e4" and e4["node"]["move_uci"] == "e2e4"
    s = _add(client, s, "d2d4")["session"]                       # alternative depuis la racine (P03)
    s = _add(client, s, "e5", parent=e4["node"]["id"])["session"]
    s = _add(client, s, "c5", parent=e4["node"]["id"])["session"]
    assert _sans(s) == ["c5", "d4", "e4", "e5"]
    roots = [n for n in s["tree"]["nodes"].values() if n["parent_id"] is None]
    assert sorted((n["move_san"], n["order_index"]) for n in roots) == [("d4", 1), ("e4", 0)]
    assert s["revision"] == 5 and s["can_undo"]


def test_illegal_move_is_refused_and_tree_is_intact(client):
    s = _session(client)
    s = _add(client, s, "e4")["session"]
    r = client.post(f"/api/v1/sessions/{s['id']}/nodes", json={"move": "e2e5", "expected_revision": s["revision"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ILLEGAL_MOVE"           # P05
    assert client.get(f"/api/v1/sessions/{s['id']}").json()["revision"] == s["revision"]
    assert _add(client, s, "e4", expect=409)["error"]["code"] == "DUPLICATE_MOVE"


def test_stale_revision_is_a_conflict(client):
    s = _session(client)
    _add(client, s, "e4")
    # Meme revision : deuxieme onglet ou double clic.
    r = client.post(f"/api/v1/sessions/{s['id']}/nodes", json={"move": "d4", "expected_revision": s["revision"]})
    assert r.status_code == 409 and r.json()["error"]["details"]["current_revision"] == 2


def test_undo_redo_and_redo_branch_is_dropped_on_new_edit(client):
    s = _session(client)
    s = _add(client, s, "e4")["session"]
    s = _add(client, s, "d4")["session"]
    s = client.post(f"/api/v1/sessions/{s['id']}/undo", json={"expected_revision": s["revision"]}).json()
    assert _sans(s) == ["e4"] and s["can_redo"]
    s = client.post(f"/api/v1/sessions/{s['id']}/redo", json={"expected_revision": s["revision"]}).json()
    assert _sans(s) == ["d4", "e4"]
    s = client.post(f"/api/v1/sessions/{s['id']}/undo", json={"expected_revision": s["revision"]}).json()
    s = _add(client, s, "c4")["session"]
    assert _sans(s) == ["c4", "e4"] and not s["can_redo"]
    r = client.post(f"/api/v1/sessions/{s['id']}/redo", json={"expected_revision": s["revision"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOTHING_TO_REDO"


def test_delete_subtree_comment_assessment_and_promote(client):
    s = _session(client)
    e4 = _add(client, s, "e4")
    s = _add(client, e4["session"], "d4")["session"]
    d4 = next(n for n in s["tree"]["nodes"].values() if n["move_san"] == "d4")
    s = _add(client, s, "e5", parent=e4["node"]["id"])["session"]
    s = client.patch(f"/api/v1/sessions/{s['id']}/nodes/{d4['id']}",
                     json={"expected_revision": s["revision"], "comment": "plus solide", "human_assessment": "equal",
                           "promote": True}).json()
    d4 = s["tree"]["nodes"][d4["id"]]
    assert d4["order_index"] == 0 and d4["comment"] == "plus solide" and d4["human_assessment"] == "equal"
    s = client.delete(f"/api/v1/sessions/{s['id']}/nodes/{e4['node']['id']}",
                      params={"expected_revision": s["revision"]}).json()
    assert _sans(s) == ["d4"]                                    # e4 et sa suite e5 supprimes


def test_submission_freezes_the_attempt(client):
    s = _session(client)
    s = _add(client, s, "e4")["session"]
    s = client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]}).json()
    assert s["state"] == "submitted" and s["attempt"]["tree"] and s["duration_ms"] >= 0
    assert not s["can_undo"]
    for r in (
        client.post(f"/api/v1/sessions/{s['id']}/nodes", json={"move": "d4", "expected_revision": s["revision"]}),
        client.post(f"/api/v1/sessions/{s['id']}/undo", json={"expected_revision": s["revision"]}),
        client.put(f"/api/v1/sessions/{s['id']}/notes", json={"expected_revision": s["revision"], "notes": "x"}),
        client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]}),
    ):
        assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_STATE"           # P06


def test_database_itself_refuses_changes_after_submission(client, settings):
    s = _session(client)
    s = _add(client, s, "e4")["session"]
    client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]})
    conn = sqlite3.connect(settings.data_dir / "app.sqlite")
    try:
        for sql in (
            "UPDATE attempt_snapshots SET snapshot_json = '{}'",
            "DELETE FROM attempt_snapshots",
            "DELETE FROM user_nodes",
            "UPDATE sessions SET notes = 'triche'",
            "UPDATE sessions SET state = 'active'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql)
    finally:
        conn.close()


def test_reveal_requires_submission_and_abandon_is_final(client):
    s = _session(client)
    r = client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]})
    assert r.status_code == 409
    s = client.post(f"/api/v1/sessions/{s['id']}/abandon", json={"expected_revision": s["revision"]}).json()
    assert s["state"] == "abandoned" and s["attempt"] is None
    r = client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]})
    assert r.status_code == 409


# ------------------------------------------------------- mode B : mental

def test_mental_mode_forbids_board_moves(client):
    s = _session(client, mode="mental")
    r = client.post(f"/api/v1/sessions/{s['id']}/nodes", json={"move": "e4", "expected_revision": s["revision"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MENTAL_MODE"


def test_mental_lines_are_not_judged_before_submission(client):
    s = _session(client, mode="mental", fen=USER_FEN)
    lines = "1. e4 dxe4 2. Nxe4\nNb5 a6? Ke3\n\n"
    s = client.put(f"/api/v1/sessions/{s['id']}/notes",
                   json={"expected_revision": s["revision"], "lines_text": lines, "notes": "je crains ...Nb4"}).json()
    # Aucune information de legalite pendant la seance.
    assert s["lines_text"] == lines and s["attempt"] is None
    assert "ILLEGAL" not in str(s) and "written_lines" not in str(s)

    s = client.post(f"/api/v1/sessions/{s['id']}/submit", json={
        "expected_revision": s["revision"],
        "self_assessment": {"candidates": "e4, Nb5", "main_threat": "...Nb4", "evaluation": "white_better"},
    }).json()
    written = s["attempt"]["written_lines"]
    assert written[0]["moves_san"] == ["e4", "dxe4", "Nxe4"] and written[0]["error"] is None
    # Deuxieme ligne : Nb5 a6 legaux, puis Ke3 illegal -> erreur localisee, rien d'invente.
    assert written[1]["moves_san"] == ["Nb5", "a6"]
    assert written[1]["error"]["ply"] == 3 and written[1]["error"]["token"] == "Ke3"
    assert sorted(n["move_san"] for n in s["attempt"]["tree"].values()) == ["Nb5", "Nxe4", "a6", "dxe4", "e4"]
    assert s["self_assessment"]["evaluation"] == "white_better" and not s["attempt"]["no_trace"]


def test_mental_session_without_any_trace(client):
    s = _session(client, mode="mental")
    s = client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]}).json()
    assert s["attempt"]["no_trace"] is True                     # P10 : rien a diagnostiquer
    s = client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
    assert s["state"] == "revealed"


def test_notes_can_be_disabled(client):
    s = _session(client, mode="mental", allow_text_notes=False)
    r = client.put(f"/api/v1/sessions/{s['id']}/notes", json={"expected_revision": s["revision"], "notes": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOTES_DISABLED"


# --------------------------------------------- anti-spoiler et persistance

def test_hostile_client_finds_no_engine_data_before_reveal(client):
    """Lit toutes les reponses d'une seance B et d'une seance C avant revelation (P01, P02)."""
    seen = []

    def record(r):
        if r.headers.get("content-type", "").startswith("application/json"):
            seen.append((r.request.method, r.request.url.path, r.json()))
        return r

    for mode in ("tree", "mental"):
        s = record(client.post("/api/v1/sessions", json={"position_id": _position(client, USER_FEN)["id"], "mode": mode})).json()
        if mode == "tree":
            s = record(client.post(f"/api/v1/sessions/{s['id']}/nodes",
                                   json={"move": "e4", "expected_revision": s["revision"]})).json()["session"]
        else:
            s = record(client.put(f"/api/v1/sessions/{s['id']}/notes",
                                  json={"expected_revision": s["revision"], "lines_text": "e4 dxe4"})).json()
        record(client.get(f"/api/v1/sessions/{s['id']}"))
        record(client.get(f"/api/v1/sessions/{s['id']}/export"))
        s = record(client.post(f"/api/v1/sessions/{s['id']}/submit", json={"expected_revision": s["revision"]})).json()
        record(client.get(f"/api/v1/sessions/{s['id']}"))
        record(client.get(f"/api/v1/positions/{s['position']['id']}"))
        record(client.get("/api/v1/history"))
        record(client.get("/api/v1/meta"))

    assert len(seen) >= 16
    for method, path, body in seen:
        assert leaks(body) == [], f"fuite dans {method} {path} : {leaks(body)}"

    # Apres revelation seulement, la section de reference apparait.
    revealed = client.post(f"/api/v1/sessions/{s['id']}/reveal", json={"expected_revision": s["revision"]}).json()
    assert "reference" in revealed


def test_every_analysis_route_is_covered_by_the_hostile_client_test(client):
    """Doc 08 : aucun point d'entree d'analyse non garde. Toute nouvelle route
    d'analyse doit etre ajoutee ici ET au test client hostile de test_analysis."""
    paths = client.get("/openapi.json").json()["paths"]
    analysis_paths = {p for p in paths if "analys" in p or "reference" in p or "expand" in p}
    assert analysis_paths == {
        "/api/v1/analysis-jobs",
        "/api/v1/analysis-jobs/{job_id}",
        "/api/v1/analysis-jobs/{job_id}/cancel",
        "/api/v1/analysis-jobs/{job_id}/events",
    }


def test_export_json_and_pgn(client):
    s = _session(client)
    e4 = _add(client, s, "e4")
    s = _add(client, e4["session"], "d4")["session"]
    s = _add(client, s, "e5", parent=e4["node"]["id"])["session"]
    data = client.get(f"/api/v1/sessions/{s['id']}/export").json()
    assert data["format"] == "cct-session" and data["format_version"] == 1
    r = client.get(f"/api/v1/sessions/{s['id']}/export", params={"format": "pgn"})
    assert r.headers["content-type"].startswith("application/x-chess-pgn")
    assert "1. e4 ( 1. d4 ) 1... e5" in r.text


def test_history_and_resume_after_restart(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app(settings)) as first:
        s = _session(first)
        s = _add(first, s, "e4")["session"]
    with TestClient(create_app(settings)) as second:
        resumed = second.get(f"/api/v1/sessions/{s['id']}").json()
        assert resumed["state"] == "active" and _sans(resumed) == ["e4"] and resumed["revision"] == s["revision"]
        items = second.get("/api/v1/history").json()["items"]
        assert items[0]["id"] == s["id"] and items[0]["mode"] == "tree"


def test_unknown_session_and_position(client):
    assert client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000").status_code == 404
    r = client.post("/api/v1/sessions", json={"position_id": "00000000-0000-0000-0000-000000000000", "mode": "tree"})
    assert r.status_code == 404

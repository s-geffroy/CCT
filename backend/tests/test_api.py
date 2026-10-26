from __future__ import annotations

from test_domain import PGN_WITH_VARIATIONS, USER_FEN


def test_health_live(client):
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_ready_reports_engine_down_without_crashing(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"engine": False, "data_dir_writable": True}


def test_meta_without_engine(client):
    body = client.get("/api/v1/meta").json()
    assert body["engine"] is None
    assert body["capabilities"]["multipv_max"] == 20


def test_validate_fen(client):
    body = client.post("/api/v1/positions/validate", json={"fen": USER_FEN}).json()
    assert body["valid"] and isinstance(body["legal_moves_count"], int)
    bad = client.post("/api/v1/positions/validate", json={"fen": "8/8/8/8/8/8/8/8 w - - 0 1"}).json()
    assert not bad["valid"] and bad["errors"]


def test_unknown_fields_and_variants_are_refused(client):
    r = client.post("/api/v1/positions/validate", json={"fen": USER_FEN, "variant": "chess960"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.post("/api/v1/positions/validate", json={"fen": USER_FEN, "best_move": "x"})
    assert r.status_code == 422


def test_play_move_and_illegal_move(client):
    ok = client.post("/api/v1/moves/play", json={"fen": USER_FEN, "move": "e3e4"}).json()
    assert ok["san"] == "e4" and ok["uci"] == "e3e4"
    r = client.post("/api/v1/moves/play", json={"fen": USER_FEN, "move": "e1e3"})
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "ILLEGAL_MOVE", "message": "Ce coup n'est pas legal dans cette position.",
                                  "details": {"move": "e1e3"}}}


def test_import_pgn(client):
    body = client.post("/api/v1/games/import-pgn", json={"pgn": PGN_WITH_VARIATIONS}).json()
    game = body["games"][0]
    assert game["headers"]["Event"] == "Test"
    assert len(game["nodes"]) == 13


def test_oversized_body_is_refused(client):
    r = client.post("/api/v1/games/import-pgn", json={"pgn": "1. e4 " * 30_000})
    assert r.status_code == 413


def test_foreign_host_is_refused(client):
    r = client.get("/api/v1/health/live", headers={"host": "evil.example"})
    assert r.status_code == 400


def test_foreign_origin_cannot_mutate(client):
    r = client.post("/api/v1/positions/validate", json={"fen": USER_FEN},
                    headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN_ORIGIN"
    same = client.post("/api/v1/positions/validate", json={"fen": USER_FEN},
                       headers={"origin": "http://testserver"})
    assert same.status_code == 200


def test_no_wildcard_cors(client):
    r = client.options("/api/v1/positions/validate", headers={
        "origin": "https://evil.example", "access-control-request-method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_spa_fallback_and_assets(client):
    assert "<title>cct</title>" in client.get("/exercices/42").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/v1/inconnu").status_code == 404
    # Pas d'evasion hors du repertoire statique.
    assert "<title>cct</title>" in client.get("/../../etc/passwd").text

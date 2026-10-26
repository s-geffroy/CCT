"""Lot 1 : depuis un PGN a variantes, choisir un noeud, voir sa position, garder son contexte."""
from __future__ import annotations

import chess
from fastapi.testclient import TestClient

from app.main import create_app
from test_domain import PGN_WITH_VARIATIONS, USER_FEN

REPETITION_PGN = """[Event "Repetition"]

1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 *
"""


def _import(client, text=PGN_WITH_VARIATIONS):
    r = client.post("/api/v1/games/import-pgn", json={"pgn": text})
    assert r.status_code == 201, r.text
    return r.json()


def _tree(client, game_id, **params):
    r = client.get(f"/api/v1/games/{game_id}/tree", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _find(nodes, san, parent_san=None):
    for node in nodes.values():
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        if node["san"] == san and (parent_san is None or (parent and parent["san"] == parent_san)):
            return node
    raise AssertionError(f"{san} introuvable")


def test_pick_a_variation_node_and_keep_its_history(client):
    game = _import(client)["games"][0]
    tree = _tree(client, game["id"])
    assert len(tree["nodes"]) == 13 and not tree["truncated"]

    # Noeud dans une sous-variante : 1. e4 c5 2. c3 d5
    d5 = _find(tree["nodes"], "d5")
    r = client.post("/api/v1/positions", json={"source": "pgn", "game_id": game["id"], "node_id": d5["id"]})
    assert r.status_code == 201, r.text
    position = r.json()
    assert position["history_uci"] == ["e2e4", "c7c5", "c2c3", "d7d5"]
    assert position["history_san"] == ["e4", "c5", "c3", "d5"]
    assert position["history_complete"] is True
    assert position["fen"] == d5["fen"]
    assert position["source_node_id"] == d5["id"] and position["source_game_id"] == game["id"]
    assert position["turn"] == "white" and position["warnings"] == []

    # Relecture : l'instantane est retrouve tel quel.
    again = client.get(f"/api/v1/positions/{position['id']}").json()
    assert again["history_uci"] == position["history_uci"] and again["fen"] == position["fen"]


def test_same_context_is_not_duplicated(client):
    game = _import(client)["games"][0]
    node = _find(_tree(client, game["id"])["nodes"], "Bb5")
    payload = {"source": "pgn", "game_id": game["id"], "node_id": node["id"]}
    first = client.post("/api/v1/positions", json=payload)
    second = client.post("/api/v1/positions", json=payload)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"] and second.json()["created"] is False


def test_history_reveals_repetition_that_an_isolated_fen_hides(client):
    game = _import(client, REPETITION_PGN)["games"][0]
    nodes = _tree(client, game["id"])["nodes"]
    last = max(nodes.values(), key=lambda n: n["ply"])
    from_pgn = client.post("/api/v1/positions", json={"source": "pgn", "game_id": game["id"], "node_id": last["id"]}).json()
    assert from_pgn["claimable_draw"] == "threefold_repetition"

    isolated = client.post("/api/v1/positions", json={"source": "fen", "fen": from_pgn["fen"]}).json()
    # Meme placement, contexte different : deux instantanes distincts.
    assert isolated["id"] != from_pgn["id"]
    assert isolated["history_uci"] is None and isolated["claimable_draw"] is None
    assert any("historique" in w for w in isolated["warnings"])


def test_pgn_with_fen_header_gives_partial_history(client):
    text = '[SetUp "1"]\n[FEN "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"]\n\n1. e4 Kd7 *\n'
    game = _import(client, text)["games"][0]
    node = _find(_tree(client, game["id"])["nodes"], "Kd7")
    position = client.post("/api/v1/positions", json={"source": "pgn", "game_id": game["id"], "node_id": node["id"]}).json()
    assert position["history_uci"] == ["e2e4", "e8d7"]
    assert position["history_complete"] is False
    assert position["initial_fen"] == "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    assert position["warnings"]


def test_move_numbers_come_from_the_board_not_the_ply(client):
    text = '[SetUp "1"]\n[FEN "4k3/8/8/8/8/8/4P3/4K3 b - - 0 23"]\n\n23... Kd7 24. e4 *\n'
    game = _import(client, text)["games"][0]
    nodes = _tree(client, game["id"])["nodes"]
    kd7, e4 = _find(nodes, "Kd7"), _find(nodes, "e4")
    assert (kd7["move_number"], kd7["color"]) == (23, "black")
    assert (e4["move_number"], e4["color"]) == (24, "white")


def test_editor_and_fen_positions(client):
    r = client.post("/api/v1/positions", json={"source": "editor", "fen": USER_FEN})
    body = r.json()
    assert r.status_code == 201 and body["source_type"] == "editor"
    assert body["legal_moves_count"] == chess.Board(USER_FEN).legal_moves.count()
    assert len(body["warnings"]) == 2
    bad = client.post("/api/v1/positions", json={"source": "fen", "fen": "8/8/8/8/8/8/8/8 w - - 0 1"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "NO_WHITE_KING"


def test_unknown_ids_and_cross_game_nodes(client):
    a = _import(client)["games"][0]
    b = _import(client, REPETITION_PGN)["games"][0]
    node_of_b = next(iter(_tree(client, b["id"])["nodes"]))
    r = client.post("/api/v1/positions", json={"source": "pgn", "game_id": a["id"], "node_id": node_of_b})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NODE_NOT_FOUND"
    assert client.get("/api/v1/positions/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"/api/v1/games/{a['id']}/tree", params={"root": node_of_b}).status_code == 404
    assert client.get("/api/v1/positions/pas-un-uuid").status_code == 422


def test_tree_pagination_from_a_chosen_root(client):
    game = _import(client)["games"][0]
    full = _tree(client, game["id"])
    page = _tree(client, game["id"], max_nodes=4)
    assert page["truncated"] and page["frontier"]
    assert len(page["nodes"]) <= 4
    # Reprendre a partir d'un noeud de la frontiere donne la suite.
    nxt = _tree(client, game["id"], root=page["frontier"][0])
    assert set(nxt["nodes"]) <= set(full["nodes"])
    assert len(nxt["nodes"]) > 1


def test_multi_game_import_and_listing(client):
    body = _import(client, PGN_WITH_VARIATIONS + "\n" + REPETITION_PGN)
    assert [g["index"] for g in body["games"]] == [0, 1]
    listed = client.get("/api/v1/games").json()["items"]
    assert {g["id"] for g in listed} == {g["id"] for g in body["games"]}
    assert client.get("/api/v1/games", params={"limit": 0}).status_code == 422


def test_data_survives_an_application_restart(settings):
    with TestClient(create_app(settings)) as first:
        game = _import(first)["games"][0]
        node = _find(_tree(first, game["id"])["nodes"], "Nc6")
        position = first.post("/api/v1/positions", json={"source": "pgn", "game_id": game["id"], "node_id": node["id"]}).json()
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/v1/positions/{position['id']}").json()["history_uci"] == position["history_uci"]
        assert second.get(f"/api/v1/games/{game['id']}").json()["nodes_count"] == 13
        listed = second.get("/api/v1/positions").json()["items"]
        assert [p["id"] for p in listed] == [position["id"]]


def test_fen_with_played_moves_keeps_partial_history(client):
    r = client.post("/api/v1/positions", json={"source": "fen", "fen": USER_FEN, "history_uci": ["e3e4", "d5e4"]})
    body = r.json()
    assert r.status_code == 201, body
    assert body["history_uci"] == ["e3e4", "d5e4"] and body["history_complete"] is False
    assert body["initial_fen"] == USER_FEN and body["warnings"]
    start = client.post("/api/v1/positions", json={"source": "fen", "fen": chess.STARTING_FEN, "history_uci": ["e2e4"]}).json()
    assert start["history_complete"] is True and start["warnings"] == []
    illegal = client.post("/api/v1/positions", json={"source": "fen", "fen": USER_FEN, "history_uci": ["e3e5"]})
    assert illegal.status_code == 422 and illegal.json()["error"]["code"] == "HISTORY_ILLEGAL"
    editor = client.post("/api/v1/positions", json={"source": "editor", "fen": USER_FEN, "history_uci": ["e3e4"]})
    assert editor.status_code == 422

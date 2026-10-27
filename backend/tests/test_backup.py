"""Lot 6 (W09) : sauvegarde SQLite coherente, restauration verifiee au demarrage."""
from __future__ import annotations

import logging
import shutil
import sqlite3

from fastapi.testclient import TestClient

from app import backup
from app.main import create_app
from app.persistence.db import load_migrations

log = logging.getLogger("test")


def _session(client) -> str:
    position = client.post("/api/v1/positions", json={"source": "fen",
                                                     "fen": "8/8/8/8/8/4k3/8/4K2R w K - 0 1"}).json()
    return client.post("/api/v1/sessions", json={"position_id": position["id"], "mode": "tree", "start": True}).json()["id"]


def test_backup_is_consistent_and_verified_while_the_app_runs(settings):
    with TestClient(create_app(settings)) as c:
        session_id = _session(c)
        result = backup.create(settings.data_dir)  # base ouverte, en WAL
    assert result["ok"] and result["sessions"] == 1 and result["schema_version"] == len(load_migrations())
    assert result["path"].startswith(str(settings.data_dir / "backups" / "cct-"))
    with sqlite3.connect(result["path"]) as conn:
        assert conn.execute("SELECT id FROM sessions").fetchone()[0] == session_id


def test_verify_rejects_garbage_and_unknown_schema(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"pas une base")
    assert not backup.verify(bad)["ok"]
    assert backup.verify(tmp_path / "absent.sqlite") == {"ok": False, "reason": "fichier introuvable"}
    future = tmp_path / "future.sqlite"
    with sqlite3.connect(future) as conn:
        conn.execute("CREATE TABLE schema_migrations (version INTEGER, name TEXT, applied_at TEXT)")
        conn.execute("INSERT INTO schema_migrations VALUES (99, 'x', 'y')")
    assert "inconnue" in backup.verify(future)["reason"]


def test_restore_replaces_the_database_at_startup_and_keeps_the_old_one(settings):
    with TestClient(create_app(settings)) as c:
        kept = _session(c)
    saved = backup.create(settings.data_dir)["path"]
    with TestClient(create_app(settings)) as c:
        _session(c)  # seance posterieure a la sauvegarde
        assert len(c.get("/api/v1/history").json()["items"]) == 2
    # Ce que fait backup.ps1 : application arretee, fichier depose, redemarrage.
    shutil.copy(saved, settings.data_dir / "restore" / "incoming.sqlite")
    with TestClient(create_app(settings)) as c:
        items = c.get("/api/v1/history").json()["items"]
        assert [i["id"] for i in items] == [kept]
    assert not (settings.data_dir / "restore" / "incoming.sqlite").exists()
    previous = list((settings.data_dir / "backups").glob("avant-restauration-*.sqlite"))
    assert len(previous) == 1 and backup.verify(previous[0])["sessions"] == 2


def test_invalid_restore_file_is_set_aside_and_data_kept(settings):
    with TestClient(create_app(settings)) as c:
        kept = _session(c)
    (settings.data_dir / "restore" / "incoming.sqlite").write_bytes(b"corrompu")
    with TestClient(create_app(settings)) as c:
        assert [i["id"] for i in c.get("/api/v1/history").json()["items"]] == [kept]
    assert list((settings.data_dir / "restore").glob("rejected-*.sqlite"))


def test_cli(settings, monkeypatch, capsys):
    with TestClient(create_app(settings)) as c:
        _session(c)
    monkeypatch.setenv("APP_DATA_DIR", str(settings.data_dir))
    assert backup.main(["create"]) == 0
    assert '"ok": true' in capsys.readouterr().out
    assert backup.main(["verify", str(settings.data_dir / "nope")]) == 1
    assert backup.main([]) == 2


def test_nothing_to_back_up_is_not_an_error(tmp_path):
    # Mise a jour d'une installation jamais utilisee : elle doit pouvoir continuer.
    assert backup.create(tmp_path) == {"ok": True, "skipped": True, "reason": "aucune base : rien a sauvegarder",
                                       "sessions": 0}

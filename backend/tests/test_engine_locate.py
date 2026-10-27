"""Lot 7 : trouver un Stockfish existant, sinon telecharger la release officielle."""
from __future__ import annotations

import asyncio
import hashlib
import http.server
import io
import tarfile
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import catalog, download, locate
from app.main import create_app
from conftest import STOCKFISH, requires_engine

FAKE_ENGINE = """#!/usr/bin/env python3
import sys
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "uci":
        print("id name {name}\\nid author test\\n"
              "option name Threads type spin default 1 min 1 max 512\\n"
              "option name Hash type spin default 16 min 1 max 4096\\nuciok", flush=True)
    elif cmd == "isready":
        print("readyok", flush=True)
    elif cmd == "quit":
        break
"""


def fake_engine(folder: Path, name: str, filename: str = "engine") -> Path:
    path = folder / filename
    path.write_text(FAKE_ENGINE.format(name=name))
    path.chmod(0o755)
    return path


def run(coro):
    return asyncio.run(coro)


def test_names_are_judged_on_the_version():
    assert locate.judge_name("Stockfish 19") is None
    assert locate.judge_name("Stockfish 17.1") is None
    assert locate.judge_name("Stockfish dev-20260901-abcdef") is None
    assert "trop ancienne" in locate.judge_name("Stockfish 15.1")
    assert "n'est pas Stockfish" in locate.judge_name("Komodo 14")


def test_probe_accepts_recent_stockfish_and_explains_refusals(tmp_path):
    ok = run(locate.probe(str(fake_engine(tmp_path, "Stockfish 18")), "path"))
    assert ok.ok and ok.name == "Stockfish 18"
    old = run(locate.probe(str(fake_engine(tmp_path, "Stockfish 11", "old")), "path"))
    assert not old.ok and "trop ancienne" in old.reason
    missing = run(locate.probe(str(tmp_path / "absent"), "reglage"))
    assert missing.reason == "fichier introuvable"
    silent = tmp_path / "silent"
    silent.write_text("#!/bin/sh\nsleep 30\n")
    silent.chmod(0o755)
    mute = run(locate.probe(str(silent), "path", timeout=1))
    assert not mute.ok and "UCI" in mute.reason


@requires_engine
def test_real_stockfish_of_the_image_is_found():
    found = run(locate.probe(STOCKFISH, "environnement"))
    assert found.ok and found.name.startswith("Stockfish 19")


def test_locate_order_and_rejections(tmp_path):
    bad = fake_engine(tmp_path, "Stockfish 12", "bad")
    good = fake_engine(tmp_path, "Stockfish 19", "good")
    result = run(locate.locate(str(bad), str(good), tmp_path / "data"))
    assert result.chosen.path == str(good) and result.chosen.source == "environnement"
    assert [(r.source, "trop ancienne" in r.reason) for r in result.rejected] == [("reglage", True)]


# ------------------------------------------------------------ telechargement

def _release(tmp_path: Path, engine_name: str = "Stockfish 19"):
    """Archive au format officiel (tar.gz, sous-dossier stockfish/) servie en local."""
    member = "stockfish/stockfish-linux-x86-64-universal"
    script = FAKE_ENGINE.format(name=engine_name).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data, mode in ((member, script, 0o755), ("stockfish/Copying.txt", b"GPL v3", 0o644)):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            t.addfile(info, io.BytesIO(data))
    data = buf.getvalue()
    (tmp_path / "srv").mkdir()
    (tmp_path / "srv" / "sf.tar.gz").write_bytes(data)
    asset = catalog.Asset("sf.tar.gz", hashlib.sha256(data).hexdigest(), len(data), member)
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path / "srv"), **k)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return asset, server, f"http://127.0.0.1:{server.server_port}/"


def test_download_verifies_the_checksum_before_installing(tmp_path, monkeypatch):
    asset, server, base = _release(tmp_path)
    monkeypatch.setenv("STOCKFISH_DOWNLOAD_BASE", base)
    try:
        state = download.DownloadState()
        path = download.download(asset, tmp_path / "data", state)
        assert path == tmp_path / "data" / "engines" / catalog.RELEASE / "stockfish"
        assert (path.parent / "Copying.txt").read_text() == "GPL v3"
        assert state.received == asset.size and run(locate.probe(str(path), "telecharge")).ok
        # Empreinte differente : refus, rien d'installe ni de laisse a moitie.
        bad = replace(asset, sha256="0" * 64)
        other = tmp_path / "data2"
        with pytest.raises(download.DownloadError):
            download.download(bad, other, download.DownloadState())
        assert not (other / "engines" / catalog.RELEASE).exists()
        assert list((other / "engines").iterdir()) == []
    finally:
        server.shutdown()


def test_api_offers_download_then_uses_the_downloaded_engine(settings, tmp_path, monkeypatch):
    asset, server, base = _release(tmp_path)
    monkeypatch.setenv("STOCKFISH_DOWNLOAD_BASE", base)
    monkeypatch.setattr("app.api.engine.asset_for_this_machine", lambda: asset)
    monkeypatch.setattr(locate.shutil, "which", lambda _name: None)  # pas de stockfish « deja la »
    s = replace(settings, engine_enabled=True, stockfish_path=None, engine_threads=1, engine_hash_mb=16)
    try:
        with TestClient(create_app(s)) as c:
            view = c.get("/api/v1/engine").json()
            assert view["status"] == "absent" and view["offer"]["size"] == asset.size
            assert c.get("/api/v1/health/ready").status_code == 503
            r = c.post("/api/v1/engine/download")
            assert r.status_code == 202
            deadline = time.monotonic() + 30
            while c.get("/api/v1/engine").json()["download"]["status"] not in ("done", "failed"):
                assert time.monotonic() < deadline
                time.sleep(0.2)
            view = c.get("/api/v1/engine").json()
            assert view["download"]["status"] == "done", view
            assert view["status"] == "ready" and view["current"]["source"] == "telecharge"
            assert view["current"]["name"] == "Stockfish 19"
        with TestClient(create_app(s)) as c:  # au redemarrage : retrouve sans rien retelecharger
            assert c.get("/api/v1/engine").json()["current"]["source"] == "telecharge"
    finally:
        server.shutdown()


def test_user_path_setting_takes_precedence_after_rescan(settings, tmp_path, monkeypatch):
    mine = fake_engine(tmp_path, "Stockfish 18", "mine")
    monkeypatch.setattr(locate.shutil, "which", lambda _name: None)
    s = replace(settings, engine_enabled=True, stockfish_path=None, engine_threads=1, engine_hash_mb=16)
    with TestClient(create_app(s)) as c:
        assert c.get("/api/v1/engine").json()["status"] == "absent"
        assert c.put("/api/v1/settings", json={"engine_path": str(mine)}).status_code == 200
        view = c.post("/api/v1/engine/rescan").json()
        assert view["status"] == "ready" and view["current"] == {
            "name": "Stockfish 18", "source": "reglage", "path": str(mine), "threads": 1, "hash_mb": 16}
        c.put("/api/v1/settings", json={"engine_path": str(tmp_path / "nope")})
        view = c.post("/api/v1/engine/rescan").json()
        assert view["status"] == "absent" and view["rejected"][0]["reason"] == "fichier introuvable"

"""Lot 7 : lanceur de bureau (instance unique, port de repli, arret par jeton, journal fichier)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_package
from app import desktop
from app.main import create_app
from conftest import requires_engine

BACKEND_ROOT = Path(app_package.__file__).resolve().parent.parent


def test_data_dir_follows_the_platform():
    win = desktop.default_data_dir({"LOCALAPPDATA": r"C:\Users\a\AppData\Local"}, windows=True)
    assert win == Path(r"C:\Users\a\AppData\Local") / "Chess Calculation Trainer" / "data"
    assert desktop.default_data_dir({"HOME": "/home/a"}, windows=False) == Path("/home/a/.local/share/chess-calculation-trainer")
    assert desktop.default_data_dir({"APP_DATA_DIR": "/x", "LOCALAPPDATA": "C:"}, windows=True) == Path("/x")


def test_busy_port_falls_back_to_a_neighbour():
    first = desktop.bind_port(0)
    busy = first.getsockname()[1]
    try:
        second = desktop.bind_port(busy, attempts=3)
        try:
            assert second.getsockname()[1] != busy
            assert second.getsockname()[0] == "127.0.0.1"
        finally:
            second.close()
    finally:
        first.close()


def test_desktop_routes_need_the_token(settings):
    with TestClient(create_app(settings)) as c:  # image Docker : routes absentes
        assert c.get("/api/v1/desktop/ping").status_code == 404
    stopped = []
    with TestClient(create_app(replace(settings, desktop_token="secret-jeton"))) as c:
        c.app.state.request_shutdown = lambda: stopped.append(True)
        assert c.get("/api/v1/desktop/ping").status_code == 403
        assert c.get("/api/v1/desktop/ping", headers={"X-CCT-Token": "faux"}).status_code == 403
        assert c.post("/api/v1/desktop/shutdown").status_code == 403
        assert c.get("/api/v1/desktop/ping", headers={"X-CCT-Token": "secret-jeton"}).json() == {"ok": True}
        # Une page web tierce ne connait pas le jeton, et son Origin est refusee de toute facon.
        assert c.post("/api/v1/desktop/shutdown", headers={"X-CCT-Token": "secret-jeton",
                                                           "Origin": "http://evil.example"}).status_code == 403
        assert c.post("/api/v1/desktop/shutdown", headers={"X-CCT-Token": "secret-jeton"}).status_code == 202
        deadline = time.monotonic() + 5
        while not stopped and time.monotonic() < deadline:
            time.sleep(0.05)
        assert stopped == [True]


def _launch(data_dir: Path, *args: str) -> subprocess.Popen:
    env = {**os.environ, "ENGINE_THREADS": "1", "ENGINE_HASH_MB": "16"}
    env.pop("APP_DATA_DIR", None)
    return subprocess.Popen([sys.executable, "-m", "app.desktop", "--data-dir", str(data_dir), "--no-browser", *args],
                            cwd=BACKEND_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


@requires_engine
def test_single_instance_lifecycle(tmp_path):
    data = tmp_path / "donnees"
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    first = _launch(data, "--port", str(busy))
    try:
        deadline = time.monotonic() + 60
        info = None
        while time.monotonic() < deadline:
            info = desktop.read_instance(data)
            if info and desktop.is_alive(info):
                break
            assert first.poll() is None, first.stderr.read().decode()
            time.sleep(0.2)
        assert info and desktop.is_alive(info)
        assert info["port"] != busy and info["pid"] == first.pid  # port occupe : voisin choisi

        # Second lancement : rejoint l'instance et rend la main, sans second serveur.
        second = _launch(data, "--port", str(busy))
        assert second.wait(timeout=30) == 0
        assert desktop.read_instance(data) == info

        # Arret propre par le jeton (comme l'installateur avant une mise a jour).
        stop = subprocess.run([sys.executable, "-m", "app.desktop", "--data-dir", str(data), "--stop"],
                              cwd=BACKEND_ROOT, timeout=60)
        assert stop.returncode == 0
        assert first.wait(timeout=30) == 0
        assert desktop.read_instance(data) is None
    finally:
        blocker.close()
        if first.poll() is None:
            first.kill()
    log = (data / "logs" / "cct.log").read_text(encoding="utf-8")
    assert "moteur demarre : Stockfish 19" in log
    assert "application deja ouverte" in log
    assert "arret demande par le lanceur" in log and "cct.app arret" in log
    assert desktop.request_stop(data) is True  # plus rien a arreter


def test_docker_backup_is_offered_to_the_first_native_start(tmp_path, settings):
    """Passage du paquet Docker (v0.1.x) a l'installateur natif : ses sauvegardes sont
    dans %LOCALAPPDATA%\\ChessCalculationTrainer\\backups ; les donnees natives vivent
    AILLEURS (le desinstalleur Docker efface sa racine, sauf backups\\)."""
    from app import backup

    local = tmp_path / "Local"
    backups = desktop.docker_backups_dir({"LOCALAPPDATA": str(local)})
    assert backups == local / "ChessCalculationTrainer" / "backups"
    assert desktop.docker_backups_dir({}) is None
    data = desktop.default_data_dir({"LOCALAPPDATA": str(local)}, windows=True)
    assert not data.is_relative_to(local / "ChessCalculationTrainer")

    old = replace(settings, data_dir=tmp_path / "docker-data")
    with TestClient(create_app(old)) as c:  # une base Docker avec une position
        c.post("/api/v1/positions", json={"source": "fen", "fen": "8/8/8/8/8/4k3/8/4K2R w K - 0 1"})
    saved = backup.create(old.data_dir)
    backups.mkdir(parents=True)
    for name in ("cct-20261001-120000.sqlite", "cct-20261027-090000.sqlite"):
        (backups / name).write_bytes(Path(saved["path"]).read_bytes())

    assert desktop.import_docker_backup(data, None) is None  # hors Windows : rien a reprendre
    assert desktop.import_docker_backup(data, backups).name == "cct-20261027-090000.sqlite"  # la plus recente
    with TestClient(create_app(replace(settings, data_dir=data))) as c:
        assert len(c.get("/api/v1/positions").json()["items"]) == 1
    assert desktop.import_docker_backup(data, backups) is None  # base presente : jamais ecrasee

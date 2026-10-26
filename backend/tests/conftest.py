from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import get_settings

STOCKFISH = os.environ.get("STOCKFISH_PATH", "/usr/local/bin/stockfish")
requires_engine = pytest.mark.skipif(not Path(STOCKFISH).is_file(), reason="Stockfish absent")


@pytest.fixture
def settings(tmp_path: Path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>cct</title>")
    (static / "assets" / "app.js").write_text("console.log('ok')")
    data = tmp_path / "data"
    data.mkdir()
    return replace(
        get_settings(),
        data_dir=data,
        static_dir=static,
        allowed_hosts=["testserver", "127.0.0.1", "localhost"],
        engine_enabled=False,
        max_pgn_bytes=64 * 1024,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def engine_client(settings):
    with TestClient(create_app(replace(settings, engine_enabled=True, engine_threads=1, engine_hash_mb=16))) as c:
        yield c

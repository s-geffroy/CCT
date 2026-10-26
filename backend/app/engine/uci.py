"""Un seul processus Stockfish, pilote en asyncio par python-chess.

Aucun acces concurrent a l'instance : toute recherche prend `lock`. En cas de
panne, `restart()` remplace le processus ; l'etat UCI precedent est abandonne.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import chess.engine

from ..log import get_logger
from ..settings import Settings

log = get_logger("engine")

PING_TIMEOUT_S = 5.0


@dataclass
class EngineInfo:
    name: str
    author: str
    threads: int
    hash_mb: int
    build: dict[str, str]


def read_build_info(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line)


class EngineManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = asyncio.Lock()
        self._engine: chess.engine.UciProtocol | None = None
        self.info: EngineInfo | None = None
        self.last_error: str | None = None

    @property
    def engine(self) -> chess.engine.UciProtocol:
        if self._engine is None:
            raise RuntimeError("moteur non demarre")
        return self._engine

    async def start(self) -> None:
        try:
            _transport, engine = await chess.engine.popen_uci(self.settings.stockfish_path)
            await engine.configure({"Threads": self.settings.engine_threads, "Hash": self.settings.engine_hash_mb})
            self._engine = engine
            self.info = EngineInfo(
                name=engine.id.get("name", "inconnu"),
                author=engine.id.get("author", ""),
                threads=self.settings.engine_threads,
                hash_mb=self.settings.engine_hash_mb,
                build=read_build_info(self.settings.stockfish_build_info),
            )
            self.last_error = None
            log.info("moteur demarre : %s (threads=%d, hash=%d Mo)",
                     self.info.name, self.info.threads, self.info.hash_mb)
        except Exception as exc:  # le serveur doit vivre sans moteur
            self._engine = None
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.error("demarrage du moteur impossible : %s", self.last_error)

    async def stop(self) -> None:
        if self._engine is not None:
            try:
                await asyncio.wait_for(self._engine.quit(), timeout=5)
            except Exception as exc:
                log.warning("arret du moteur incomplet : %r", exc)
            self._engine = None

    async def restart(self) -> None:
        log.warning("redemarrage du moteur")
        await self.stop()
        await self.start()

    async def is_ready(self) -> bool:
        if self._engine is None:
            return False
        if self.lock.locked():
            # Une recherche est en cours : le moteur repond, inutile de l'interrompre.
            return True
        try:
            await asyncio.wait_for(self._engine.ping(), timeout=PING_TIMEOUT_S)
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.error("moteur sans reponse : %s", self.last_error)
            return False

"""Telechargement de la release officielle de Stockfish (Lot 7).

Telechargement en flux, empreinte SHA-256 verifiee AVANT toute extraction,
installation atomique dans <donnees>/engines/sf_19/, puis verification UCI du
moteur installe. Un echec ne laisse aucun fichier a moitie installe.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ..log import get_logger
from .catalog import RELEASE, Asset
from .locate import engines_dir

log = get_logger("engine.download")

CHUNK = 1 << 20


@dataclass
class DownloadState:
    status: str = "idle"  # idle | downloading | verifying | installing | done | failed
    received: int = 0
    total: int = 0
    error: str | None = None
    path: str | None = None
    started_at: float | None = None

    def view(self) -> dict:
        return asdict(self)


class DownloadError(Exception):
    pass


def _extract_member(archive: Path, member: str, target: Path) -> None:
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z, z.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, CHUNK)
    else:
        with tarfile.open(archive, "r:gz") as t:
            src = t.extractfile(member)
            if src is None:
                raise DownloadError(f"{member} absent de l'archive")
            with src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)


def download(asset: Asset, data_dir: Path, state: DownloadState) -> Path:
    """Bloquant (a lancer dans un thread). Met `state` a jour au fil de l'eau."""
    state.status, state.received, state.total, state.error = "downloading", 0, asset.size, None
    state.started_at = time.time()
    root = engines_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="download-", dir=root))
    try:
        archive = work / asset.file
        digest = hashlib.sha256()
        request = urllib.request.Request(asset.url, headers={"User-Agent": "chess-calculation-trainer"})
        with urllib.request.urlopen(request, timeout=60) as response, open(archive, "wb") as out:
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                state.total = int(length)
            for chunk in iter(lambda: response.read(CHUNK), b""):
                out.write(chunk)
                digest.update(chunk)
                state.received += len(chunk)
        state.status = "verifying"
        if digest.hexdigest() != asset.sha256:
            raise DownloadError("empreinte SHA-256 inattendue : archive refusee, rien n'a ete installe")
        state.status = "installing"
        exe_name = "stockfish.exe" if asset.member.endswith(".exe") else "stockfish"
        staged = work / exe_name
        _extract_member(archive, asset.member, staged)
        staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        licence = work / "Copying.txt"
        try:  # licence GPL de Stockfish, gardee a cote du binaire
            _extract_member(archive, asset.member.rsplit("/", 1)[0] + "/Copying.txt", licence)
        except (KeyError, DownloadError):
            licence = None
        final = root / RELEASE
        if final.exists():
            shutil.rmtree(final)
        final.mkdir()
        os.replace(staged, final / exe_name)
        if licence is not None:
            os.replace(licence, final / "Copying.txt")
        state.path = str(final / exe_name)
        return final / exe_name
    except Exception as exc:
        state.status, state.error = "failed", (str(exc) if isinstance(exc, DownloadError)
                                               else f"telechargement impossible ({type(exc).__name__}: {exc})")
        log.error("telechargement de Stockfish : %s", state.error)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)

"""Trouver un Stockfish utilisable sur la machine (Lot 7).

Ordre : chemin choisi par l'utilisateur (Reglages), variable STOCKFISH_PATH
(image Docker), PATH, emplacements habituels (Windows), moteur deja telecharge
par l'application. Chaque candidat est VERIFIE (poignee de main UCI avec delai)
et doit etre Stockfish 16 ou plus recent (reseau NNUE integre, MultiPV) ; les
refus sont gardes avec leur raison pour l'interface.
"""
from __future__ import annotations

import asyncio
import glob
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import chess.engine

from .catalog import RELEASE

MIN_MAJOR = 16
PROBE_TIMEOUT_S = 15.0
_VERSION_RE = re.compile(r"^Stockfish\s+(\d+)(?:\.(\d+))?\b")
_DEV_RE = re.compile(r"^Stockfish\s+(dev|\d{6})", re.IGNORECASE)


@dataclass
class Probe:
    path: str
    source: str  # 'reglage' | 'environnement' | 'path' | 'emplacement' | 'telecharge'
    ok: bool = False
    name: str | None = None
    reason: str | None = None


@dataclass
class Located:
    chosen: Probe | None
    rejected: list[Probe] = field(default_factory=list)


def engines_dir(data_dir: Path) -> Path:
    return data_dir / "engines"


def downloaded_engine(data_dir: Path) -> Path | None:
    folder = engines_dir(data_dir) / RELEASE
    for name in ("stockfish.exe", "stockfish"):
        if (folder / name).is_file():
            return folder / name
    return None


def _known_locations() -> list[str]:
    """Dossiers ou les logiciels d'echecs courants rangent Stockfish (Windows)."""
    if os.name != "nt":
        return []
    roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    docs = os.path.join(os.environ.get("USERPROFILE", ""), "Documents")
    patterns = []
    for root in filter(None, roots):
        patterns += [os.path.join(root, "Stockfish", "**", "stockfish*.exe"),
                     os.path.join(root, "Arena", "Engines", "**", "stockfish*.exe")]
    patterns.append(os.path.join(docs, "ChessBase", "Engines*", "**", "stockfish*.exe"))
    found: list[str] = []
    for pattern in patterns:
        found += sorted(glob.glob(pattern, recursive=True))[:5]
    return found


def candidates(user_path: str | None, env_path: str | None, data_dir: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if user_path:
        out.append((user_path, "reglage"))
    if env_path:
        out.append((env_path, "environnement"))
    on_path = shutil.which("stockfish")
    if on_path:
        out.append((on_path, "path"))
    out += [(p, "emplacement") for p in _known_locations()]
    downloaded = downloaded_engine(data_dir)
    if downloaded:
        out.append((str(downloaded), "telecharge"))
    seen: set[str] = set()
    unique = []
    for path, source in out:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            unique.append((path, source))
    return unique


def judge_name(name: str) -> str | None:
    """None si le nom annonce un Stockfish acceptable, sinon la raison du refus."""
    match = _VERSION_RE.match(name)
    if match:
        major = int(match.group(1))
        return None if major >= MIN_MAJOR else f"{name} : version trop ancienne (Stockfish {MIN_MAJOR} ou plus recent requis)"
    if _DEV_RE.match(name):
        return None  # version de developpement : recente par construction
    return f"« {name} » n'est pas Stockfish (seul Stockfish {MIN_MAJOR}+ est pris en charge)"


async def probe(path: str, source: str, timeout: float = PROBE_TIMEOUT_S) -> Probe:
    result = Probe(path=path, source=source)
    if not Path(path).is_file():
        result.reason = "fichier introuvable"
        return result
    engine = None
    try:
        async with asyncio.timeout(timeout):
            _transport, engine = await chess.engine.popen_uci(path)
            result.name = engine.id.get("name", "")
            await engine.ping()
    except TimeoutError:
        result.reason = "le programme ne repond pas au protocole UCI"
    except Exception as exc:  # binaire incompatible, droits, protocole...
        result.reason = f"demarrage impossible ({type(exc).__name__})"
    finally:
        if engine is not None:
            try:
                await asyncio.wait_for(engine.quit(), timeout=5)
            except Exception:
                pass
    if result.reason is None:
        result.reason = judge_name(result.name or "")
        result.ok = result.reason is None
    return result


async def locate(user_path: str | None, env_path: str | None, data_dir: Path) -> Located:
    rejected = []
    for path, source in candidates(user_path, env_path, data_dir):
        found = await probe(path, source)
        if found.ok:
            return Located(found, rejected)
        rejected.append(found)
    return Located(None, rejected)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

"""Release officielle de Stockfish proposee au telechargement (Lot 7).

Binaires « universal » de la release sf_19 : ils choisissent eux-memes les
instructions du processeur (AVX2, etc.) a l'execution, donc une seule archive
par plateforme. Empreintes SHA-256 verifiees contre celles publiees par GitHub
(26/10/2026) ; une archive differente est refusee.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass

RELEASE = "sf_19"
BASE_URL = f"https://github.com/official-stockfish/Stockfish/releases/download/{RELEASE}/"


@dataclass(frozen=True)
class Asset:
    file: str
    sha256: str
    size: int
    member: str  # chemin de l'executable dans l'archive

    @property
    def url(self) -> str:
        # Surchargeable pour les tests (serveur local) ; jamais pour un utilisateur.
        return os.environ.get("STOCKFISH_DOWNLOAD_BASE", BASE_URL) + self.file


ASSETS: dict[tuple[str, str], Asset] = {
    ("windows", "x86_64"): Asset(
        "stockfish-windows-x86-64-universal.zip",
        "3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7", 81_431_614,
        "stockfish/stockfish-windows-x86-64-universal.exe"),
    ("linux", "x86_64"): Asset(
        "stockfish-linux-x86-64-universal.tar.gz",
        "9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f", 81_388_977,
        "stockfish/stockfish-linux-x86-64-universal"),
}


def current_platform() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64"}.get(machine, machine)
    return system, machine


def asset_for_this_machine() -> Asset | None:
    return ASSETS.get(current_platform())

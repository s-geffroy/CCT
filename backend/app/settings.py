"""Configuration lue dans l'environnement, bornee et validee au demarrage."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-dev")  # fixe au build de l'image de release


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    if not lo <= value <= hi:
        raise ValueError(f"{name}={value} hors bornes [{lo}, {hi}]")
    return value


def _list_env(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _default_threads() -> int:
    # Quota effectif du conteneur (cgroups) plutot que le nombre de coeurs de
    # l'hote : os.sched_getaffinity ne voit pas les quotas CPU.
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            return max(1, min(2, int(int(quota) / int(period))))
    except (OSError, ValueError):
        pass
    return max(1, min(2, (os.cpu_count() or 1) - 1))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("APP_DATA_DIR", "/data")))
    static_dir: Path = field(default_factory=lambda: Path(os.environ.get("APP_STATIC_DIR", "/app/static")))
    stockfish_path: str = field(default_factory=lambda: os.environ.get("STOCKFISH_PATH", "/usr/local/bin/stockfish"))
    stockfish_build_info: Path = Path("/usr/share/doc/stockfish/stockfish-build.txt")
    engine_threads: int = field(default_factory=lambda: _int_env("ENGINE_THREADS", _default_threads(), 1, 64))
    engine_hash_mb: int = field(default_factory=lambda: _int_env("ENGINE_HASH_MB", 128, 16, 4096))
    max_pgn_bytes: int = field(default_factory=lambda: _int_env("MAX_PGN_BYTES", 5 * 1024 * 1024, 1024, 50 * 1024 * 1024))
    max_pgn_games: int = field(default_factory=lambda: _int_env("MAX_PGN_GAMES", 200, 1, 10_000))
    max_pgn_nodes: int = field(default_factory=lambda: _int_env("MAX_PGN_NODES", 50_000, 100, 1_000_000))
    # Hotes acceptes (protection DNS rebinding) et origines acceptees pour les
    # mutations (protection contre un site tiers qui viserait localhost).
    allowed_hosts: list[str] = field(default_factory=lambda: _list_env("ALLOWED_HOSTS", ["127.0.0.1", "localhost"]))
    allowed_origins: list[str] = field(default_factory=lambda: _list_env("ALLOWED_ORIGINS", []))
    max_queued_jobs: int = field(default_factory=lambda: _int_env("MAX_QUEUED_JOBS", 20, 1, 1000))
    engine_enabled: bool = field(default_factory=lambda: os.environ.get("ENGINE_ENABLED", "1") != "0")
    # Reference d'une seance (doc 06) : analyse racine puis arbre sous plafonds.
    reference_depth: int = field(default_factory=lambda: _int_env("REFERENCE_DEPTH", 21, 8, 32))
    reference_budget_s: int = field(default_factory=lambda: _int_env("REFERENCE_BUDGET_S", 300, 5, 3600))
    tree_budget_s: int = field(default_factory=lambda: _int_env("TREE_BUDGET_S", 300, 0, 3600))
    tree_max_nodes: int = field(default_factory=lambda: _int_env("TREE_MAX_NODES", 80, 1, 500))
    tree_node_depth: int = field(default_factory=lambda: _int_env("TREE_NODE_DEPTH", 21, 8, 32))
    tree_node_budget_s: int = field(default_factory=lambda: _int_env("TREE_NODE_BUDGET_S", 30, 5, 600))
    tree_auto_max_ply: int = field(default_factory=lambda: _int_env("TREE_AUTO_MAX_PLY", 4, 0, 12))


def get_settings() -> Settings:
    return Settings()

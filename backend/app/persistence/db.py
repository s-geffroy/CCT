"""SQLite : connexion, migrations versionnees deterministes, sauvegarde coherente.

Une connexion par unite de travail (les routes synchrones de FastAPI tournent
dans un pool de threads ; sqlite3 interdit le partage entre threads).
Les migrations sont des fichiers `NNNN_nom.sql` appliques dans l'ordre, chacun
dans sa transaction ; avant toute mise a niveau d'une base existante, une
copie est faite avec l'API backup de SQLite (jamais une copie de fichier brute
d'une base en WAL).
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..log import get_logger

log = get_logger("db")

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_MIGRATION_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
BUSY_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = []
    for path in sorted(directory.iterdir()):
        match = _MIGRATION_RE.match(path.name)
        if match:
            migrations.append(Migration(int(match.group(1)), path.stem, path.read_text(encoding="utf-8")))
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"migrations non contigues : {versions}")
    return migrations


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transaction courte et explicite (IMMEDIATE : verrou d'ecriture d'emblee)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def backup(conn: sqlite3.Connection, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(destination)
    try:
        conn.backup(target)
    finally:
        target.close()


class Database:
    def __init__(self, path: Path, migrations: list[Migration] | None = None):
        self.path = path
        self.migrations = migrations if migrations is not None else load_migrations()
        self.version = 0
        self.journal_mode = ""

    def open(self) -> sqlite3.Connection:
        return connect(self.path)

    def migrate(self) -> int:
        """Applique les migrations manquantes ; renvoie la version finale."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.open()
        try:
            self.journal_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if self.journal_mode.lower() != "wal":
                log.warning("WAL indisponible sur ce systeme de fichiers (mode %s)", self.journal_mode)
            version = current_version(conn)
            latest = self.migrations[-1].version if self.migrations else 0
            if version > latest:
                raise RuntimeError(f"base en version {version}, plus recente que l'application ({latest})")
            pending = [m for m in self.migrations if m.version > version]
            if pending and version > 0:
                stamp = utc_now().replace(":", "").replace("-", "").replace(".", "")
                target = self.path.parent / "backups" / f"app-v{version}-{stamp}.sqlite"
                backup(conn, target)
                log.info("sauvegarde avant migration : %s", target.name)
            for migration in pending:
                with transaction(conn):
                    for statement in _split_sql(migration.sql):
                        conn.execute(statement)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, utc_now()),
                    )
                log.info("migration appliquee : %s", migration.name)
            self.version = current_version(conn)
            return self.version
        finally:
            conn.close()

    def is_ready(self) -> bool:
        try:
            conn = self.open()
            try:
                return current_version(conn) == (self.migrations[-1].version if self.migrations else 0)
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.open()
        try:
            yield conn
        finally:
            conn.close()


def _split_sql(sql: str) -> list[str]:
    """Decoupe un script en instructions (executescript ignore la transaction ouverte)."""
    statements, buffer = [], []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        candidate = "\n".join(buffer)
        if sqlite3.complete_statement(candidate):
            statements.append(candidate.strip())
            buffer = []
    if buffer:
        raise RuntimeError("instruction SQL incomplete en fin de migration")
    return statements

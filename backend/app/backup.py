"""Sauvegarde et restauration de la base SQLite (Lot 6, W09).

Utilise depuis Windows (`backup.ps1`, `update.ps1`) :

    python -m app.backup create            # -> /data/backups/cct-AAAAMMJJ-HHMMSS.sqlite
    python -m app.backup verify FICHIER     # base complete et lisible ?

Une sauvegarde passe par l'API backup de SQLite (jamais une copie brute d'une
base en WAL), puis est verifiee (`integrity_check`, version de schema).

Restauration : le fichier depose en `/data/restore/incoming.sqlite` (par
`docker compose cp`, application arretee) est pris au demarrage suivant, apres
verification ; la base remplacee est d'abord sauvegardee. Un fichier invalide
est ecarte et la base actuelle reste en place.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from .persistence.db import backup as sqlite_backup, load_migrations

RESTORE_DIR = "restore"
INCOMING = "incoming.sqlite"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def verify(path: Path) -> dict:
    """Controle une base : integrite et version de schema connue de l'application."""
    if not path.is_file():
        return {"ok": False, "reason": "fichier introuvable"}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            known = bool(version) and version <= len(load_migrations())
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] if known and version >= 2 else 0
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"ok": False, "reason": f"base illisible ({exc})"}
    latest = len(load_migrations())
    if integrity != "ok":
        return {"ok": False, "reason": f"integrite : {integrity}"}
    if not version or version > latest:
        return {"ok": False, "reason": f"version de schema {version} inconnue (application : {latest})"}
    return {"ok": True, "schema_version": version, "sessions": sessions, "bytes": path.stat().st_size}


def create(data_dir: Path) -> dict:
    source = data_dir / "app.sqlite"
    if not source.is_file():
        return {"ok": False, "reason": "aucune base a sauvegarder"}
    target = data_dir / "backups" / f"cct-{_stamp()}.sqlite"
    conn = sqlite3.connect(source)
    try:
        sqlite_backup(conn, target)
    finally:
        conn.close()
    result = verify(target)
    return {**result, "path": str(target)}


def apply_pending_restore(data_dir: Path, log) -> None:
    """Au demarrage, avant les migrations : remplace la base par la sauvegarde
    deposee, si elle est valide. Jamais de perte : l'ancienne base est gardee."""
    incoming = data_dir / RESTORE_DIR / INCOMING
    if not incoming.is_file():
        return
    check = verify(incoming)
    if not check["ok"]:
        rejected = incoming.with_name(f"rejected-{_stamp()}.sqlite")
        incoming.rename(rejected)
        log.error("restauration refusee (%s) : fichier mis de cote (%s)", check["reason"], rejected.name)
        return
    current = data_dir / "app.sqlite"
    if current.is_file():
        conn = sqlite3.connect(current)
        try:
            sqlite_backup(conn, data_dir / "backups" / f"avant-restauration-{_stamp()}.sqlite")
        finally:
            conn.close()
    for suffix in ("-wal", "-shm"):
        Path(str(current) + suffix).unlink(missing_ok=True)
    incoming.replace(current)
    log.warning("base restauree depuis une sauvegarde (schema v%s, %s seance(s))",
                check["schema_version"], check["sessions"])


def main(argv: list[str]) -> int:
    from .settings import get_settings

    data_dir = get_settings().data_dir
    if argv[:1] == ["create"]:
        result = create(data_dir)
    elif argv[:1] == ["verify"] and len(argv) == 2:
        result = verify(Path(argv[1]))
    else:
        print("usage : python -m app.backup create | verify FICHIER", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

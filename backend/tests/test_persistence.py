"""SQLite : migrations, WAL, cles etrangeres, sauvegarde avant mise a niveau."""
from __future__ import annotations

import sqlite3

import pytest

from app.persistence.db import Database, Migration, load_migrations


def test_fresh_database_is_migrated_with_wal_and_foreign_keys(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    assert db.migrate() == len(load_migrations())
    assert db.journal_mode == "wal"
    with db.session() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"schema_migrations", "pgn_imports", "games", "game_nodes", "positions", "settings"} <= tables


def test_migrate_is_idempotent_and_does_not_back_up_without_change(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    db.migrate()
    assert not (tmp_path / "backups").exists()


def test_upgrade_backs_up_existing_data_first(tmp_path):
    base = load_migrations()
    Database(tmp_path / "app.sqlite", base).migrate()
    with sqlite3.connect(tmp_path / "app.sqlite") as conn:
        conn.execute("INSERT INTO settings VALUES ('k', '1', 'now')")

    extra = Migration(len(base) + 1, f"{len(base) + 1:04d}_test", "CREATE TABLE extra (x INTEGER);")
    upgraded = Database(tmp_path / "app.sqlite", [*base, extra])
    assert upgraded.migrate() == len(base) + 1

    backups = list((tmp_path / "backups").glob("app-v*.sqlite"))
    assert len(backups) == 1
    # La sauvegarde est une base complete et restaurable, a l'ancienne version.
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT value_json FROM settings WHERE key = 'k'").fetchone()[0] == "1"
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == len(base)


def test_failed_migration_is_rolled_back(tmp_path):
    base = load_migrations()
    Database(tmp_path / "app.sqlite", base).migrate()
    broken = Migration(len(base) + 1, "broken", "CREATE TABLE ok (x INTEGER);\nINSERT INTO nope VALUES (1);")
    with pytest.raises(sqlite3.OperationalError):
        Database(tmp_path / "app.sqlite", [*base, broken]).migrate()
    with sqlite3.connect(tmp_path / "app.sqlite") as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "ok" not in tables
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == len(base)


def test_newer_database_is_refused(tmp_path):
    Database(tmp_path / "app.sqlite").migrate()
    with pytest.raises(RuntimeError, match="plus recente"):
        Database(tmp_path / "app.sqlite", []).migrate()


def test_lot4_tables_exist(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    with db.session() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {r[1] for r in conn.execute("PRAGMA table_info(analysis_jobs)")}
    assert {"reference_trees", "reference_nodes", "reviews", "review_diagnostics"} <= tables
    assert "node_path_json" in columns


def test_queue_ages_so_background_jobs_are_not_starved(tmp_path):
    from datetime import UTC, datetime, timedelta

    from app.persistence import analysis_repo

    now = datetime.now(UTC)
    stamp = lambda d: d.isoformat(timespec="milliseconds").replace("+00:00", "Z")  # noqa: E731

    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    with db.session() as conn:
        conn.execute("INSERT INTO positions (id, context_key, variant, fen, initial_fen, history_complete, source_type,"
                     " turn, legal_moves_count, validation_status, created_at) VALUES"
                     " ('p', 'k', 'standard', 'f', 'f', 0, 'fen', 'white', 20, 'valid', '2026-01-01T00:00:00.000Z')")
        for job_id, priority, created in (("old", 40, stamp(now - timedelta(hours=2))), ("new", 100, stamp(now)),
                                         ("recent", 40, stamp(now - timedelta(minutes=1)))):
            conn.execute("INSERT INTO analysis_jobs (id, position_id, purpose, scope, priority, state, settings_json,"
                         " cache_key, created_at) VALUES (?, 'p', 'study', 'root', ?, 'queued', '{}', ?, ?)",
                         (job_id, priority, job_id, created))
        # Le travail de fond qui attend depuis longtemps passe devant ; sinon, la priorite.
        assert [analysis_repo.claim_next(conn)["id"] for _ in range(3)] == ["old", "new", "recent"]

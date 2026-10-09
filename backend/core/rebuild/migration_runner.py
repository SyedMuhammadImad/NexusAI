"""Serialize migrations and reject edits to already-applied migration files."""
import hashlib
import sqlite3
from pathlib import Path


def migrate(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS migration_checksums(version INTEGER PRIMARY KEY, sha256 TEXT NOT NULL)")
        has_versions = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")} if has_versions else set()
        paths = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
        known = {int(path.name.split("_")[0]) for path in paths}
        if applied - known or (applied and applied != set(range(1,max(applied)+1))):
            raise ValueError("Unsupported or incomplete migration history")
        for path in paths:
            version = int(path.name.split("_")[0])
            script = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(script.encode()).hexdigest()
            recorded = conn.execute("SELECT sha256 FROM migration_checksums WHERE version=?", (version,)).fetchone()
            if recorded and recorded[0] != digest:
                raise ValueError(f"Applied migration {version} checksum mismatch")
            if version not in applied:
                statement = ""
                for line in script.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        if statement.strip().upper() not in {"BEGIN IMMEDIATE;", "COMMIT;", "PRAGMA FOREIGN_KEYS=ON;"}:
                            conn.execute(statement)
                        statement = ""
                if statement.strip():
                    raise ValueError(f"Incomplete migration {version}")
            conn.execute("INSERT INTO migration_checksums VALUES(?,?) ON CONFLICT(version) DO NOTHING", (version,digest))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

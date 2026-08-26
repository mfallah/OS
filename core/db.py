"""SQLite storage layer with schema migrations.

Storage location resolution order:
  1. PERSONAL_OS_DB environment variable (explicit path or :memory:)
  2. /tmp on Vercel-style read-only deployments (ephemeral per warm instance;
     point PERSONAL_OS_DB at durable storage or add a remote adapter for
     production persistence)
  3. <repo>/personal_os.sqlite3 for local development
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

SCHEMA_VERSION = 2

def default_db_path() -> str:
    explicit = os.environ.get("PERSONAL_OS_DB")
    if explicit:
        return explicit
    if os.environ.get("VERCEL"):
        return "/tmp/personal_os.sqlite3"
    return str(Path(__file__).resolve().parent.parent / "personal_os.sqlite3")

class Database:
    """Thin thread-safe wrapper around a SQLite connection."""

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.migrate()

    def execute(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def query(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def migrate(self):
        with self.lock:
            self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entities(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,
                status TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                deleted_at TEXT, idempotency_key TEXT UNIQUE);
            CREATE INDEX IF NOT EXISTS entity_kind ON entities(kind);
            CREATE INDEX IF NOT EXISTS entity_updated ON entities(updated_at);
            CREATE TABLE IF NOT EXISTS edges(
                source TEXT NOT NULL, relation TEXT NOT NULL, target TEXT NOT NULL,
                created_at TEXT NOT NULL, created_by TEXT DEFAULT 'user',
                PRIMARY KEY(source, relation, target));
            CREATE INDEX IF NOT EXISTS edge_target ON edges(target);
            CREATE TABLE IF NOT EXISTS memories(
                id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL,
                confidence REAL NOT NULL, source TEXT NOT NULL, provenance TEXT,
                scope TEXT NOT NULL, importance INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                corrected_by_user INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL DEFAULT 'system',
                why TEXT, expires_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS memory_cat ON memories(category);
            CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY, type TEXT NOT NULL, actor TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE);
            CREATE INDEX IF NOT EXISTS event_type ON events(type);
            CREATE TABLE IF NOT EXISTS audit(
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, agent TEXT, skill TEXT,
                tool TEXT, action TEXT NOT NULL, permission TEXT NOT NULL,
                risk INTEGER NOT NULL DEFAULT 0, approved INTEGER NOT NULL DEFAULT 0,
                result TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals(
                id TEXT PRIMARY KEY, action TEXT NOT NULL, reason TEXT NOT NULL,
                risk INTEGER NOT NULL, permission TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', context TEXT,
                created_at TEXT NOT NULL, decided_at TEXT, actor TEXT DEFAULT 'user');
            CREATE TABLE IF NOT EXISTS workflow_runs(
                id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, status TEXT NOT NULL,
                steps TEXT NOT NULL, error TEXT, started_at TEXT NOT NULL, finished_at TEXT,
                idempotency_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS notifications(
                id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
                body TEXT, entity_id TEXT, why TEXT, status TEXT NOT NULL DEFAULT 'unread',
                snoozed_until TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY, window_start TEXT NOT NULL, count INTEGER NOT NULL);
            """)
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),))
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()

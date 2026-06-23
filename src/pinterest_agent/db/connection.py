"""SQLite connection manager with schema initialization and transaction support."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

_SCHEMA_VERSION = 4

# ---------------------------------------------------------------------------
# Schema DDL — applied on first connect
# ---------------------------------------------------------------------------

SCHEMA_SQL = f"""
-- Schema version tracking for future migrations
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Prompt queue
CREATE TABLE IF NOT EXISTS prompts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    aesthetic      TEXT    NOT NULL,
    template_id    TEXT    NOT NULL,
    variables      TEXT    NOT NULL DEFAULT '{{}}',
    variable_seed  INTEGER NOT NULL DEFAULT 0,
    text           TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'generated', 'failed')),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts(status);
CREATE INDEX IF NOT EXISTS idx_prompts_hash ON prompts(text);
CREATE INDEX IF NOT EXISTS idx_prompts_template_seed ON prompts(template_id, variable_seed);

-- Image metadata store
CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id       INTEGER NOT NULL REFERENCES prompts(id),
    prompt_hash     TEXT    NOT NULL DEFAULT '',
    phash           TEXT    NOT NULL DEFAULT '',
    sha256          TEXT    NOT NULL DEFAULT '',
    file_path       TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'generated', 'published', 'failed')),
    pin_id          TEXT,
    niche           TEXT    NOT NULL DEFAULT '',
    backend         TEXT    NOT NULL DEFAULT '',
    seed            INTEGER NOT NULL DEFAULT 0,
    width           INTEGER NOT NULL DEFAULT 0,
    height          INTEGER NOT NULL DEFAULT 0,
    file_size       INTEGER NOT NULL DEFAULT 0,
    generation_time REAL    NOT NULL DEFAULT 0.0,
    negative_prompt TEXT,
    error           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    published_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_prompt_hash ON images(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);

-- Pin log / analytics
CREATE TABLE IF NOT EXISTS pins (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    pinterest_pin_id TEXT    NOT NULL,
    image_id         INTEGER NOT NULL REFERENCES images(id),
    board_id         TEXT    NOT NULL DEFAULT '',
    url              TEXT    NOT NULL DEFAULT '',
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    saves            INTEGER NOT NULL DEFAULT 0,
    clicks           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pins_pinterest_id ON pins(pinterest_pin_id);

-- Analytics events
CREATE TABLE IF NOT EXISTS analytics_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pin_id     TEXT    NOT NULL,
    event_type TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_analytics_pin_id ON analytics_events(pin_id);
CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type);

-- Publication log
CREATE TABLE IF NOT EXISTS publications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id         INTEGER NOT NULL REFERENCES images(id),
    board_id         TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    description      TEXT    NOT NULL DEFAULT '',
    tags             TEXT    NOT NULL DEFAULT '',
    published_at     TEXT,
    pinterest_pin_id TEXT,
    status           TEXT    NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'published', 'failed')),
    error            TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_publications_image_id ON publications(image_id);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status);
"""


class ConnectionManager:
    """Manages a SQLite connection with schema auto-initialization.

    Usage::

        with ConnectionManager("data/app.db") as cm:
            cm.execute("SELECT 1")

    Supports ``:memory:`` for testing.
    """

    def __init__(self, db_path: str = "data/pinterest_agent.db") -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Open (or return existing) connection and ensure schema is applied."""
        if self._conn is not None:
            return self._conn

        # Ensure parent directory exists for file-based databases
        if self._db_path != ":memory:":
            parent = Path(self._db_path).parent
            parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

        self._init_schema()

        return self._conn

    def close(self) -> None:
        """Close the connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for atomic transactions.

        Commits on success, rolls back on exception.
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query on the managed connection."""
        return self.connect().execute(sql, params)

    def executemany(self, sql: str, seq: list[tuple]) -> sqlite3.Cursor:
        """Execute a parameterized query against a sequence of parameters."""
        return self.connect().executemany(sql, seq)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Apply schema and run incremental migrations."""
        assert self._conn is not None
        current = self._get_schema_version()

        if current < 1:
            # Fresh database — apply full initial schema (already at v2)
            self._conn.executescript(SCHEMA_SQL)
            self._conn.execute(
                "INSERT INTO _schema_version (version) VALUES (2)",
            )
            return

        # --- Incremental migrations for existing databases ---

        if current == 1:
            # Migration v1 → v2: add variable_seed column
            try:
                self._conn.execute(
                    "ALTER TABLE prompts ADD COLUMN variable_seed INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column may already exist
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prompts_template_seed ON prompts(template_id, variable_seed)"
            )
            self._conn.execute(
                "INSERT INTO _schema_version (version) VALUES (2)",
            )
            current = 2

        if current == 2:
            # Migration v2 → v3: add new columns + update CHECK constraint on images
            # Drop dependent tables first (safe — pre-release, no real data)
            self._conn.execute("DROP TABLE IF EXISTS analytics_events")
            self._conn.execute("DROP TABLE IF EXISTS pins")
            self._conn.execute("DROP TABLE IF EXISTS images")

            self._conn.execute(
                """CREATE TABLE images (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id       INTEGER NOT NULL REFERENCES prompts(id),
                    prompt_hash     TEXT    NOT NULL DEFAULT '',
                    phash           TEXT    NOT NULL DEFAULT '',
                    sha256          TEXT    NOT NULL DEFAULT '',
                    file_path       TEXT    NOT NULL DEFAULT '',
                    status          TEXT    NOT NULL DEFAULT 'pending'
                                            CHECK (status IN ('pending', 'generated', 'published', 'failed')),
                    pin_id          TEXT,
                    niche           TEXT    NOT NULL DEFAULT '',
                    backend         TEXT    NOT NULL DEFAULT '',
                    seed            INTEGER NOT NULL DEFAULT 0,
                    width           INTEGER NOT NULL DEFAULT 0,
                    height          INTEGER NOT NULL DEFAULT 0,
                    file_size       INTEGER NOT NULL DEFAULT 0,
                    generation_time REAL    NOT NULL DEFAULT 0.0,
                    negative_prompt TEXT,
                    error           TEXT,
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                    published_at    TEXT
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_status ON images(status)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_prompt_hash ON images(prompt_hash)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256)"
            )

            # Recreate pins + analytics_events
            self._conn.execute(
                """CREATE TABLE pins (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    pinterest_pin_id TEXT    NOT NULL,
                    image_id         INTEGER NOT NULL REFERENCES images(id),
                    board_id         TEXT    NOT NULL DEFAULT '',
                    url              TEXT    NOT NULL DEFAULT '',
                    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                    saves            INTEGER NOT NULL DEFAULT 0,
                    clicks           INTEGER NOT NULL DEFAULT 0
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pins_pinterest_id ON pins(pinterest_pin_id)"
            )
            self._conn.execute(
                """CREATE TABLE analytics_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    pin_id     TEXT    NOT NULL,
                    event_type TEXT    NOT NULL,
                    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_pin_id ON analytics_events(pin_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type)"
            )

            self._conn.execute(
                "INSERT INTO _schema_version (version) VALUES (3)",
            )
            current = 3

        if current == 3:
            # Migration v3 → v4: add publications table
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS publications (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id         INTEGER NOT NULL REFERENCES images(id),
                    board_id         TEXT    NOT NULL,
                    title            TEXT    NOT NULL,
                    description      TEXT    NOT NULL DEFAULT '',
                    tags             TEXT    NOT NULL DEFAULT '',
                    published_at     TEXT,
                    pinterest_pin_id TEXT,
                    status           TEXT    NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'published', 'failed')),
                    error            TEXT,
                    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publications_image_id ON publications(image_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status)"
            )
            self._conn.execute(
                "INSERT INTO _schema_version (version) VALUES (4)",
            )
            current = 4

        self._conn.commit()

    def _get_schema_version(self) -> int:
        """Return current schema version, or 0 if not yet initialized."""
        assert self._conn is not None
        try:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM _schema_version"
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0

    def __enter__(self) -> ConnectionManager:
        self.connect()
        return self

    def __exit__(self, *exc_args: object) -> None:
        self.close()

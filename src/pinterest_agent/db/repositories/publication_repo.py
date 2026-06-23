"""SQLite implementation of PublicationRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.domain.models import PublicationRecord, PublicationStatus
from pinterest_agent.domain.repositories import PublicationRepository

_SELECT_COLS = (
    "id, image_id, board_id, title, description, tags, "
    "published_at, pinterest_pin_id, status, error, created_at"
)


class SqlitePublicationRepository(PublicationRepository):
    """Concrete SQLite implementation of the PublicationRepository interface.

    Stores publication records in the ``publications`` table with status
    tracking for pin publishing attempts.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._cm = connection_manager

    # ------------------------------------------------------------------
    # PublicationRepository interface
    # ------------------------------------------------------------------

    def save(self, record: PublicationRecord) -> int:
        """Insert a new publication record and return its row ID."""
        cursor = self._cm.execute(
            """INSERT INTO publications
               (image_id, board_id, title, description, tags,
                published_at, pinterest_pin_id, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.image_id,
                record.board_id,
                record.title,
                record.description,
                record.tags,
                record.published_at.isoformat() if record.published_at else None,
                record.pinterest_pin_id,
                record.status.value,
                record.error,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def find_by_image_id(self, image_id: int) -> Optional[PublicationRecord]:
        """Find a publication record by image ID."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM publications WHERE image_id = ? ORDER BY id DESC LIMIT 1",
            (image_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def find_by_pinterest_pin_id(self, pin_id: str) -> Optional[PublicationRecord]:
        """Find a publication record by Pinterest pin ID."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM publications WHERE pinterest_pin_id = ?",
            (pin_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def query(
        self,
        status: Optional[PublicationStatus] = None,
        limit: int = 100,
    ) -> list[PublicationRecord]:
        """Query publication records by optional status filter."""
        conditions: list[str] = []
        params: list = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM publications {where_clause} ORDER BY id ASC LIMIT ?",
            tuple(params) + (limit,),
        ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def count_by_status(self, status: PublicationStatus) -> int:
        """Return count of records with the given status."""
        row = self._cm.execute(
            "SELECT COUNT(*) FROM publications WHERE status = ?",
            (status.value,),
        ).fetchone()
        return row[0] if row else 0

    def count_published_today(self) -> int:
        """Return number of successful publications today."""
        row = self._cm.execute(
            """SELECT COUNT(*) FROM publications
               WHERE status = ? AND date(published_at) = date('now')""",
            (PublicationStatus.PUBLISHED.value,),
        ).fetchone()
        return row[0] if row else 0

    def mark_failed(self, record_id: int, error: str) -> None:
        """Mark a publication record as failed with error message."""
        self._cm.execute(
            "UPDATE publications SET status = ?, error = ? WHERE id = ?",
            (PublicationStatus.FAILED.value, error, record_id),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> PublicationRecord:  # type: ignore[name-defined]  # noqa: F821
        """Convert a SQLite row to a PublicationRecord dataclass."""
        published_at = row["published_at"]
        error = row["error"]
        return PublicationRecord(
            id=row["id"],
            image_id=row["image_id"],
            board_id=row["board_id"],
            title=row["title"],
            description=row["description"],
            tags=row["tags"],
            published_at=datetime.fromisoformat(published_at) if published_at else None,
            pinterest_pin_id=row["pinterest_pin_id"],
            status=PublicationStatus(row["status"]),
            error=error if error else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

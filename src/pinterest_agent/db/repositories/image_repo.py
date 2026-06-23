"""SQLite implementation of ImageRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.domain.models import ImageRecord, ImageStatus
from pinterest_agent.domain.repositories import ImageRepository

_SELECT_COLS = (
    "id, prompt_id, prompt_hash, phash, sha256, file_path, "
    "status, pin_id, niche, backend, seed, width, height, "
    "file_size, generation_time, negative_prompt, error, "
    "created_at, published_at"
)


class SqliteImageRepository(ImageRepository):
    """Concrete SQLite implementation of the ImageRepository interface.

    Stores image metadata in the ``images`` table with status tracking
    and dedup support via prompt_hash, phash, and sha256 columns.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._cm = connection_manager

    # ------------------------------------------------------------------
    # ImageRepository interface
    # ------------------------------------------------------------------

    def save(self, image: ImageRecord) -> int:
        """Insert a new image record and return its auto-generated ID."""
        cursor = self._cm.execute(
            """INSERT INTO images
               (prompt_id, prompt_hash, phash, sha256, file_path,
                status, pin_id, niche, backend, seed,
                width, height, file_size, generation_time,
                negative_prompt, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                image.prompt_id,
                image.prompt_hash,
                image.phash,
                image.sha256,
                image.file_path,
                image.status.value,
                image.pin_id,
                image.niche,
                image.backend,
                image.seed,
                image.width,
                image.height,
                image.file_size,
                image.generation_time,
                image.negative_prompt,
                image.error,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def find_by_prompt_hash(self, prompt_hash: str) -> Optional[ImageRecord]:
        """Look up an image by the source prompt hash."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images WHERE prompt_hash = ?",
            (prompt_hash,),
        ).fetchone()
        return self._row_to_image(row) if row else None

    def find_by_perceptual_hash(self, phash: str) -> Optional[ImageRecord]:
        """Look up an image by its perceptual hash (for image dedup)."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images WHERE phash = ?",
            (phash,),
        ).fetchone()
        return self._row_to_image(row) if row else None

    def find_by_prompt_id(self, prompt_id: int) -> Optional[ImageRecord]:
        """Look up the most recent image by its source prompt ID."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images WHERE prompt_id = ? ORDER BY id DESC LIMIT 1",
            (prompt_id,),
        ).fetchone()
        return self._row_to_image(row) if row else None

    def find_by_sha256(self, sha256: str) -> Optional[ImageRecord]:
        """Look up an image by its SHA256 content hash (for exact dedup)."""
        row = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        return self._row_to_image(row) if row else None

    def query(
        self,
        status: Optional[str] = None,
        niche: Optional[str] = None,
        limit: int = 100,
    ) -> list[ImageRecord]:
        """Query images by optional status and niche filters.

        Args:
            status: Filter by status string ('pending', 'generated', 'failed').
            niche: Filter by aesthetic niche.
            limit: Maximum rows to return.

        Returns images ordered by id ASC.
        """
        conditions: list[str] = []
        params: list = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if niche is not None:
            conditions.append("niche = ?")
            params.append(niche)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images {where} ORDER BY id ASC LIMIT ?",
            tuple(params) + (limit,),
        ).fetchall()

        return [self._row_to_image(row) for row in rows]

    def find_unpublished(self, limit: int = 10) -> list[ImageRecord]:
        """Fetch next batch of unpublished (pending) images in FIFO order."""
        rows = self._cm.execute(
            f"SELECT {_SELECT_COLS} FROM images WHERE status = ? ORDER BY id ASC LIMIT ?",
            (ImageStatus.PENDING.value, limit),
        ).fetchall()
        return [self._row_to_image(row) for row in rows]

    def mark_published(self, image_id: int, pin_id: str) -> None:
        """Transition an image to 'published' with its Pinterest pin ID."""
        self._cm.execute(
            """UPDATE images
               SET status = ?, pin_id = ?, published_at = datetime('now')
               WHERE id = ?""",
            (ImageStatus.PUBLISHED.value, pin_id, image_id),
        )

    def count_by_status(self, status: str) -> int:
        """Return count of images with the given status string.

        Args:
            status: One of 'pending', 'generated', 'published', 'failed'.
        """
        row = self._cm.execute(
            "SELECT COUNT(*) FROM images WHERE status = ?",
            (status,),
        ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_image(row: sqlite3.Row) -> ImageRecord:  # type: ignore[name-defined]  # noqa: F821
        """Convert a SQLite row to an ImageRecord dataclass."""
        published_at = row["published_at"]
        negative_prompt = row["negative_prompt"]
        error = row["error"]
        return ImageRecord(
            id=row["id"],
            prompt_id=row["prompt_id"],
            prompt_hash=row["prompt_hash"],
            phash=row["phash"],
            sha256=row["sha256"],
            file_path=row["file_path"],
            status=ImageStatus(row["status"]),
            pin_id=row["pin_id"],
            niche=row["niche"],
            backend=row["backend"],
            seed=row["seed"],
            width=row["width"],
            height=row["height"],
            file_size=row["file_size"],
            generation_time=row["generation_time"],
            negative_prompt=negative_prompt if negative_prompt else None,
            error=error if error else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            published_at=datetime.fromisoformat(published_at) if published_at else None,
        )

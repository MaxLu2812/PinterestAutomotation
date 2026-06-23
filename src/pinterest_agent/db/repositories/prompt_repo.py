"""SQLite implementation of PromptRepository."""

from __future__ import annotations

import json
from typing import Optional

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.domain.models import Prompt, PromptStatus
from pinterest_agent.domain.repositories import PromptRepository

_SELECT_COLS = (
    "id, aesthetic, template_id, variables, variable_seed, text, status, created_at, error"
)


class SqlitePromptRepository(PromptRepository):
    """Concrete SQLite implementation of the PromptRepository interface.

    Stores prompts in the ``prompts`` table with status tracking.
    Uses JSON serialization for the ``variables`` dict column.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._cm = connection_manager

    # ------------------------------------------------------------------
    # PromptRepository interface
    # ------------------------------------------------------------------

    def enqueue(self, prompt: Prompt) -> int:
        """Insert a new prompt and return its auto-generated ID."""
        cursor = self._cm.execute(
            """INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                prompt.aesthetic,
                prompt.template_id,
                json.dumps(prompt.variables),
                prompt.variable_seed,
                prompt.text,
                prompt.status.value,
                prompt.error,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def dequeue(self, limit: int = 10) -> list[Prompt]:
        """Fetch next batch of pending prompts in FIFO order."""
        rows = self._cm.execute(
            f"""SELECT {_SELECT_COLS}
                FROM prompts
                WHERE status = ?
                ORDER BY id ASC
                LIMIT ?""",
            (PromptStatus.PENDING.value, limit),
        ).fetchall()

        return [self._row_to_prompt(row) for row in rows]

    def mark_done(self, prompt_id: int) -> None:
        """Transition a prompt to 'generated' status."""
        self._cm.execute(
            "UPDATE prompts SET status = ? WHERE id = ?",
            (PromptStatus.GENERATED.value, prompt_id),
        )

    def mark_failed(self, prompt_id: int, error: str) -> None:
        """Transition a prompt to 'failed' status with error message."""
        self._cm.execute(
            "UPDATE prompts SET status = ?, error = ? WHERE id = ?",
            (PromptStatus.FAILED.value, error, prompt_id),
        )

    def count_by_status(self, status: PromptStatus) -> int:
        """Return count of prompts in the given status."""
        row = self._cm.execute(
            "SELECT COUNT(*) FROM prompts WHERE status = ?",
            (status.value,),
        ).fetchone()
        return row[0] if row else 0

    def find_by_hash(self, prompt_hash: str) -> Optional[Prompt]:
        """Look up a prompt by its text hash (for dedup)."""
        row = self._cm.execute(
            f"""SELECT {_SELECT_COLS}
                FROM prompts
                WHERE text = ?""",
            (prompt_hash,),
        ).fetchone()

        return self._row_to_prompt(row) if row else None

    def find_by_template_and_seed(
        self, template_id: str, variable_seed: int
    ) -> Optional[Prompt]:
        """Look up a prompt by template_id + variable_seed (for dedup).

        Returns the first matching prompt or None.
        """
        row = self._cm.execute(
            f"""SELECT {_SELECT_COLS}
                FROM prompts
                WHERE template_id = ? AND variable_seed = ?
                ORDER BY id ASC
                LIMIT 1""",
            (template_id, variable_seed),
        ).fetchone()

        return self._row_to_prompt(row) if row else None

    def query(
        self,
        status: Optional[PromptStatus] = None,
        niche: Optional[str] = None,
        limit: int = 100,
    ) -> list[Prompt]:
        """Query prompts by optional status and niche filters.

        Returns prompts ordered by id ASC (FIFO).
        """
        conditions: list[str] = []
        params: list = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if niche is not None:
            conditions.append("aesthetic = ?")
            params.append(niche)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = self._cm.execute(
            f"""SELECT {_SELECT_COLS}
                FROM prompts
                {where_clause}
                ORDER BY id ASC
                LIMIT ?""",
            tuple(params) + (limit,),
        ).fetchall()

        return [self._row_to_prompt(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_prompt(row: sqlite3.Row) -> Prompt:  # type: ignore[name-defined]  # noqa: F821
        """Convert a SQLite row to a Prompt dataclass."""
        from datetime import datetime

        return Prompt(
            id=row["id"],
            aesthetic=row["aesthetic"],
            template_id=row["template_id"],
            variables=json.loads(row["variables"]) if row["variables"] else {},
            variable_seed=row["variable_seed"],
            text=row["text"],
            status=PromptStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            error=row["error"],
        )

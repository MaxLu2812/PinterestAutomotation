"""SQLite implementation of AnalyticsRepository."""

from __future__ import annotations

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.domain.repositories import AnalyticsRepository


class SqliteAnalyticsRepository(AnalyticsRepository):
    """Concrete SQLite implementation of the AnalyticsRepository interface.

    Tracks pin events (saves, clicks) and provides aggregate performance
    queries for templates and niches.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._cm = connection_manager

    # ------------------------------------------------------------------
    # AnalyticsRepository interface
    # ------------------------------------------------------------------

    def record_pin_event(self, pin_id: str, event_type: str) -> None:
        """Record an analytics event for a pin.

        Args:
            pin_id: The Pinterest pin ID string.
            event_type: Event type (e.g. 'save', 'click').

        The ``pins`` table counters are also updated atomically:
            - ``saves`` incremented when event_type is 'save'.
            - ``clicks`` incremented when event_type is 'click'.
        """
        self._cm.execute(
            "INSERT INTO analytics_events (pin_id, event_type) VALUES (?, ?)",
            (pin_id, event_type),
        )

        # Update aggregate counters on the pins table
        if event_type == "save":
            self._cm.execute(
                "UPDATE pins SET saves = saves + 1 WHERE pinterest_pin_id = ?",
                (pin_id,),
            )
        elif event_type == "click":
            self._cm.execute(
                "UPDATE pins SET clicks = clicks + 1 WHERE pinterest_pin_id = ?",
                (pin_id,),
            )

    def get_top_templates(self, limit: int = 10) -> list[dict]:
        """Return top-performing templates by total saves across all pins.

        Each result dict contains::

            {
                "template_id": str,
                "total_pins": int,
                "total_saves": int,
                "total_clicks": int,
            }
        """
        rows = self._cm.execute(
            """SELECT p.template_id,
                      COUNT(DISTINCT pin.id)        AS total_pins,
                      COALESCE(SUM(pin.saves), 0)   AS total_saves,
                      COALESCE(SUM(pin.clicks), 0)  AS total_clicks
               FROM pins pin
               JOIN images img ON img.id = pin.image_id
               JOIN prompts p  ON p.id = img.prompt_id
               GROUP BY p.template_id
               ORDER BY total_saves DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    def get_niche_performance(self, niche: str) -> dict:
        """Return aggregate performance metrics for a specific niche.

        Returns a dict with keys:
            - ``niche``: the requested niche name.
            - ``total_pins``: total published pins.
            - ``total_saves``: sum of saves across pins.
            - ``total_clicks``: sum of clicks across pins.
            - ``total_images``: total images generated for this niche.
        """
        row = self._cm.execute(
            """SELECT
                      ?                                              AS niche,
                      COUNT(DISTINCT pin.id)                         AS total_pins,
                      COALESCE(SUM(pin.saves), 0)                   AS total_saves,
                      COALESCE(SUM(pin.clicks), 0)                  AS total_clicks,
                      (SELECT COUNT(*) FROM images WHERE niche = ?) AS total_images
               FROM pins pin
               JOIN images img ON img.id = pin.image_id
               WHERE img.niche = ?""",
            (niche, niche, niche),
        ).fetchone()

        return dict(row) if row else {"niche": niche, "total_pins": 0, "total_saves": 0, "total_clicks": 0, "total_images": 0}

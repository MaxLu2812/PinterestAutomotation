"""ConstraintEngine — filter component options based on scene constraints.

Constraint rules restrict which component values are available based on
previously selected component values.  Typical use: if the selected
outfit is swimwear, only allow beach/pool backgrounds.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConstraintEngine:
    """Filter component options by applying YAML-defined constraints."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def apply(
        component_name: str,
        component_def: dict[str, Any],
        selected_components: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Return filtered options based on constraints.

        Parameters
        ----------
        component_name:
            Name of the component being processed (unused in this
            implementation but available for subclasses).
        component_def:
            The full component definition from YAML, which may contain
            a ``constraints`` key.
        selected_components:
            Already-selected component values, e.g.
            ``{"outfit": "cream cashmere sweater"}``.

        Returns
        -------
        Filtered list of option dicts.  If no constraints match or the
        component has no constraints, returns the full options list.
        """
        options: list[dict[str, Any]] = list(component_def.get("options", []))
        constraints: list[dict[str, Any]] = component_def.get("constraints", [])

        if not constraints:
            return options

        for constraint in constraints:
            condition: dict = constraint.get("if", {})
            action: dict = constraint.get("then", {})

            if not condition or not action:
                continue

            if ConstraintEngine._condition_met(condition, selected_components):
                only_values: list[str] = action.get("only", [])
                if only_values:
                    filtered = [
                        opt
                        for opt in options
                        if ConstraintEngine._option_matches(opt["value"], only_values)
                    ]
                    if filtered:
                        options = filtered
                    else:
                        # If the constraint would remove ALL options, keep
                        # originals and log a warning rather than returning
                        # an empty list.
                        logger.warning(
                            "Constraint for '%s' would remove all options — "
                            "keeping originals. Condition=%s",
                            component_name,
                            condition,
                        )

        return options

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _condition_met(
        condition: dict[str, Any],
        selected: dict[str, str],
    ) -> bool:
        """Evaluate whether a constraint condition matches selections.

        Supported condition keys (extensible):

        - ``outfit_contains``: check if the selected outfit value
          contains the given substring (or any in a list).
        """
        for cond_key, cond_val in condition.items():
            if cond_key == "outfit_contains":
                outfit = selected.get("outfit", "")
                if not outfit:
                    return False

                if isinstance(cond_val, str):
                    if cond_val.lower() in outfit.lower():
                        return True
                elif isinstance(cond_val, list):
                    if any(v.lower() in outfit.lower() for v in cond_val):
                        return True
                else:
                    logger.warning("Unsupported condition value type: %s", type(cond_val))
            else:
                logger.debug("Unknown condition key: %s — skipping", cond_key)

        return False

    @staticmethod
    def _option_matches(option_value: str, only_values: list[str]) -> bool:
        """Check if an option value matches any of the *only_values* list.

        Uses substring matching (case-insensitive) in both directions so
        that short keys like ``"cafe"`` match descriptive values like
        ``"luxury cafe with natural light"``.
        """
        opt_lower = option_value.lower()
        for val in only_values:
            val_lower = val.lower().replace("_", " ")
            if val_lower in opt_lower or opt_lower in val_lower:
                return True
        return False

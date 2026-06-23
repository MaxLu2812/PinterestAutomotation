"""BiasResolver — applies archetype bias weights to component options.

Archetype biases adjust the probability of certain values for specific
components.  Biases are **multiplied** with base weights, not replaced.
An archetype can make a choice 3× more likely but never force it to 100%.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEPRIORITIZE_FACTOR = 0.1


class BiasResolver:
    """Resolve archetype bias weights against component definitions."""

    @staticmethod
    def apply(
        options: list[dict[str, Any]],
        biases: dict[str, dict[str, float]] | None,
        component_name: str,
    ) -> list[dict[str, Any]]:
        """Multiply base weights by archetype biases for *component_name*.

        Parameters
        ----------
        options:
            List of ``{"value": str, "weight": number}`` dicts (already
            filtered by constraints).
        biases:
            Archetype bias map, e.g.
            ``{"outfit": {"cashmere": 40, "blazer": 30}}``.
            May be ``None`` or not contain this component.
        component_name:
            The current component being processed.

        Returns
        -------
        New list of option dicts with adjusted weights.  The original
        list is not mutated.

        Algorithm
        ---------
        - If *biases* has an entry for this component:
          - If the option value exists in the bias map:
            ``new_weight = base_weight * bias_weight / 100``
          - If the option value is **not** in the bias map:
            ``new_weight = base_weight * 0.1`` (deprioritise)
        - No bias at all for this component → keep base weight.
        """
        if not biases:
            return list(options)

        component_biases = biases.get(component_name, {})
        if not component_biases:
            return list(options)

        result: list[dict[str, Any]] = []
        for opt in options:
            value = opt["value"]
            base_weight = float(opt["weight"])

            if value in component_biases:
                bias_pct = float(component_biases[value])
                new_weight = base_weight * bias_pct / 100.0
            else:
                new_weight = base_weight * _DEPRIORITIZE_FACTOR

            result.append({"value": value, "weight": new_weight})

        return result

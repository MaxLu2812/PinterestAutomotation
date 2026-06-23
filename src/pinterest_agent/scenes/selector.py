"""WeightedSelector — deterministic weighted random selection.

Uses pure Python ``random.Random(seed)`` — no numpy dependency.
"""

from __future__ import annotations

import random


def _stable_hash(s: str) -> int:
    """Deterministic string hash stable across Python runs and versions.

    Uses the classic Java String hashCode algorithm:
        h = s[0]*31^{n-1} + s[1]*31^{n-2} + ... + s[n-1]
    Masked to 32-bit unsigned.
    """
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h


class WeightedSelector:
    """Deterministic weighted random value picker."""

    @staticmethod
    def select(options: list[dict], seed: int) -> str:
        """Pick one value from *options* using weighted random with *seed*.

        Parameters
        ----------
        options:
            List of ``{"value": str, "weight": number}`` dicts.
        seed:
            Integer seed for deterministic selection.

        Returns
        -------
        The ``value`` string of the selected option.
        """
        if not options:
            raise ValueError("WeightedSelector.select() called with empty options")

        total = sum(opt["weight"] for opt in options)
        if total <= 0:
            raise ValueError("WeightedSelector.select() called with non-positive total weight")

        rng = random.Random(seed)
        r = rng.random() * total

        cumulative = 0.0
        for opt in options:
            cumulative += opt["weight"]
            if r <= cumulative:
                return opt["value"]

        # Fallback in case of floating-point edge case
        return options[-1]["value"]

    @staticmethod
    def component_seed(base_seed: int, component_name: str) -> int:
        """Derive a per-component seed that is stable and independent.

        Uses ``_stable_hash`` so the same base_seed + component_name
        always produces the same child seed across Python processes.
        """
        return base_seed + _stable_hash(component_name)

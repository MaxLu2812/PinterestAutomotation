"""SceneComposer — procedural, constraint-driven scene generation engine.

Generates millions of unique, coherent prompts without any LLM
dependency.  Coexists with the existing ``prompts/engine.py``.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pinterest_agent.scenes.bias import BiasResolver
from pinterest_agent.scenes.constraints import ConstraintEngine
from pinterest_agent.scenes.renderer import SceneRenderer
from pinterest_agent.scenes.selector import WeightedSelector

logger = logging.getLogger(__name__)

_DEFAULT_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


@dataclass
class Scene:
    """Complete output of a SceneComposer generation.

    Attributes
    ----------
    niche:
        The aesthetic niche (e.g. ``"old_money"``).
    archetype:
        The archetype used (e.g. ``"old_money_student"``).
    seed:
        The base seed used for deterministic generation.
    components:
        Mapping of component name → selected value string.
    prompt:
        Fully rendered, fluent prompt string.
    negative_prompt:
        Context-aware negative prompt string.
    weights_used:
        For analytics/debug — component → {value → final weight}.
    constraints_applied:
        List of human-readable constraint descriptions that fired.
    """

    niche: str
    archetype: str
    seed: int
    components: dict[str, str] = field(default_factory=dict)
    prompt: str = ""
    negative_prompt: str = ""
    weights_used: dict[str, dict[str, float]] = field(default_factory=dict)
    constraints_applied: list[str] = field(default_factory=list)


class SceneComposer:
    """Orchestrates procedural scene generation from YAML definitions.

    Usage
    -----
    >>> composer = SceneComposer()
    >>> scene = composer.generate("old_money", "old_money_student", seed=42)
    >>> scene.prompt
    'Elegant woman ... '
    """

    def __init__(
        self,
        definitions_dir: str | Path | None = None,
    ) -> None:
        """Load YAML definitions from *definitions_dir*.

        Defaults to ``scenes/definitions/`` next to this file.
        """
        self._definitions_dir = Path(definitions_dir or _DEFAULT_DEFINITIONS_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        niche: str,
        archetype: str | None = None,
        seed: int = 42,
    ) -> Scene:
        """Generate a complete scene for *niche*.

        Parameters
        ----------
        niche:
            Aesthetic niche name matching a ``{niche}.yaml`` definition.
        archetype:
            Archetype within the niche.  If ``None``, a random archetype
            is chosen using *seed*.
        seed:
            Base deterministic seed for all random choices.

        Returns
        -------
        A fully populated ``Scene`` dataclass.
        """
        # 1. Load YAML definition
        definition = self._load_definition(niche)

        # 2. Resolve archetype
        archetypes: dict[str, Any] = definition.get("archetypes", {})
        archetype_names = list(archetypes.keys())

        if not archetype_names:
            raise ValueError(f"Niche '{niche}' has no archetypes defined")

        if archetype is None:
            rng = random.Random(seed)
            archetype = rng.choice(archetype_names)

        if archetype not in archetypes:
            raise ValueError(
                f"Unknown archetype '{archetype}' for niche '{niche}'. "
                f"Available: {', '.join(archetype_names)}"
            )

        archetype_def = archetypes[archetype]
        biases: dict[str, dict[str, float]] = archetype_def.get("biases", {})

        # 3. Process each component
        components: dict[str, str] = {}
        weights_used: dict[str, dict[str, float]] = {}
        constraints_applied: list[str] = []

        component_defs: dict[str, Any] = definition.get("components", {})

        for comp_name, comp_def in component_defs.items():
            # a) Get base options
            options: list[dict[str, Any]] = list(comp_def.get("options", []))

            # b) Apply constraints (filters options based on previous picks)
            if "constraints" in comp_def:
                pre_count = len(options)
                filtered = ConstraintEngine.apply(comp_name, comp_def, components)
                if len(filtered) < pre_count:
                    constraints_applied.append(
                        f"{comp_name}: constrained ({pre_count} → {len(filtered)} options)"
                    )
                options = filtered

            # c) Apply archetype biases
            biased = BiasResolver.apply(options, biases, comp_name)

            # d) Select weighted-random with deterministic per-component seed
            comp_seed = WeightedSelector.component_seed(seed, comp_name)
            selected = WeightedSelector.select(biased, comp_seed)

            components[comp_name] = selected
            weights_used[comp_name] = {opt["value"]: opt["weight"] for opt in biased}

        # 4. Render scene prompt
        prompt = SceneRenderer.render(components)

        # 5. Build negative prompt
        negative_prompt = SceneRenderer.build_negative_prompt(components)

        return Scene(
            niche=niche,
            archetype=archetype,
            seed=seed,
            components=components,
            prompt=prompt,
            negative_prompt=negative_prompt,
            weights_used=weights_used,
            constraints_applied=constraints_applied,
        )

    def list_niches(self) -> list[str]:
        """Return available niche names (file stems without extension)."""
        if not self._definitions_dir.is_dir():
            return []
        return sorted(
            p.stem
            for p in self._definitions_dir.iterdir()
            if p.suffix in (".yaml", ".yml")
        )

    def list_archetypes(self, niche: str) -> list[str]:
        """Return available archetype names for *niche*."""
        definition = self._load_definition(niche)
        return list(definition.get("archetypes", {}).keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_definition(self, niche: str) -> dict[str, Any]:
        """Load a YAML definition by its stem name (e.g. ``'old_money'``)."""
        if not self._definitions_dir.is_dir():
            raise FileNotFoundError(
                f"Definitions directory not found: {self._definitions_dir}"
            )

        candidates = [
            self._definitions_dir / f"{niche}.yaml",
            self._definitions_dir / f"{niche}.yml",
        ]
        for path in candidates:
            if path.is_file():
                with path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    raise ValueError(
                        f"Definition '{niche}' is not a valid YAML mapping"
                    )
                return data

        raise FileNotFoundError(
            f"Definition '{niche}' not found in {self._definitions_dir}. "
            f"Available: {', '.join(self.list_niches())}"
        )

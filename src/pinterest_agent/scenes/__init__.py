"""Procedural SceneComposer — constraint-driven scene generation.

Replaces flat YAML template variables with weighted, constraint-driven
procedural scene generation.  Coexists with ``prompts/engine.py``.
"""

from __future__ import annotations

from pinterest_agent.scenes.composer import Scene, SceneComposer
from pinterest_agent.scenes.selector import WeightedSelector
from pinterest_agent.scenes.bias import BiasResolver
from pinterest_agent.scenes.constraints import ConstraintEngine
from pinterest_agent.scenes.renderer import SceneRenderer

__all__ = [
    "SceneComposer",
    "Scene",
    "WeightedSelector",
    "BiasResolver",
    "ConstraintEngine",
    "SceneRenderer",
]

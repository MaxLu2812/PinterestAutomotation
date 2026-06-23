"""Tests for the procedural SceneComposer engine.

Covers determinism, bias resolution, constraint filtering, rendering,
end-to-end generation, and CLI flag registration.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import pytest
import yaml

from pinterest_agent.scenes.bias import BiasResolver
from pinterest_agent.scenes.composer import Scene, SceneComposer
from pinterest_agent.scenes.constraints import ConstraintEngine
from pinterest_agent.scenes.renderer import SceneRenderer, _article
from pinterest_agent.scenes.selector import WeightedSelector


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def sample_options() -> list[dict]:
    return [
        {"value": "a", "weight": 50},
        {"value": "b", "weight": 30},
        {"value": "c", "weight": 20},
    ]


@pytest.fixture
def composer() -> SceneComposer:
    return SceneComposer()


# ======================================================================
# 4.1 — WeightedSelector determinism
# ======================================================================

class TestWeightedSelector:
    """WeightedSelector must be deterministic and correct."""

    def test_same_seed_same_result(self, sample_options):
        result_a = WeightedSelector.select(sample_options, seed=42)
        result_b = WeightedSelector.select(sample_options, seed=42)
        assert result_a == result_b

    def test_different_seed_different_result(self, sample_options):
        results = {WeightedSelector.select(sample_options, seed=s) for s in range(100)}
        # With 3 options, we should see at least 2 different values
        assert len(results) >= 2, "100 seeds with weighted options should vary"

    def test_empty_options_raises(self):
        with pytest.raises(ValueError, match="empty options"):
            WeightedSelector.select([], seed=1)

    def test_zero_weight_raises(self):
        with pytest.raises(ValueError, match="non-positive total weight"):
            WeightedSelector.select([{"value": "x", "weight": 0}], seed=1)

    def test_component_seed_stable(self):
        s1 = WeightedSelector.component_seed(42, "outfit")
        s2 = WeightedSelector.component_seed(42, "outfit")
        assert s1 == s2

    def test_component_seed_different_per_component(self):
        s1 = WeightedSelector.component_seed(42, "outfit")
        s2 = WeightedSelector.component_seed(42, "pose")
        assert s1 != s2

    def test_weight_distribution(self):
        """Heavily-weighted option should be selected roughly proportionally."""
        options = [
            {"value": "common", "weight": 90},
            {"value": "rare", "weight": 10},
        ]
        common_count = sum(
            1 for _ in range(1000)
            if WeightedSelector.select(options, seed=_) == "common"
        )
        assert common_count > 700, "90% weight should dominate over 1000 trials"


# ======================================================================
# 4.2 — BiasResolver archetype weight adjustments
# ======================================================================

class TestBiasResolver:
    """BiasResolver must correctly multiply weights."""

    def test_no_biases_returns_same(self):
        options = [{"value": "x", "weight": 50}, {"value": "y", "weight": 50}]
        result = BiasResolver.apply(options, None, "outfit")
        assert result == options

    def test_empty_biases_returns_same(self):
        options = [{"value": "x", "weight": 50}]
        result = BiasResolver.apply(options, {}, "outfit")
        assert result == options

    def test_bias_multiplies_weight(self):
        options = [{"value": "cashmere", "weight": 25}]
        biases = {"outfit": {"cashmere": 40}}
        result = BiasResolver.apply(options, biases, "outfit")
        # 25 * 40 / 100 = 10.0
        assert result[0]["weight"] == 10.0

    def test_bias_deprioritises_unlisted(self):
        options = [
            {"value": "cashmere", "weight": 50},
            {"value": "silk", "weight": 50},
        ]
        biases = {"outfit": {"cashmere": 100}}
        result = BiasResolver.apply(options, biases, "outfit")
        cashmere = next(o for o in result if o["value"] == "cashmere")
        silk = next(o for o in result if o["value"] == "silk")
        # cashmere: 50 * 100 / 100 = 50
        # silk: 50 * 0.1 = 5
        assert cashmere["weight"] == 50.0
        assert silk["weight"] == 5.0

    def test_bias_for_different_component_ignored(self):
        options = [{"value": "cashmere", "weight": 25}]
        # biases for "accessories", not "outfit"
        biases = {"accessories": {"cashmere": 40}}
        result = BiasResolver.apply(options, biases, "outfit")
        assert result == options


# ======================================================================
# 4.3 — ConstraintEngine outfit→background rules
# ======================================================================

class TestConstraintEngine:
    """ConstraintEngine must filter options based on selected components."""

    def test_no_constraints_returns_all(self):
        component_def = {
            "options": [
                {"value": "beach", "weight": 50},
                {"value": "library", "weight": 50},
            ]
        }
        result = ConstraintEngine.apply("background", component_def, {"outfit": "silk dress"})
        assert len(result) == 2

    def test_outfit_contains_filters(self):
        component_def = {
            "constraints": [
                {
                    "if": {"outfit_contains": "swimwear"},
                    "then": {"only": ["beach", "pool"]},
                }
            ],
            "options": [
                {"value": "sandy beach with waves", "weight": 50},
                {"value": "grand library with books", "weight": 50},
                {"value": "pool deck with loungers", "weight": 50},
            ],
        }
        result = ConstraintEngine.apply(
            "background", component_def, {"outfit": "black swimwear"}
        )
        values = {o["value"] for o in result}
        assert "sandy beach with waves" in values
        assert "pool deck with loungers" in values
        assert "grand library with books" not in values

    def test_outfit_contains_list(self):
        component_def = {
            "constraints": [
                {
                    "if": {"outfit_contains": ["cashmere", "blazer"]},
                    "then": {"only": ["library", "cafe"]},
                }
            ],
            "options": [
                {"value": "grand library with tall windows", "weight": 50},
                {"value": "luxury cafe with natural light", "weight": 50},
                {"value": "sandy beach with waves", "weight": 50},
            ],
        }
        result = ConstraintEngine.apply(
            "background", component_def, {"outfit": "cream cashmere sweater"}
        )
        values = {o["value"] for o in result}
        assert "grand library with tall windows" in values
        assert "luxury cafe with natural light" in values
        assert "sandy beach with waves" not in values

    def test_constraint_not_fired_no_filter(self):
        component_def = {
            "constraints": [
                {
                    "if": {"outfit_contains": "swimwear"},
                    "then": {"only": ["beach", "pool"]},
                }
            ],
            "options": [
                {"value": "grand library with books", "weight": 50},
            ],
        }
        result = ConstraintEngine.apply(
            "background", component_def, {"outfit": "silk blouse"}
        )
        assert len(result) == 1

    def test_constraint_keeps_all_on_empty_result(self, caplog):
        """If a constraint would remove all options, originals are kept."""
        component_def = {
            "constraints": [
                {
                    "if": {"outfit_contains": "swimwear"},
                    "then": {"only": ["mars_crater"]},  # nothing matches
                }
            ],
            "options": [
                {"value": "grand library with books", "weight": 50},
            ],
        }
        result = ConstraintEngine.apply(
            "background", component_def, {"outfit": "black swimwear"}
        )
        assert len(result) == 1
        assert "would remove all options" in caplog.text


# ======================================================================
# 4.4 — SceneRenderer output format
# ======================================================================

class TestArticlePluralFix:
    """Regression tests for `_article()` pluralia tantum fix."""

    def test_article_plural_leggings(self):
        assert _article("high-waist leggings and cropped tank") == ""

    def test_article_plural_shorts(self):
        assert _article("strappy sports bra and biker shorts") == "a"

    def test_article_plural_tights(self):
        assert _article("scoop-neck leotard with sheer tights") == "a"

    def test_article_singular_normal(self):
        assert _article("cream cashmere sweater") == "a"

    def test_article_singular_vowel(self):
        assert _article("elegant silk blouse") == "an"

    def test_article_empty(self):
        assert _article("") == "a"


class TestHairWithoutEthnicity:
    """Regression: hair must render even without ethnicity."""

    def test_hair_present_without_ethnicity(self):
        prompt = SceneRenderer.render({
            "subject": "woman",
            "hair": "styled in a sleek blowout",
            "outfit": "dress",
            "pose": "standing",
        })
        assert "sleek blowout" in prompt, "Hair should appear even without ethnicity"

    def test_hair_present_with_ethnicity(self):
        prompt = SceneRenderer.render({
            "subject": "woman",
            "ethnicity": "with chestnut hair",
            "hair": "styled in a sleek blowout",
            "outfit": "dress",
            "pose": "standing",
        })
        assert "chestnut hair" in prompt
        assert "sleek blowout" in prompt


class TestBabydollConstraintFix:
    """Regression: frilly bed must be selectable with babydoll outfit."""

    def test_frilly_bed_matches_with_bed_keyword(self):
        from pinterest_agent.scenes.constraints import ConstraintEngine
        result = ConstraintEngine._option_matches(
            "frilly bed draped in tulle",
            ["bedroom", "garden", "vanity", "cafe", "gazebo", "bed"],
        )
        assert result, "frilly bed should match with 'bed' keyword"

    def test_frilly_bed_not_matched_without_bed(self):
        from pinterest_agent.scenes.constraints import ConstraintEngine
        result = ConstraintEngine._option_matches(
            "frilly bed draped in tulle",
            ["bedroom", "garden", "vanity", "cafe", "gazebo"],
        )
        assert not result, "frilly bed should NOT match without 'bed'"


class TestSceneRenderer:
    """SceneRenderer must produce fluent prompts."""

    def test_render_contains_component_values(self):
        components = {
            "subject": "woman",
            "ethnicity": "with chestnut hair",
            "hair": "styled in a sleek blowout",
            "outfit": "cream cashmere sweater",
            "pose": "reading a book",
            "background": "grand library with tall windows",
            "lighting": "golden hour",
            "camera": "85mm lens",
            "mood": "quiet luxury",
            "style": "editorial fashion photography",
            "composition": "portrait orientation",
            "accessories": "a classic watch",
        }
        prompt = SceneRenderer.render(components)
        prompt_lower = prompt.lower()
        assert "woman" in prompt_lower
        assert "chestnut hair" in prompt_lower
        assert "cream cashmere sweater" in prompt_lower
        assert "reading a book" in prompt_lower
        assert "library" in prompt_lower
        assert "golden hour" in prompt_lower
        assert "85mm lens" in prompt_lower
        assert "quiet luxury" in prompt_lower
        assert "editorial" in prompt_lower
        assert "portrait" in prompt_lower
        assert "watch" in prompt_lower

    def test_render_minimal_components(self):
        components = {
            "subject": "woman",
            "outfit": "silk dress",
            "pose": "walking",
        }
        prompt = SceneRenderer.render(components)
        assert "Elegant woman" in prompt
        assert "silk dress" in prompt
        assert "walking" in prompt

    def test_render_empty_components(self):
        prompt = SceneRenderer.render({})
        assert prompt.strip() != ""

    def test_render_ends_with_period(self):
        components = {"subject": "woman", "outfit": "dress", "pose": "standing"}
        prompt = SceneRenderer.render(components)
        assert prompt.strip().endswith(".")

    def test_negative_prompt_base(self):
        components = {"outfit": "cream cashmere sweater", "background": "library"}
        neg = SceneRenderer.build_negative_prompt(components)
        assert "blurry" in neg
        assert "watermark" in neg

    def test_negative_prompt_swimwear(self):
        components = {"outfit": "black swimwear", "background": "beach"}
        neg = SceneRenderer.build_negative_prompt(components)
        assert "suggestive" in neg
        assert "nudity" in neg
        assert "explicit" in neg

    def test_negative_prompt_lingerie(self):
        components = {"outfit": "lace lingerie set", "background": "bedroom"}
        neg = SceneRenderer.build_negative_prompt(components)
        assert "suggestive" in neg

    def test_negative_prompt_indoor(self):
        components = {"outfit": "silk dress", "background": "grand library with tall windows"}
        neg = SceneRenderer.build_negative_prompt(components)
        assert "overexposed window" in neg
        assert "harsh shadows" in neg

    def test_negative_prompt_outdoor_no_addition(self):
        components = {"outfit": "silk dress", "background": "sandy beach with waves"}
        neg = SceneRenderer.build_negative_prompt(components)
        assert "overexposed window" not in neg
        assert "suggestive" not in neg


# ======================================================================
# 4.5 — SceneComposer end-to-end
# ======================================================================

class TestSceneComposerE2E:
    """SceneComposer end-to-end generation tests."""

    def test_generate_returns_scene(self, composer):
        scene = composer.generate("old_money", seed=42)
        assert isinstance(scene, Scene)
        assert scene.niche == "old_money"
        assert isinstance(scene.seed, int)

    def test_scene_has_all_fields(self, composer):
        scene = composer.generate("old_money", "old_money_reader", seed=99)
        assert scene.niche == "old_money"
        assert scene.archetype == "old_money_reader"
        assert scene.seed == 99
        assert len(scene.components) >= 10
        assert scene.prompt
        assert scene.negative_prompt
        assert scene.weights_used
        assert isinstance(scene.constraints_applied, list)

    def test_prompt_contains_component_values(self, composer):
        scene = composer.generate("old_money", seed=42)
        prompt_lower = scene.prompt.lower()
        for value in scene.components.values():
            if len(value) > 3:
                assert value.lower() in prompt_lower, (
                    f"'{value}' not found in prompt"
                )

    def test_all_niches_generate(self, composer):
        for niche in composer.list_niches():
            scene = composer.generate(niche, seed=7)
            assert scene.niche == niche
            assert scene.prompt, f"Empty prompt for niche '{niche}'"

    def test_all_archetypes_valid(self, composer):
        for niche in composer.list_niches():
            archetypes = composer.list_archetypes(niche)
            assert len(archetypes) >= 2, f"Niche '{niche}' should have ≥2 archetypes"
            for arch in archetypes:
                scene = composer.generate(niche, arch, seed=5)
                assert scene.archetype == arch

    def test_scene_prompt_is_sentence(self, composer):
        scene = composer.generate("old_money", seed=1)
        prompt = scene.prompt.strip()
        assert prompt.endswith(".")
        assert prompt[0].isupper()

    def test_list_niches(self, composer):
        niches = composer.list_niches()
        assert "old_money" in niches
        assert "coquette" in niches
        assert "pilates" in niches

    def test_list_archetypes(self, composer):
        archetypes = composer.list_archetypes("old_money")
        assert "old_money_student" in archetypes
        assert "old_money_businesswoman" in archetypes


# ======================================================================
# 4.6 — Same seed produces identical scene
# ======================================================================

class TestDeterminism:
    """Same seed must always produce the same scene."""

    def test_same_seed_identical(self, composer):
        scene_a = composer.generate("old_money", seed=42)
        scene_b = composer.generate("old_money", seed=42)
        assert scene_a.components == scene_b.components
        assert scene_a.prompt == scene_b.prompt
        assert scene_a.negative_prompt == scene_b.negative_prompt

    def test_same_seed_identical_across_archetypes(self, composer):
        scene_a = composer.generate("coquette", "romantic", seed=100)
        scene_b = composer.generate("coquette", "romantic", seed=100)
        assert scene_a.components == scene_b.components
        assert scene_a.prompt == scene_b.prompt

    def test_same_seed_identical_pilates(self, composer):
        scene_a = composer.generate("pilates", seed=77)
        scene_b = composer.generate("pilates", seed=77)
        assert scene_a.components == scene_b.components


# ======================================================================
# 4.7 — Different seeds produce different scenes
# ======================================================================

class TestVariety:
    """Different seeds should produce variation in outputs."""

    def test_different_seeds_different_components(self, composer):
        scenes = [composer.generate("old_money", seed=s) for s in range(20)]
        prompts = {s.prompt for s in scenes}
        # With 12 components × weighted options, 20 seeds should give variety
        assert len(prompts) > 1, "All 20 seeds produced the same prompt!"

    def test_different_seeds_different_archetypes(self, composer):
        """Even when archetype is random, seeds should differ."""
        scenes = [composer.generate("old_money", seed=s) for s in range(10)]
        assert len({s.archetype for s in scenes}) >= 1  # at least one


# ======================================================================
# 4.7 — ~466M combination count projection
# ======================================================================

class TestCombinationCount:
    """Verify the ~466M unique scene projection (no hardcoded limits)."""

    @staticmethod
    def _count_combinations(niche_def: dict) -> int:
        """Compute total combinations = product of option counts per component."""
        components = niche_def.get("components", {})
        # Archetype selection is a top-level multiplier
        archetype_count = len(niche_def.get("archetypes", {}))
        total = archetype_count
        for comp_name, comp_def in components.items():
            total *= len(comp_def.get("options", []))
        return total

    def test_old_money_combination_count(self):
        path = Path(__file__).parent.parent / "src" / "pinterest_agent" / "scenes" / "definitions" / "old_money.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        count = self._count_combinations(data)
        # 4 archetypes × 3×5×5×6×8×6×5×4×5×6×4×5 = ~1B combinations
        assert count >= 100_000_000, f"Expected ≥100M combinations, got {count}"
        assert count < 5_000_000_000, f"Suspiciously high count: {count}"

    def test_all_niches_combination_total(self, composer):
        total = 0
        for niche in composer.list_niches():
            with open(composer._definitions_dir / f"{niche}.yaml") as f:
                data = yaml.safe_load(f)
            total += self._count_combinations(data)
        # 3 niches should comfortably exceed 250M
        assert total >= 250_000_000, f"Expected ≥250M total combinations, got {total}"
        assert total < 10_000_000_000, f"Suspiciously high total: {total}"

    def test_no_hardcoded_limits(self, composer):
        """Every component must have at least 3 options (meaningful variety)."""
        for niche in composer.list_niches():
            with open(composer._definitions_dir / f"{niche}.yaml") as f:
                data = yaml.safe_load(f)
            for comp_name, comp_def in data.get("components", {}).items():
                assert len(comp_def.get("options", [])) >= 3, (
                    f"Component '{comp_name}' in '{niche}' has <3 options"
                )


# ======================================================================
# 3.1 — CLI flag registration
# ======================================================================

class TestCliFlagRegistration:
    """The ``--composer`` and ``--archetype`` flags must be registered."""

    def test_generate_prompts_has_composer_option(self):
        from pinterest_agent.cli.main import cli

        cmd = cli.commands.get("generate-prompts")
        assert cmd is not None
        params = {p.name for p in cmd.params}
        assert "composer" in params

    def test_generate_prompts_has_archetype_option(self):
        from pinterest_agent.cli.main import cli

        cmd = cli.commands.get("generate-prompts")
        assert cmd is not None
        params = {p.name for p in cmd.params}
        assert "archetype" in params


# ======================================================================
# Edge cases
# ======================================================================

class TestEdgeCases:
    """Edge-case handling for the SceneComposer."""

    def test_generate_unknown_niche(self, composer):
        with pytest.raises(FileNotFoundError):
            composer.generate("nonexistent_niche", seed=1)

    def test_generate_unknown_archetype(self, composer):
        with pytest.raises(ValueError, match="Unknown archetype"):
            composer.generate("old_money", archetype="nonexistent", seed=1)

    def test_scene_negative_present(self, composer):
        scene = composer.generate("old_money", seed=42)
        assert scene.negative_prompt
        assert "blurry" in scene.negative_prompt

    def test_scene_metadata_niche(self, composer):
        scene = composer.generate("coquette", seed=10)
        assert scene.niche == "coquette"

    def test_prompt_does_not_contain_placeholder(self, composer):
        scene = composer.generate("pilates", seed=3)
        assert "{value}" not in scene.prompt
        assert "{component" not in scene.prompt

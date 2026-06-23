"""Snapshot test suite: 1000 scene generations with quality verification."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

from pinterest_agent.scenes.composer import SceneComposer

# Reduce sample for CI speed; override via env when needed
_SAMPLE_SIZE = 1000
_SEED_RANGE = range(_SAMPLE_SIZE)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(scope="session")
def composer() -> SceneComposer:
    return SceneComposer()


@pytest.fixture(scope="session")
def all_scenes(composer) -> list:
    niches = composer.list_niches()
    scenes = []
    for i in _SEED_RANGE:
        niche = niches[i % len(niches)]
        scenes.append(composer.generate(niche, seed=i))
    return scenes


# ======================================================================
# Quality assertions
# ======================================================================


class TestNoMalformedEnglish:
    """Prompts must be well-formed English sentences."""

    def test_all_end_with_period(self, all_scenes):
        bad = [s for s in all_scenes if not s.prompt.strip().endswith(".")]
        assert not bad, f"{len(bad)} prompts missing trailing period"

    def test_all_start_uppercase(self, all_scenes):
        bad = [s for s in all_scenes if not s.prompt.strip()[0].isupper()]
        assert not bad, f"{len(bad)} prompts start lowercase"

    def test_no_empty_prompts(self, all_scenes):
        bad = [s for s in all_scenes if not s.prompt.strip()]
        assert not bad, f"{len(bad)} empty prompts"

    def test_no_empty_negative(self, all_scenes):
        bad = [s for s in all_scenes if not s.negative_prompt.strip()]
        assert not bad, f"{len(bad)} empty negative prompts"


class TestNoAdjacentDuplicates:
    """No adjacent repeated words (would indicate concatenation bugs)."""

    def test_no_adjacent_word_repeats(self, all_scenes):
        bad = []
        for s in all_scenes:
            words = s.prompt.lower().replace(",", "").replace(".", "").split()
            for i in range(len(words) - 1):
                if words[i] == words[i + 1] and len(words[i]) > 1:
                    bad.append((s.seed, words[i]))
                    break
        assert not bad, f"{len(bad)} prompts with adjacent duplicates (e.g. seed={bad[0][0]}, word='{bad[0][1]}')"


class TestNoPhraseRepeats:
    """No 4+ word sequences repeated within the same prompt."""

    def test_no_ngram_repeats(self, all_scenes):
        bad = []
        for s in all_scenes:
            words = s.prompt.lower().replace(",", "").replace(".", "").split()
            seen = set()
            for i in range(len(words) - 3):
                ngram = tuple(words[i:i + 4])
                if ngram in seen and len(set(ngram)) >= 2:
                    bad.append((s.seed, " ".join(ngram)))
                    break
                seen.add(ngram)
        assert not bad, f"{len(bad)} prompts with repeated 4-word sequences (e.g. seed={bad[0][0]}, phrase='{bad[0][1]}')"


class TestNoImpossibleCombinations:
    """No constraint-violating outfit→background pair should occur."""

    def _load_definition(self, niche: str) -> dict:
        from pinterest_agent.scenes.composer import SceneComposer
        c = SceneComposer()
        with open(c._definitions_dir / f"{niche}.yaml") as f:
            return yaml.safe_load(f)

    def _get_banned_backgrounds(self, outfit: str, niche: str) -> set:
        """Return backgrounds banned for this outfit under YAML constraints."""
        data = self._load_definition(niche)
        bg_def = data["components"]["background"]
        constraints = bg_def.get("constraints", [])
        if not constraints:
            return set()
        all_bg = {o["value"] for o in bg_def["options"]}
        # Find matching constraint
        for c in constraints:
            condition = c["if"]
            action = c["then"]
            cond_key = list(condition.keys())[0]
            if cond_key != "outfit_contains":
                continue
            cond_val = condition[cond_key]
            outfit_lower = outfit.lower()
            matches = False
            if isinstance(cond_val, str):
                matches = cond_val.lower() in outfit_lower
            elif isinstance(cond_val, list):
                matches = any(v.lower() in outfit_lower for v in cond_val)
            if matches:
                only_values = action.get("only", [])
                allowed = set()
                for bg in all_bg:
                    bg_lower = bg.lower()
                    if any(v in bg_lower or bg_lower in v for v in only_values):
                        allowed.add(bg)
                return all_bg - allowed
        return set()

    def test_no_forbidden_backgrounds(self, all_scenes):
        bad = []
        for s in all_scenes:
            outfit = s.components.get("outfit", "")
            bg = s.components.get("background", "")
            banned = self._get_banned_backgrounds(outfit, s.niche)
            if bg in banned:
                bad.append((s.seed, s.niche, outfit, bg))
        assert not bad, f"{len(bad)} impossible combos: {bad[:3]}"


class TestNoEmptySections:
    """Every component should render into the prompt."""

    def test_outfit_in_prompt(self, all_scenes):
        for s in all_scenes:
            outfit = s.components.get("outfit", "")
            if outfit and outfit not in s.prompt:
                pytest.fail(f"seed={s.seed}: outfit '{outfit}' missing from prompt")

    def test_pose_in_prompt(self, all_scenes):
        for s in all_scenes:
            pose = s.components.get("pose", "")
            if pose and pose not in s.prompt:
                pytest.fail(f"seed={s.seed}: pose '{pose}' missing from prompt")

    def test_background_in_prompt(self, all_scenes):
        for s in all_scenes:
            bg = s.components.get("background", "")
            if bg and bg not in s.prompt:
                # Fallback: last 3+ words for long backgrounds
                words = bg.split()
                tail = " ".join(words[-3:]) if len(words) >= 3 else bg
                if tail not in s.prompt:
                    pytest.fail(f"seed={s.seed}: background '{bg}' missing from prompt")


class TestNoRepeatedClauses:
    """No clause should appear twice in the same prompt."""

    def test_no_clause_repeats(self, all_scenes):
        bad = []
        for s in all_scenes:
            clauses = [c.strip() for c in s.prompt.replace(".", ",").split(",")]
            seen = set()
            for clause in clauses:
                key = clause.lower().strip()
                if len(key) > 10 and key in seen:
                    bad.append((s.seed, clause))
                    break
                seen.add(key)
        assert not bad, f"{len(bad)} prompts with repeated clauses"


# ======================================================================
# Metrics
# ======================================================================


class TestMetrics:
    """Report generation metrics and verify minimum quality bars."""

    def test_uniqueness_ratio(self, all_scenes):
        prompts = {s.prompt for s in all_scenes}
        ratio = len(prompts) / len(all_scenes)
        print(f"\n  Uniqueness ratio: {ratio:.2%} ({len(prompts)} unique / {len(all_scenes)} total)")
        assert ratio >= 0.90, f"Uniqueness ratio {ratio:.2%} below 90% threshold"

    def test_average_prompt_length(self, all_scenes):
        lengths = [len(s.prompt) for s in all_scenes]
        avg = sum(lengths) / len(lengths)
        print(f"\n  Avg prompt length: {avg:.0f} chars (min={min(lengths)}, max={max(lengths)})")
        assert 100 <= avg <= 500, f"Avg length {avg:.0f} outside expected range"

    def test_archetype_distribution(self, all_scenes):
        counts = Counter(s.archetype for s in all_scenes)
        print(f"\n  Archetype distribution ({len(counts)} archetypes):")
        for arch, n in counts.most_common():
            print(f"    {arch}: {n} ({n / len(all_scenes):.1%})")
        # Every archetype should appear at least once
        assert len(counts) >= 9, f"Expected >= 9 archetypes, got {len(counts)}"

    def test_background_distribution(self, all_scenes):
        counts = Counter(s.components.get("background", "") for s in all_scenes)
        print(f"\n  Background distribution ({len(counts)} backgrounds):")
        for bg, n in counts.most_common(8):
            print(f"    {bg}: {n} ({n / len(all_scenes):.1%})")
        # At least half of defined backgrounds should appear
        all_bgs = set()
        for niche in ["old_money", "coquette", "pilates"]:
            from pinterest_agent.scenes.composer import SceneComposer
            c = SceneComposer()
            with open(c._definitions_dir / f"{niche}.yaml") as f:
                data = yaml.safe_load(f)
            for opt in data["components"]["background"]["options"]:
                all_bgs.add(opt["value"])
        assert len(counts) >= len(all_bgs) * 0.5, (
            f"Only {len(counts)}/{len(all_bgs)} backgrounds appeared"
        )

    def test_no_placeholder_text(self, all_scenes):
        for s in all_scenes:
            assert "{value}" not in s.prompt, f"seed={s.seed}: placeholder in prompt"
            assert "{component" not in s.prompt, f"seed={s.seed}: placeholder in prompt"
            assert s.negative_prompt, f"seed={s.seed}: empty negative prompt"
            assert "blurry" in s.negative_prompt, f"seed={s.seed}: missing base negative"

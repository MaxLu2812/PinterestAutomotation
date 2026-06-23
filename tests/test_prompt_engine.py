"""Tests for the Prompt Engine — templates, engine, provider, and CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
from pinterest_agent.domain.models import Prompt, PromptStatus
from pinterest_agent.prompts.engine import PromptEngine
from pinterest_agent.prompts.gpt_provider import GPT4MiniProvider
from pinterest_agent.prompts.provider import PromptProvider


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with test YAML templates."""
    templates = tmp_path / "templates"
    templates.mkdir()

    # --- old_money template ---
    old_money = {
        "niche": "old_money",
        "description": "Test template",
        "prompt_template": "Elegant {age} woman with {hair_color} hair wearing {outfit}",
        "variables": {
            "age": ["25-35", "35-50"],
            "hair_color": ["dark brown", "blonde"],
            "outfit": ["cashmere coat", "silk dress"],
        },
    }
    with (templates / "old_money.yaml").open("w") as f:
        yaml.dump(old_money, f)

    # --- coquette template ---
    coquette = {
        "niche": "coquette",
        "description": "Test template",
        "prompt_template": "Soft feminine {age} woman with {hair_color} hair, wearing {outfit}",
        "variables": {
            "age": ["18-25", "20-30"],
            "hair_color": ["blonde", "pastel pink"],
            "outfit": ["lace babydoll", "satin camisole"],
        },
    }
    with (templates / "coquette.yaml").open("w") as f:
        yaml.dump(coquette, f)

    return templates


@pytest.fixture
def in_memory_cm() -> ConnectionManager:
    """Return a ConnectionManager backed by :memory: SQLite."""
    cm = ConnectionManager(":memory:")
    cm.connect()
    return cm


@pytest.fixture
def repo(in_memory_cm: ConnectionManager) -> SqlitePromptRepository:
    return SqlitePromptRepository(in_memory_cm)


@pytest.fixture
def engine(repo: SqlitePromptRepository, template_dir: Path) -> PromptEngine:
    return PromptEngine(repo=repo, template_dir=template_dir)


# ======================================================================
# Task 2.1 — Template loading and structure
# ======================================================================


class TestTemplateLoading:
    """Verify YAML templates load correctly and have required fields."""

    def test_list_templates(self, engine: PromptEngine) -> None:
        templates = engine.list_templates()
        assert sorted(templates) == ["coquette", "old_money"]

    def test_load_template_has_required_keys(self, engine: PromptEngine) -> None:
        tmpl = engine._load_template("old_money")
        assert "niche" in tmpl
        assert "prompt_template" in tmpl
        assert "variables" in tmpl
        assert "description" in tmpl

    def test_missing_template_raises(self, engine: PromptEngine) -> None:
        with pytest.raises(FileNotFoundError):
            engine._load_template("nonexistent")

    def test_missing_variable_raises(self, engine: PromptEngine) -> None:
        """A template referencing an undefined variable should error."""
        # Manually inject a bad template into the dir
        bad = {
            "niche": "bad",
            "prompt_template": "Hello {undefined_var}",
            "variables": {"defined_var": ["a"]},
        }
        bad_path = engine._template_dir / "bad.yaml"
        with bad_path.open("w") as f:
            yaml.dump(bad, f)

        with pytest.raises(ValueError, match="undefined_var"):
            engine.generate_one("bad", seed=1)


# ======================================================================
# Task 2.2 — Engine: variable seeding, dedup, batch
# ======================================================================


class TestVariableSeeding:
    """Deterministic variable selection — same seed → same result."""

    def test_deterministic_selection(self, engine: PromptEngine) -> None:
        variables_a = engine._pick_variables(
            engine._load_template("old_money"), seed=42
        )
        variables_b = engine._pick_variables(
            engine._load_template("old_money"), seed=42
        )
        assert variables_a == variables_b

    def test_different_seed_different_result(self, engine: PromptEngine) -> None:
        v1 = engine._pick_variables(engine._load_template("old_money"), seed=1)
        v2 = engine._pick_variables(engine._load_template("old_money"), seed=999)
        # Extremely unlikely all three vars are identical across seeds
        assert v1 != v2


class TestEngineGenerate:
    """End-to-end prompt generation through the engine."""

    def test_generate_one_stores_prompt(self, engine: PromptEngine) -> None:
        prompt = engine.generate_one("old_money", seed=42)

        assert prompt.id > 0
        assert prompt.template_id == "old_money"
        assert prompt.variable_seed == 42
        assert prompt.status == PromptStatus.GENERATED
        assert prompt.text != ""
        # Verify variables are substituted
        for val in prompt.variables.values():
            assert val in prompt.text

    def test_generate_batch(self, engine: PromptEngine) -> None:
        results = engine.generate_batch("old_money", count=3, start_seed=1)
        assert len(results) == 3
        # Each should have distinct seeds
        seeds = {p.variable_seed for p in results}
        assert seeds == {1, 2, 3}

    def test_duplicate_skip(self, engine: PromptEngine) -> None:
        """Same template + seed returns existing prompt without creating a new row."""
        first = engine.generate_one("old_money", seed=42)
        second = engine.generate_one("old_money", seed=42)

        assert first.id == second.id
        assert first.text == second.text

    def test_different_seed_not_duplicate(self, engine: PromptEngine) -> None:
        """Different seeds produce different prompts."""
        first = engine.generate_one("old_money", seed=1)
        second = engine.generate_one("old_money", seed=2)

        assert first.id != second.id
        assert first.text != second.text


class TestProviderInterface:
    """GPT4MiniProvider interface — passthrough and error handling."""

    def test_passthrough_when_no_api_key(self) -> None:
        provider = GPT4MiniProvider(api_key=None)
        assert not provider.is_available()
        result = provider.generate("test prompt")
        assert result == "test prompt"

    def test_provider_name(self) -> None:
        provider = GPT4MiniProvider(api_key=None)
        assert provider.name() == "gpt-4o-mini"

    def test_provider_retries_on_error(self) -> None:
        """When API fails, retries happen (we mock to verify the attempt)."""
        provider = GPT4MiniProvider(api_key="test-key", max_retries=2)

        # Mock is_available to return True, and _call_api to always fail
        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(provider, "_call_api") as mock_call,
        ):
            mock_call.side_effect = RuntimeError("API error")

            with pytest.raises(RuntimeError, match="API error"):
                provider.generate("test")

            # Should have attempted max_retries times
            assert mock_call.call_count == 2

    def test_provider_recovers_after_retry(self) -> None:
        """First call fails, second succeeds."""
        provider = GPT4MiniProvider(api_key="test-key", max_retries=3)

        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(provider, "_call_api") as mock_call,
        ):
            mock_call.side_effect = [RuntimeError("first fail"), "refined prompt"]

            result = provider.generate("test")
            assert result == "refined prompt"
            assert mock_call.call_count == 2

    def test_abc_interface(self) -> None:
        """All providers must implement PromptProvider."""
        assert issubclass(GPT4MiniProvider, PromptProvider)

    def test_engine_with_provider(self, engine: PromptEngine) -> None:
        """Engine generates prompts with a provider attached (passthrough)."""
        provider = GPT4MiniProvider(api_key=None)
        engine._provider = provider

        prompt = engine.generate_one("old_money", seed=1)
        assert prompt.id > 0
        assert prompt.status == PromptStatus.GENERATED


# ======================================================================
# Task 2.3 — Repository: FIFO queue, status tracking, dedup queries
# ======================================================================


class TestFifoQueue:
    """Prompts are returned in FIFO order by the repository."""

    def test_fifo_order(self, repo: SqlitePromptRepository) -> None:
        p1 = Prompt(aesthetic="test", template_id="t1", text="first", variables={}, variable_seed=1)
        p2 = Prompt(aesthetic="test", template_id="t2", text="second", variables={}, variable_seed=2)
        p3 = Prompt(aesthetic="test", template_id="t3", text="third", variables={}, variable_seed=3)

        repo.enqueue(p1)
        repo.enqueue(p2)
        repo.enqueue(p3)

        dequeued = repo.dequeue(limit=10)
        texts = [p.text for p in dequeued]
        assert texts == ["first", "second", "third"]


class TestDedupQueries:
    """Repository-level dedup by template_id + variable_seed."""

    def test_find_by_template_and_seed_found(self, repo: SqlitePromptRepository) -> None:
        prompt = Prompt(
            aesthetic="test",
            template_id="old_money",
            text="test prompt",
            variables={"age": "25-35"},
            variable_seed=42,
            status=PromptStatus.GENERATED,
        )
        pid = repo.enqueue(prompt)
        prompt.id = pid

        found = repo.find_by_template_and_seed("old_money", 42)
        assert found is not None
        assert found.id == pid

    def test_find_by_template_and_seed_not_found(
        self, repo: SqlitePromptRepository
    ) -> None:
        found = repo.find_by_template_and_seed("nonexistent", 999)
        assert found is None

    def test_find_by_template_and_seed_respects_different_seed(
        self, repo: SqlitePromptRepository
    ) -> None:
        prompt = Prompt(
            aesthetic="test",
            template_id="old_money",
            text="test prompt",
            variables={"age": "25-35"},
            variable_seed=1,
            status=PromptStatus.GENERATED,
        )
        repo.enqueue(prompt)

        # Same template, different seed → not found
        found = repo.find_by_template_and_seed("old_money", 2)
        assert found is None


class TestQuery:
    """Repository query method with optional filters."""

    def test_query_by_status(self, repo: SqlitePromptRepository) -> None:
        p1 = Prompt(aesthetic="a", template_id="t1", text="x", variables={}, variable_seed=1, status=PromptStatus.PENDING)
        p2 = Prompt(aesthetic="b", template_id="t2", text="y", variables={}, variable_seed=2, status=PromptStatus.GENERATED)
        repo.enqueue(p1)
        repo.enqueue(p2)

        pending = repo.query(status=PromptStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].text == "x"

        generated = repo.query(status=PromptStatus.GENERATED)
        assert len(generated) == 1
        assert generated[0].text == "y"

    def test_query_by_niche(self, repo: SqlitePromptRepository) -> None:
        p1 = Prompt(aesthetic="old_money", template_id="t1", text="a", variables={}, variable_seed=1)
        p2 = Prompt(aesthetic="coquette", template_id="t2", text="b", variables={}, variable_seed=2)
        repo.enqueue(p1)
        repo.enqueue(p2)

        results = repo.query(niche="old_money")
        assert len(results) == 1
        assert results[0].text == "a"

    def test_query_by_status_and_niche(self, repo: SqlitePromptRepository) -> None:
        p1 = Prompt(aesthetic="a", template_id="t1", text="x", variables={}, variable_seed=1, status=PromptStatus.FAILED)
        p2 = Prompt(aesthetic="a", template_id="t2", text="y", variables={}, variable_seed=2, status=PromptStatus.GENERATED)
        repo.enqueue(p1)
        repo.enqueue(p2)

        results = repo.query(status=PromptStatus.GENERATED, niche="a")
        assert len(results) == 1
        assert results[0].text == "y"


# ======================================================================
# Real template files (Task 2.1 — structural validation)
# ======================================================================


class TestRealTemplates:
    """Validate the shipped YAML templates have correct structure."""

    TEMPLATE_NAMES = ["old_money", "coquette", "pilates", "lingerie_aesthetic"]
    TEMPLATE_DIR = Path(__file__).parents[1] / "src" / "pinterest_agent" / "prompts" / "templates"

    @pytest.fixture(autouse=True)
    def verify_template_dir(self) -> None:
        assert self.TEMPLATE_DIR.is_dir(), (
            f"Template directory not found: {self.TEMPLATE_DIR}"
        )

    @pytest.mark.parametrize("name", TEMPLATE_NAMES)
    def test_template_exists(self, name: str) -> None:
        path = self.TEMPLATE_DIR / f"{name}.yaml"
        assert path.is_file(), f"Missing template: {path}"

    @pytest.mark.parametrize("name", TEMPLATE_NAMES)
    def test_template_structure(self, name: str) -> None:
        path = self.TEMPLATE_DIR / f"{name}.yaml"
        with path.open("r") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict), f"{name}: root is not a mapping"
        assert "niche" in data, f"{name}: missing 'niche'"
        assert "description" in data, f"{name}: missing 'description'"
        assert "prompt_template" in data, f"{name}: missing 'prompt_template'"
        assert "variables" in data, f"{name}: missing 'variables'"

        # Verify all placeholders in prompt_template have a variable entry
        import re
        placeholders = re.findall(r"\{(\w+)\}", data["prompt_template"])
        for ph in placeholders:
            assert ph in data["variables"], (
                f"{name}: placeholder '{{{ph}}}' has no matching variable entry"
            )

        # Verify each variable has at least one option
        for var_name, options in data["variables"].items():
            assert isinstance(options, list), f"{name}: '{var_name}' is not a list"
            assert len(options) >= 1, f"{name}: '{var_name}' has no options"


class TestCliRegistration:
    """CLI commands register without errors."""

    def test_import_generate_module(self) -> None:
        """Importing the generate module should not raise."""
        from pinterest_agent.cli import generate  # noqa: F401
        assert True

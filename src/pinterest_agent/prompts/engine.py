"""PromptEngine — orchestrates template loading, variable seeding, and queueing.

Flow
----
1. Load a YAML template for the requested niche.
2. Pick random variable values (seeded for repeatability).
3. Fill placeholders in the template string.
4. Optionally send to a PromptProvider for GPT-4o-mini refinement.
5. Check for duplicate (same template_id + variable_seed → skip).
6. Store result in SQLite queue via PromptRepository.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional

import yaml

from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
from pinterest_agent.domain.models import Prompt, PromptStatus
from pinterest_agent.prompts.provider import PromptProvider

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptEngine:
    """Orchestrates prompt generation from YAML templates.

    Args:
        repo: PromptRepository for persistence.
        provider: Optional PromptProvider for GPT-4o-mini refinement.
        template_dir: Directory containing YAML template files.
            Defaults to ``prompts/templates/`` next to this file.
    """

    def __init__(
        self,
        repo: SqlitePromptRepository,
        provider: Optional[PromptProvider] = None,
        template_dir: Optional[Path] = None,
        enable_dedup: bool = True,
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._template_dir = template_dir or _TEMPLATE_DIR
        self._enable_dedup = enable_dedup

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_one(
        self,
        template_id: str,
        seed: int,
    ) -> Prompt:
        """Generate a single prompt from *template_id* with the given *seed*.

        Returns the stored Prompt. If a prompt with the same template and seed
        already exists (status ``generated``), returns the existing record.
        """
        # 1. Load template
        template = self._load_template(template_id)

        # 2. Check for duplicate (optional via enable_dedup flag)
        if self._enable_dedup:
            existing = self._repo.find_by_template_and_seed(template_id, seed)
            if existing is not None and existing.status == PromptStatus.GENERATED:
                logger.info(
                    "Duplicate prompt for %s / seed %d — returning existing id=%d",
                    template_id,
                    seed,
                    existing.id,
                )
                return existing

        # 3. Pick variables deterministically
        variables = self._pick_variables(template, seed)

        # 4. Fill template
        try:
            prompt_text = template["prompt_template"].format(**variables)
        except KeyError as exc:
            raise ValueError(
                f"Template '{template_id}' references unknown variable {exc}. "
                f"Available: {list(template.get('variables', {}))}"
            ) from exc

        # 5. Optionally refine via provider
        if self._provider is not None and self._provider.is_available():
            try:
                prompt_text = self._provider.generate(
                    prompt_text, seed=seed
                )
            except Exception as exc:
                logger.error("Provider refinement failed for %s: %s", template_id, exc)
                # Fall through — use the unrefined prompt

        # 6. Enqueue
        prompt = Prompt(
            aesthetic=template.get("niche", template_id),
            template_id=template_id,
            variables=variables,
            text=prompt_text,
            variable_seed=seed,
            status=PromptStatus.GENERATED,
        )
        prompt_id = self._repo.enqueue(prompt)
        prompt.id = prompt_id
        logger.info(
            "Generated prompt id=%d for %s / seed=%d",
            prompt_id,
            template_id,
            seed,
        )
        return prompt

    def generate_batch(
        self,
        template_id: str,
        count: int = 10,
        start_seed: int = 1,
    ) -> list[Prompt]:
        """Generate *count* prompts for *template_id* using sequential seeds.

        Each prompt uses a seed from ``start_seed`` to ``start_seed + count - 1``.
        Existing duplicates are returned from the DB without calling the provider.
        """
        results: list[Prompt] = []
        for offset in range(count):
            seed = start_seed + offset
            prompt = self.generate_one(template_id, seed)
            results.append(prompt)
        return results

    def list_templates(self) -> list[str]:
        """Return all available template names (file stems without extension)."""
        if not self._template_dir.is_dir():
            return []
        return sorted(
            p.stem
            for p in self._template_dir.iterdir()
            if p.suffix in (".yaml", ".yml")
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_template(self, template_id: str) -> dict:
        """Load a YAML template by its stem name (e.g. 'old_money')."""
        candidates = [
            self._template_dir / f"{template_id}.yaml",
            self._template_dir / f"{template_id}.yml",
        ]
        for path in candidates:
            if path.is_file():
                with path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    raise ValueError(
                        f"Template '{template_id}' is not a valid YAML mapping"
                    )
                return data

        raise FileNotFoundError(
            f"Template '{template_id}' not found in {self._template_dir}. "
            f"Available: {', '.join(self.list_templates())}"
        )

    @staticmethod
    def _pick_variables(template: dict, seed: int) -> dict[str, str]:
        """Pick one random value per variable key using the given seed.

        Uses Python's ``random.Random(seed)`` for deterministic choice.
        """
        var_defs: dict[str, list[str]] = template.get("variables", {})
        if not var_defs:
            return {}

        rng = random.Random(seed)
        return {key: rng.choice(values) for key, values in var_defs.items()}

"""End-to-end test for the complete pipeline.

Mocks external APIs (GPT, image generation, Pinterest) but uses real
SQLite and file system operations. Tests the full flow:
generate prompts → generate images → publish pins.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.e2e
class TestE2EPipeline:
    """Full pipeline E2E test with all mocks."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up temporary directories for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmpdir) / "test.db")
        self.storage_root = Path(self.tmpdir) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "images" / "processed").mkdir(parents=True, exist_ok=True)

        yield

        # Clean up
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_template(self, template_dir: Path):
        """Create a test YAML template."""
        import yaml

        template = {
            "niche": "old_money",
            "description": "Test template for E2E",
            "prompt_template": "Elegant {age} woman with {hair_color} hair wearing {outfit}",
            "variables": {
                "age": ["25-35", "35-50"],
                "hair_color": ["dark brown", "blonde"],
                "outfit": ["cashmere coat", "silk dress"],
            },
        }
        template_dir.mkdir(parents=True, exist_ok=True)
        with (template_dir / "old_money.yaml").open("w") as f:
            yaml.dump(template, f)

    def _mock_gpt_provider(self):
        """Create a mock GPT provider that returns the prompt text as-is."""
        provider = MagicMock()
        provider.is_available.return_value = True
        provider.name.return_value = "gpt-4o-mini"
        provider.generate.side_effect = lambda text, seed=None: text
        return provider

    def _mock_image_generator(self):
        """Create a mock image generator that produces unique images per seed."""
        from PIL import Image
        from pinterest_agent.generators.base import GenerationResult

        class MockImageGenerator:
            @property
            def name(self):
                return "mock_e2e"

            def is_available(self):
                return True

            def generate(self, prompt, seed=None, **kwargs):
                # Use seed to create unique images (avoid SHA256 dedup)
                s = seed or 0
                r = (s * 50) % 256
                g = (s * 80) % 256
                b = (s * 120) % 256
                img = Image.new("RGB", (1024, 1024), color=(r, g, b))
                return GenerationResult(
                    success=True,
                    image=img,
                    width=1024,
                    height=1024,
                    generation_time=0.2,
                    provider="mock_e2e",
                    seed=s,
                )

        return MockImageGenerator()

    def _mock_pinterest_client(self):
        """Create a mock Pinterest client."""
        client = MagicMock()
        client.create_pin.return_value = {
            "id": "e2e_pin_001",
            "link": "https://pin.it/e2e_test",
        }
        client.resolve_board_id.return_value = "board_e2e_001"
        return client

    def test_full_pipeline(self):
        """Complete flow: generate prompts → generate images → publish pins."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )
        from pinterest_agent.domain.models import (
            ImageStatus,
            PromptStatus,
            PublicationStatus,
        )
        from pinterest_agent.generators.pipeline import ImagePipeline

        # ---- Phase 1: Generate prompts ----
        cm = ConnectionManager(self.db_path)
        cm.connect()

        repo = SqlitePromptRepository(cm)
        template_dir = Path(self.tmpdir) / "templates"
        self._seed_template(template_dir)

        from pinterest_agent.prompts.engine import PromptEngine

        engine = PromptEngine(
            repo=repo,
            provider=self._mock_gpt_provider(),
            template_dir=template_dir,
        )

        prompts = engine.generate_batch("old_money", count=3, start_seed=1)
        assert len(prompts) == 3

        # Verify all prompts are in DB with GENERATED status
        for p in prompts:
            assert p.id > 0
            assert p.status == PromptStatus.GENERATED
            assert p.text != ""

        # Reset prompt statuses to PENDING so pipeline can process them
        for p in prompts:
            cm.execute(
                "UPDATE prompts SET status = ? WHERE id = ?",
                (PromptStatus.PENDING.value, p.id),
            )

        assert repo.count_by_status(PromptStatus.GENERATED) == 0
        assert repo.count_by_status(PromptStatus.PENDING) == 3

        # ---- Phase 2: Generate images ----
        image_repo = SqliteImageRepository(cm)

        pipeline = ImagePipeline(
            prompt_repo=repo,
            image_repo=image_repo,
            generators=[self._mock_image_generator()],
            storage_root=self.storage_root,
        )

        stats = pipeline.run()
        assert stats.total == 3
        assert stats.succeeded == 3
        assert stats.failed == 0

        # Verify DB records
        assert repo.count_by_status(PromptStatus.GENERATED) == 3
        assert image_repo.count_by_status(ImageStatus.GENERATED.value) == 3

        # Verify files were created
        images = image_repo.query(status=ImageStatus.GENERATED.value, limit=10)
        assert len(images) == 3
        for img in images:
            assert img.file_path != ""
            img_path = Path(img.file_path)
            assert img_path.exists(), f"Image file not found: {img_path}"
            assert img.status == ImageStatus.GENERATED

        # ---- Phase 3: Publish pins ----
        from pinterest_agent.publishers.pin_publisher import PinPublisher

        pub_repo = SqlitePublicationRepository(cm)
        publisher = PinPublisher(
            pinterest_client=self._mock_pinterest_client(),
            image_repo=image_repo,
            publication_repo=pub_repo,
            board_mapping={"old_money": "Old Money Women"},
        )

        results = publisher.publish_batch(images)
        assert len(results) == 3
        assert all(r.success for r in results)

        # Verify publication records
        assert pub_repo.count_by_status(PublicationStatus.PUBLISHED) == 3
        assert pub_repo.count_published_today() == 3

        # Verify image statuses updated
        for img in images:
            updated = image_repo.find_by_prompt_id(img.prompt_id)
            assert updated is not None
            assert updated.status == ImageStatus.PUBLISHED
            assert updated.pin_id is not None

        # Verify prompt statuses remain GENERATED (not changed by publishing)
        for p in prompts:
            row = cm.execute(
                "SELECT status FROM prompts WHERE id = ?", (p.id,)
            ).fetchone()
            assert row["status"] == "generated"

        # ---- Phase 4: Verify complete cycle ----
        # Total counts should be correct
        total_prompts = (
            repo.count_by_status(PromptStatus.GENERATED)
            + repo.count_by_status(PromptStatus.FAILED)
            + repo.count_by_status(PromptStatus.PENDING)
        )
        assert total_prompts == 3

        total_images = (
            image_repo.count_by_status(ImageStatus.GENERATED.value)
            + image_repo.count_by_status(ImageStatus.PUBLISHED.value)
            + image_repo.count_by_status(ImageStatus.FAILED.value)
            + image_repo.count_by_status(ImageStatus.PENDING.value)
        )
        assert total_images == 3

        # Clean up
        cm.close()

    def test_empty_pipeline(self):
        """Pipeline with no data should handle gracefully."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.generators.pipeline import ImagePipeline

        cm = ConnectionManager(":memory:")
        cm.connect()

        repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)

        pipeline = ImagePipeline(
            prompt_repo=repo,
            image_repo=image_repo,
            generators=[],
            storage_root=self.storage_root,
        )

        stats = pipeline.run()
        assert stats.total == 0
        assert stats.succeeded == 0
        assert stats.failed == 0

        cm.close()

    def test_pipeline_with_some_failures(self):
        """Pipeline should handle partial failures."""
        from PIL import Image
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )
        from pinterest_agent.domain.models import Prompt
        from pinterest_agent.generators.base import GenerationResult

        cm = ConnectionManager(":memory:")
        cm.connect()

        repo = SqlitePromptRepository(cm)

        # Seed prompts
        for i in range(3):
            p = Prompt(
                aesthetic="test",
                template_id="t",
                text=f"prompt {i}",
                variable_seed=i,
            )
            p.id = repo.enqueue(p)
            cm.execute(
                "UPDATE prompts SET status = ? WHERE id = ?",
                ("pending", p.id),
            )

        # Create a generator that fails for the second prompt
        # and produces different images for each prompt
        class AlternatingGenerator:
            call_count = 0

            @property
            def name(self):
                return "alternating"

            def is_available(self):
                return True

            def generate(self, prompt, seed=None, **kwargs):
                AlternatingGenerator.call_count += 1
                if AlternatingGenerator.call_count == 2:  # Second prompt fails
                    return GenerationResult(
                        success=False,
                        error="Simulated failure",
                        provider="alternating",
                    )
                # Use seed to make different images (avoid SHA256 dedup)
                color_val = (seed or 0) * 50 % 256
                img = Image.new("RGB", (100, 100), color=(color_val, 150, 200))
                return GenerationResult(
                    success=True,
                    image=img,
                    width=100,
                    height=100,
                    generation_time=0.1,
                    provider="alternating",
                    seed=seed,
                )

        from pinterest_agent.generators.pipeline import ImagePipeline

        image_repo = SqliteImageRepository(cm)
        pipeline = ImagePipeline(
            prompt_repo=repo,
            image_repo=image_repo,
            generators=[AlternatingGenerator()],
            storage_root=self.storage_root,
            phash_threshold=0,
        )

        stats = pipeline.run()
        assert stats.total == 3
        assert stats.succeeded == 2
        assert stats.failed == 1

        cm.close()

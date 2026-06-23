"""Integration tests for Pinterest Aesthetic Automation.

These tests use real SQLite (can be :memory:) but mock external APIs.
Marked with @pytest.mark.integration to distinguish from pure unit tests.

To run with real API keys:
    PINTEREST_TOKEN=your_token OPENAI_API_KEY=your_key pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from pinterest_agent.config.loader import AppConfig, ConfigLoader
from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.domain.models import (
    ImageRecord,
    ImageStatus,
    Prompt,
    PromptStatus,
    PublicationRecord,
    PublicationStatus,
)


# ======================================================================
# Integration tests: DB full lifecycle
# ======================================================================


@pytest.mark.integration
class TestDatabaseLifecycle:
    """Full database lifecycle: prompt → image → publication."""

    def test_full_lifecycle(self):
        """Create a prompt, generate image, publish, and verify all transitions."""
        cm = ConnectionManager(":memory:")
        cm.connect()

        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)
        pub_repo = SqlitePublicationRepository(cm)

        # --- Step 1: Create prompt ---
        prompt = Prompt(
            aesthetic="old_money",
            template_id="old_money",
            text="Elegant 30-year-old woman with dark brown hair wearing a cashmere coat",
            variable_seed=42,
            status=PromptStatus.GENERATED,
        )
        prompt.id = prompt_repo.enqueue(prompt)
        assert prompt.id > 0

        # --- Step 2: Create image record ---
        img = ImageRecord(
            prompt_id=prompt.id,
            prompt_hash=prompt.text,
            file_path="/tmp/test_image.webp",
            status=ImageStatus.GENERATED,
            niche="old_money",
            backend="mock",
            seed=42,
            width=1000,
            height=1500,
            file_size=50000,
            generation_time=1.5,
        )
        img.id = image_repo.save(img)
        assert img.id > 0

        # --- Step 3: Create publication record ---
        from datetime import datetime
        pub = PublicationRecord(
            image_id=img.id,
            board_id="Old Money Women",
            title="Elegant Old Money Style",
            description="Timeless elegance",
            tags="old_money, elegance, style",
            status=PublicationStatus.PUBLISHED,
            pinterest_pin_id="pin_12345",
            published_at=datetime.now(),
        )
        pub.id = pub_repo.save(pub)
        assert pub.id > 0

        # --- Step 4: Verify counts ---
        assert prompt_repo.count_by_status(PromptStatus.GENERATED) == 1
        assert image_repo.count_by_status(ImageStatus.GENERATED.value) == 1
        assert pub_repo.count_by_status(PublicationStatus.PUBLISHED) == 1

        # --- Step 5: Verify queries ---
        prompts = prompt_repo.query(niche="old_money")
        assert len(prompts) == 1

        images = image_repo.query(niche="old_money")
        assert len(images) == 1

        # --- Step 6: Verify find_by methods ---
        found_img = image_repo.find_by_prompt_id(prompt.id)
        assert found_img is not None
        assert found_img.id == img.id

        found_pub = pub_repo.find_by_image_id(img.id)
        assert found_pub is not None
        assert found_pub.pinterest_pin_id == "pin_12345"

    def test_status_transitions(self):
        """Verify all status transitions work correctly."""
        cm = ConnectionManager(":memory:")
        cm.connect()

        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)
        pub_repo = SqlitePublicationRepository(cm)

        # Prompt: pending → generated → failed
        prompt = Prompt(
            aesthetic="test",
            template_id="t",
            text="test",
            variable_seed=1,
            status=PromptStatus.PENDING,
        )
        prompt.id = prompt_repo.enqueue(prompt)
        assert prompt_repo.count_by_status(PromptStatus.PENDING) == 1

        prompt_repo.mark_done(prompt.id)
        assert prompt_repo.count_by_status(PromptStatus.GENERATED) == 1
        assert prompt_repo.count_by_status(PromptStatus.PENDING) == 0

        prompt_repo.mark_failed(prompt.id, "test error")
        assert prompt_repo.count_by_status(PromptStatus.FAILED) == 1

        # Image: pending → generated → published → failed (in parallel)
        img = ImageRecord(
            prompt_id=prompt.id,
            file_path="/tmp/img.webp",
            status=ImageStatus.PENDING,
            niche="test",
        )
        img.id = image_repo.save(img)

        image_repo.mark_published(img.id, "pin_001")
        published = image_repo.find_by_prompt_id(prompt.id)
        assert published is not None
        assert published.status == ImageStatus.PUBLISHED
        assert published.pin_id == "pin_001"


# ======================================================================
# Integration tests: Config loading
# ======================================================================


@pytest.mark.integration
class TestConfigLoading:
    """Config loading from actual YAML strings."""

    def test_load_from_yaml_string(self):
        """Load config from a YAML string via validate_config_dict."""
        yaml_str = """
        publishing:
          pins_per_day: 15
          publish_windows:
            - hour: 8
              minute: 0
              label: "early"
        generator:
          target_width: 800
          target_height: 1200
        accounts:
          - name: "main"
            token_ref: "TEST_TOKEN"
        niches:
          old_money:
            name: "Old Money Women"
            board_name: "Old Money"
            template_dir: "templates"
        """
        data = yaml.safe_load(yaml_str)
        config = ConfigLoader.validate_config_dict(data)
        assert isinstance(config, AppConfig)
        assert config.publishing.pins_per_day == 15
        assert config.generator.target_width == 800
        assert config.generator.target_height == 1200

    def test_minimal_config(self):
        """Minimal config should work with defaults."""
        data = {
            "accounts": [{"name": "test", "token_ref": "TEST_TOKEN"}],
            "niches": {"test": {"name": "Test"}},
        }
        config = ConfigLoader.validate_config_dict(data)
        assert config.accounts[0].name == "test"
        assert config.publishing.pins_per_day == 10  # default

    def test_config_with_all_defaults(self):
        """Empty config should use all defaults."""
        config = ConfigLoader.validate_config_dict({})
        assert isinstance(config, AppConfig)
        assert config.db_path == "data/pinterest_agent.db"
        assert config.generator.primary_provider == "local_diffusers"

    def test_invalid_config_raises(self):
        """Invalid config should raise ValueError with details."""
        with pytest.raises(ValueError) as excinfo:
            ConfigLoader.validate_config_dict({
                "publishing": {"pins_per_day": -1},
            })
        assert "validation failed" in str(excinfo.value).lower()

    @patch.dict(os.environ, {"TEST_TOKEN": "real_token"}, clear=True)
    def test_config_with_env_resolution(self, tmp_path: Path):
        """ConfigLoader should resolve env vars from a real YAML file."""
        config_data = {
            "accounts": [
                {
                    "name": "main",
                    "token_ref": "TEST_TOKEN",
                    "niches": ["old_money"],
                },
            ],
            "niches": {
                "old_money": {
                    "name": "Old Money",
                    "board_name": "Old Money Women",
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        loader = ConfigLoader(str(config_file))
        config = loader.load(str(config_file))

        assert config.accounts[0].tokens.get("access_token") == "real_token"


# ======================================================================
# Integration tests: File system operations
# ======================================================================


@pytest.mark.integration
class TestFileSystemOperations:
    """File system operations: create directories, save images, clean up."""

    def test_directory_creation(self):
        """Directories should be created automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Test mkdir chain
            target = base / "images" / "processed"
            target.mkdir(parents=True, exist_ok=True)
            assert target.is_dir()

            # Test nested structures
            (base / "images" / "raw").mkdir(parents=True, exist_ok=True)
            (base / "images" / "failed").mkdir(parents=True, exist_ok=True)
            (base / "logs").mkdir(parents=True, exist_ok=True)

            assert (base / "images" / "raw").is_dir()
            assert (base / "images" / "failed").is_dir()
            assert (base / "logs").is_dir()

    def test_image_save_and_verify(self):
        """Save a PIL image to disk and verify metadata."""
        from PIL import Image
        from pinterest_agent.utils.image_utils import save_image

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "processed"
            output_dir.mkdir(parents=True, exist_ok=True)

            img = Image.new("RGB", (1000, 1500), color=(128, 128, 128))
            filepath = save_image(
                image=img,
                output_dir=output_dir,
                niche="old_money",
                date_str="2024-06-23",
                seed=42,
                short_hash="abcdef12",
                quality=90,
            )

            assert filepath.exists()
            assert filepath.suffix == ".webp"
            assert filepath.stat().st_size > 0

            # Verify dimensions preserved
            saved = Image.open(filepath)
            assert saved.width == 1000
            assert saved.height == 1500
            saved.close()  # Release file handle for cleanup

    def test_image_processing(self):
        """Process an image and verify dimensions."""
        from PIL import Image
        from pinterest_agent.utils.image_utils import process_image

        # Create a wide image
        wide = Image.new("RGB", (1600, 900), color=(255, 0, 0))
        processed = process_image(wide, target_width=1000, target_height=1500)
        assert processed.width == 1000
        assert processed.height == 1500
        assert processed.mode == "RGB"

        # Create a tall image
        tall = Image.new("RGB", (600, 2000), color=(0, 255, 0))
        processed = process_image(tall, target_width=1000, target_height=1500)
        assert processed.width == 1000
        assert processed.height == 1500

    def test_db_connection_with_file(self):
        """File-based DB connection should create the file."""
        import sqlite3
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cm = ConnectionManager(str(db_path))
            cm.connect()

            assert db_path.exists()
            assert db_path.stat().st_size > 0

            # Verify schema was applied (fresh DB gets version 2 with v4 schema)
            version = cm._get_schema_version()
            assert version >= 2, f"Expected version >= 2, got {version}"

            # Verify all expected tables exist
            tables = cm.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            assert "prompts" in table_names
            assert "images" in table_names
            assert "publications" in table_names

            cm.close()

    def test_db_with_in_memory(self):
        """In-memory database should work correctly."""
        cm = ConnectionManager(":memory:")
        cm.connect()
        version = cm._get_schema_version()
        assert version >= 2, f"Expected version >= 2, got {version}"

        # Verify tables exist
        tables = cm.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "prompts" in table_names
        assert "images" in table_names
        assert "publications" in table_names

        cm.close()


# ======================================================================
# Integration: Repository count methods
# ======================================================================


@pytest.mark.integration
class TestRepositoryCounts:
    """Repository count methods should return correct values."""

    def test_prompt_count_by_status(self):
        """PromptRepository.count_by_status should reflect current state."""
        cm = ConnectionManager(":memory:")
        cm.connect()

        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.domain.models import Prompt

        repo = SqlitePromptRepository(cm)

        pending = Prompt(aesthetic="a", text="p", variable_seed=1, status=PromptStatus.PENDING)
        generated = Prompt(aesthetic="b", text="g", variable_seed=2, status=PromptStatus.GENERATED)
        failed = Prompt(aesthetic="c", text="f", variable_seed=3, status=PromptStatus.FAILED)

        repo.enqueue(pending)
        repo.enqueue(generated)
        repo.enqueue(failed)

        assert repo.count_by_status(PromptStatus.PENDING) == 1
        assert repo.count_by_status(PromptStatus.GENERATED) == 1
        assert repo.count_by_status(PromptStatus.FAILED) == 1

    def test_image_count_by_status(self):
        """ImageRepository.count_by_status should reflect current state."""
        cm = ConnectionManager(":memory:")
        cm.connect()

        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.domain.models import ImageRecord

        repo = SqliteImageRepository(cm)

        # Seed prompts first to satisfy foreign key
        cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('test', 't', '{}', 1, 'test', 'generated')"
        )

        for status in ["pending", "generated", "published", "failed"]:
            img = ImageRecord(
                prompt_id=1,
                file_path=f"/tmp/{status}.webp",
                status=ImageStatus(status),
                niche="test",
            )
            repo.save(img)

        assert repo.count_by_status("pending") == 1
        assert repo.count_by_status("generated") == 1
        assert repo.count_by_status("published") == 1
        assert repo.count_by_status("failed") == 1

    def test_publication_count_by_status(self):
        """PublicationRepository.count_by_status should reflect state."""
        cm = ConnectionManager(":memory:")
        cm.connect()

        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )
        from pinterest_agent.domain.models import PublicationRecord

        repo = SqlitePublicationRepository(cm)

        # Need a prompt + image for FK
        cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('test', 't', '{}', 1, 'test', 'generated')"
        )
        cm.execute(
            "INSERT INTO images (prompt_id, file_path, status, niche) "
            "VALUES (1, '/tmp/i.webp', 'generated', 'test')"
        )

        for status, pin_id in [("published", "p1"), ("published", "p2"), ("failed", None)]:
            repo.save(PublicationRecord(
                image_id=1,
                board_id="b1",
                title="T",
                status=PublicationStatus(status),
                pinterest_pin_id=pin_id,
            ))

        assert repo.count_by_status(PublicationStatus.PUBLISHED) == 2
        assert repo.count_by_status(PublicationStatus.FAILED) == 1

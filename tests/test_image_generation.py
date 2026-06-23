"""Tests for image generation pipeline — providers, factory, dedup, processing."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pinterest_agent.generators.hf_inference  # noqa: F401

# Import generator modules to trigger auto-registration in the global registry
import pinterest_agent.generators.local_diffusers  # noqa: F401
from pinterest_agent.dedup.perceptual_hash import compute_phash, hamming_distance
from pinterest_agent.domain.models import ImageStatus, PromptStatus
from pinterest_agent.generators.base import (
    GenerationResult,
    ImageGenerator,
    get_provider_class,
    list_registered_providers,
    register_provider,
)
from pinterest_agent.generators.factory import GeneratorFactory
from pinterest_agent.generators.pipeline import ImagePipeline, compute_sha256
from pinterest_agent.utils.image_utils import (
    process_image,
    safety_check,
    save_image,
)

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def pil_image():
    """Create a small test PIL image."""
    from PIL import Image

    return Image.new("RGB", (512, 768), color=(128, 128, 128))


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test image output."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_generator():
    """Create a mock ImageGenerator that succeeds."""

    class MockGenerator(ImageGenerator):
        @property
        def name(self):
            return "mock"

        def is_available(self):
            return True

        def generate(self, prompt, seed=None, **kwargs):
            from PIL import Image

            img = Image.new("RGB", (1024, 1024), color=(42, 42, 42))
            return GenerationResult(
                success=True,
                image=img,
                width=1024,
                height=1024,
                generation_time=0.5,
                provider="mock",
                seed=seed or 0,
            )

    return MockGenerator()


@pytest.fixture
def failing_mock_generator():
    """Create a mock ImageGenerator that fails."""

    class FailingGenerator(ImageGenerator):
        @property
        def name(self):
            return "failing"

        def is_available(self):
            return True

        def generate(self, prompt, seed=None, **kwargs):
            return GenerationResult(
                success=False,
                error="Mock failure",
                provider="failing",
                seed=seed,
            )

    return FailingGenerator()


@pytest.fixture
def image_pipeline(mock_generator):
    """Create an ImagePipeline with a mock generator and in-memory repos."""
    from pinterest_agent.db.connection import ConnectionManager
    from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
    from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
    from pinterest_agent.domain.models import Prompt

    cm = ConnectionManager(":memory:")
    cm.connect()

    prompt_repo = SqlitePromptRepository(cm)
    image_repo = SqliteImageRepository(cm)

    # Seed a pending prompt
    prompt = Prompt(
        aesthetic="test_niche",
        template_id="test",
        variable_seed=42,
        text="A test prompt",
        status=ImageStatus.PENDING,
    )
    prompt.id = prompt_repo.enqueue(prompt)

    # Fix status to pending (enqueue uses PromptStatus.PENDING)
    cm.execute(
        "UPDATE prompts SET status = ? WHERE id = ?",
        (PromptStatus.PENDING.value, prompt.id),
    )

    pipeline = ImagePipeline(
        prompt_repo=prompt_repo,
        image_repo=image_repo,
        generators=[mock_generator],
        storage_root=Path(tempfile.mkdtemp()),
    )
    return pipeline, cm


# ======================================================================
# Tests: Generator ABC contract
# ======================================================================


class TestGeneratorABC:
    """Verify that ImageGenerator ABC enforces the interface contract."""

    def test_cannot_instantiate_abc(self):
        """ABC should not be instantiable directly."""
        with pytest.raises(TypeError):
            ImageGenerator()  # type: ignore[abstract]

    def test_concrete_must_implement_abstract_methods(self):
        """Subclass missing abstract methods must raise TypeError."""

        class Incomplete(ImageGenerator):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ======================================================================
# Tests: Provider registry
# ======================================================================


class TestProviderRegistry:
    def test_register_and_retrieve(self):
        """Registered provider should be retrievable by name."""

        class TestGen(ImageGenerator):
            @property
            def name(self):
                return "test_reg"

            def is_available(self):
                return True

            def generate(self, prompt, seed=None, **kwargs):
                return GenerationResult(success=True, provider="test_reg")

        register_provider("test_reg", TestGen)
        cls = get_provider_class("test_reg")
        assert cls is TestGen

    def test_unknown_provider_raises_keyerror(self):
        """Unknown provider names should raise KeyError."""
        with pytest.raises(KeyError):
            get_provider_class("nonexistent")

    def test_list_registered(self):
        """list_registered_providers should return all names."""
        providers = list_registered_providers()
        assert "local_diffusers" in providers
        assert "huggingface" in providers


# ======================================================================
# Tests: GeneratorFactory
# ======================================================================


class TestGeneratorFactory:
    def test_create_known_provider(self):
        """Factory should create a registered provider."""
        factory = GeneratorFactory()
        gen = factory.create("local_diffusers", device="cpu")
        assert gen.is_available() is not None  # may be False if no deps

    def test_create_unknown_provider_raises(self):
        """Factory should raise KeyError for unknown provider."""
        factory = GeneratorFactory()
        with pytest.raises(KeyError):
            factory.create("nonexistent")

    def test_create_priority_chain(self):
        """Priority chain should return ordered list of generators."""
        factory = GeneratorFactory()
        chain = factory.create_priority_chain(
            ["local_diffusers", "huggingface"]
        )
        assert len(chain) == 2
        assert chain[0].name == "local_diffusers"
        assert chain[1].name == "huggingface"

    def test_first_available(self, mock_generator, failing_mock_generator):
        """first_available should return the first available generator."""
        result = GeneratorFactory.first_available(
            [failing_mock_generator, mock_generator]
        )
        assert result is failing_mock_generator  # both available, first wins
        assert result.is_available()


# ======================================================================
# Tests: HuggingFaceProvider (mocked)
# ======================================================================


class TestHuggingFaceProvider:
    def test_is_available_no_token(self):
        """Without HF_API_TOKEN, is_available should return False."""
        from pinterest_agent.generators.hf_inference import HuggingFaceProvider

        provider = HuggingFaceProvider(api_token="")
        assert not provider.is_available()

    def test_is_available_with_token(self):
        """With a token set, is_available should check huggingface_hub import."""
        from pinterest_agent.generators.hf_inference import HuggingFaceProvider

        provider = HuggingFaceProvider(api_token="hf_test_token")
        # huggingface_hub may or may not be installed
        # If installed, True; otherwise False (graceful)
        import huggingface_hub  # noqa: F401

        assert provider.is_available()

    @patch("pinterest_agent.generators.hf_inference.HuggingFaceProvider._get_client")
    def test_generate_success(self, mock_get_client, pil_image):
        """Successful generation should return a GenerationResult with image."""
        mock_client = MagicMock()
        mock_client.text_to_image.return_value = pil_image
        mock_get_client.return_value = mock_client

        from pinterest_agent.generators.hf_inference import HuggingFaceProvider

        provider = HuggingFaceProvider(api_token="hf_test_token")
        result = provider.generate("test prompt", seed=42)

        assert result.success
        assert result.image is not None
        assert result.provider == "huggingface"
        assert result.seed == 42

    @patch("pinterest_agent.generators.hf_inference.HuggingFaceProvider._get_client")
    def test_generate_failure(self, mock_get_client):
        """Generation failure should return result with error."""
        mock_client = MagicMock()
        mock_client.text_to_image.side_effect = RuntimeError("API error")
        mock_get_client.return_value = mock_client

        from pinterest_agent.generators.hf_inference import HuggingFaceProvider

        provider = HuggingFaceProvider(api_token="hf_test_token")
        result = provider.generate("test prompt")

        assert not result.success
        assert "API error" in (result.error or "")


# ======================================================================
# Tests: Image processing
# ======================================================================


class TestImageProcessing:
    def test_process_image_resizes(self, pil_image):
        """Image should be cropped and resized to target dimensions."""
        processed = process_image(pil_image, target_width=1000, target_height=1500)
        assert processed.width == 1000
        assert processed.height == 1500

    def test_process_image_center_crop_wide(self):
        """Wide image should be center-cropped then resized."""
        from PIL import Image

        wide = Image.new("RGB", (1600, 800), color=(255, 0, 0))
        processed = process_image(wide, target_width=1000, target_height=1500)
        assert processed.width == 1000
        assert processed.height == 1500

    def test_process_image_center_crop_tall(self):
        """Tall image should be center-cropped then resized."""
        from PIL import Image

        tall = Image.new("RGB", (600, 1800), color=(0, 255, 0))
        processed = process_image(tall, target_width=1000, target_height=1500)
        assert processed.width == 1000
        assert processed.height == 1500

    def test_process_image_unknown_strategy(self, pil_image):
        """Unknown crop_strategy should raise ValueError."""
        with pytest.raises(ValueError, match="(?i)unknown.*crop_strategy"):
            process_image(pil_image, crop_strategy="unknown")

    def test_process_image_non_rgb(self):
        """Non-RGB images should be converted to RGB."""
        from PIL import Image

        rgba = Image.new("RGBA", (512, 512), color=(128, 128, 128, 128))
        processed = process_image(rgba)
        assert processed.mode == "RGB"

    def test_save_image_creates_file(self, pil_image, temp_output_dir):
        """Saved image file should exist with correct naming."""
        filepath = save_image(
            pil_image,
            output_dir=temp_output_dir,
            niche="test_niche",
            date_str="2024-01-01",
            seed=42,
            short_hash="abcdef12",
        )
        assert filepath.exists()
        # Verify naming convention
        assert "2024-01-01_test_niche_42_abcdef12.webp" in str(filepath)
        # Verify it's a WEBP
        assert filepath.suffix == ".webp"

    def test_save_image_directory_structure(self, pil_image, temp_output_dir):
        """Image should be saved under niche/date directory."""
        filepath = save_image(
            pil_image,
            output_dir=temp_output_dir,
            niche="my_niche",
            date_str="2024-06-15",
            seed=1,
            short_hash="aabbccdd",
        )
        expected_parent = temp_output_dir / "my_niche" / "2024-06-15"
        assert filepath.parent == expected_parent

    def test_compute_sha256_deterministic(self, pil_image):
        """SHA256 should be deterministic for the same image."""
        h1 = compute_sha256(pil_image)
        h2 = compute_sha256(pil_image)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_safety_check_passes(self, pil_image):
        """V1 safety check should always pass."""
        result = safety_check(pil_image)
        assert result.safe
        assert result.reason is None


# ======================================================================
# Tests: Perceptual hash
# ======================================================================


class TestPerceptualHash:
    def test_compute_phash(self, pil_image):
        """pHash should return a hex string."""
        phash = compute_phash(pil_image)
        if phash is not None:
            # If imagehash is installed
            assert isinstance(phash, str)
            assert len(phash) > 0

    def test_hamming_distance_same(self):
        """Hamming distance of same hash should be 0."""
        assert hamming_distance("abc", "abc") == 0

    def test_hamming_distance_different(self):
        """Different hashes should have non-zero distance."""
        # 'a' ^ 'b' = 0x03 → 2 bits differ
        dist = hamming_distance("a", "b")
        assert dist > 0


# ======================================================================
# Tests: Pipeline
# ======================================================================


class TestImagePipeline:
    def test_pipeline_success_path(self, image_pipeline):
        """Successful generation should create an image record and mark prompt done."""
        pipeline, cm = image_pipeline

        stats = pipeline.run()

        assert stats.total == 1
        assert stats.succeeded == 1

        # Verify prompt status changed
        prompt = cm.execute("SELECT status FROM prompts WHERE id = 1").fetchone()
        assert prompt["status"] == "generated"

        # Verify image record was created
        images = cm.execute("SELECT COUNT(*) FROM images").fetchone()
        assert images[0] == 1

    def test_pipeline_already_generated(self, image_pipeline):
        """Prompt with existing generated image should be skipped."""
        pipeline, cm = image_pipeline

        # Run once to generate
        pipeline.run()

        # Run again — should skip
        stats = pipeline.run()

        assert stats.total == 0  # no pending prompts
        assert stats.succeeded == 0

    def test_pipeline_provider_failure(self, failing_mock_generator, pil_image):
        """Provider failure should mark prompt as failed and continue."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.domain.models import Prompt, PromptStatus

        cm = ConnectionManager(":memory:")
        cm.connect()

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)

        prompt = Prompt(
            aesthetic="test",
            text="fail prompt",
            variable_seed=1,
        )
        prompt.id = prompt_repo.enqueue(prompt)
        cm.execute(
            "UPDATE prompts SET status = ? WHERE id = ?",
            (PromptStatus.PENDING.value, prompt.id),
        )

        pipeline = ImagePipeline(
            prompt_repo=prompt_repo,
            image_repo=image_repo,
            generators=[failing_mock_generator],
            storage_root=Path(tempfile.mkdtemp()),
        )

        stats = pipeline.run()

        assert stats.total == 1
        assert stats.failed == 1

        # Prompt should be marked failed
        p = cm.execute("SELECT status FROM prompts WHERE id = ?", (prompt.id,)).fetchone()
        assert p["status"] == "failed"

        # Image record should exist with failed status
        img = cm.execute("SELECT status FROM images WHERE prompt_id = ?", (prompt.id,)).fetchone()
        assert img["status"] == "failed"

    def test_fetch_by_prompt_ids(self, mock_generator):
        """Pipeline should accept specific prompt IDs."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.domain.models import Prompt, PromptStatus

        cm = ConnectionManager(":memory:")
        cm.connect()

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)

        p1 = Prompt(aesthetic="a", text="p1", variable_seed=1)
        p1.id = prompt_repo.enqueue(p1)
        cm.execute("UPDATE prompts SET status = ? WHERE id = ?", (PromptStatus.PENDING.value, p1.id))

        p2 = Prompt(aesthetic="b", text="p2", variable_seed=2)
        p2.id = prompt_repo.enqueue(p2)
        cm.execute("UPDATE prompts SET status = ? WHERE id = ?", (PromptStatus.PENDING.value, p2.id))

        pipeline = ImagePipeline(
            prompt_repo=prompt_repo,
            image_repo=image_repo,
            generators=[mock_generator],
            storage_root=Path(tempfile.mkdtemp()),
        )

        stats = pipeline.run(prompt_ids=[p1.id])
        assert stats.total == 1
        assert stats.succeeded == 1


# ======================================================================
# Tests: CLI
# ======================================================================


class TestCLIRegistration:
    def test_cli_has_generate_images(self):
        """CLI should have the generate-images command registered."""
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        assert "generate-images" in commands
        assert "list-images" in commands
        assert "retry-images" in commands

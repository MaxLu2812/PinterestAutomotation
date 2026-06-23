"""Tests for deduplication — SHA256 computation, pHash, Hamming distance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pinterest_agent.dedup.perceptual_hash import compute_phash, hamming_distance
from pinterest_agent.generators.pipeline import compute_sha256


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def pil_image():
    """Create a small test PIL image."""
    from PIL import Image

    return Image.new("RGB", (512, 768), color=(128, 128, 128))


@pytest.fixture
def pil_image_red():
    """Create a slightly different test image."""
    from PIL import Image

    return Image.new("RGB", (512, 768), color=(200, 50, 50))


# ======================================================================
# Tests: SHA256 computation
# ======================================================================


class TestSHA256:
    def test_sha256_deterministic(self, pil_image):
        """SHA256 should be deterministic for the same image."""
        h1 = compute_sha256(pil_image)
        h2 = compute_sha256(pil_image)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest length

    def test_sha256_different_images(self, pil_image, pil_image_red):
        """Different images should have different hashes."""
        h1 = compute_sha256(pil_image)
        h2 = compute_sha256(pil_image_red)
        assert h1 != h2

    def test_sha256_format(self, pil_image):
        """SHA256 should be a hex string."""
        h = compute_sha256(pil_image)
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256_in_memory(self):
        """SHA256 should work without saving to disk."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        h = compute_sha256(img)
        assert len(h) == 64


# ======================================================================
# Tests: Perceptual hash
# ======================================================================


class TestPerceptualHash:
    def test_compute_phash(self, pil_image):
        """pHash should return a hex string when imagehash is installed."""
        phash = compute_phash(pil_image)
        if phash is not None:
            assert isinstance(phash, str)
            assert len(phash) > 0
            assert all(c in "0123456789abcdef" for c in phash)

    def test_compute_phash_handles_exception(self, pil_image):
        """pHash should handle internal computation errors gracefully."""
        from pinterest_agent.dedup.perceptual_hash import compute_phash as cp
        import pinterest_agent.dedup.perceptual_hash as ph_module

        # If imagehash is installed and available, test error handling
        if hasattr(ph_module, "imagehash") and ph_module.imagehash is not None:
            with patch.object(ph_module.imagehash, "phash") as mock_phash:
                mock_phash.side_effect = RuntimeError("Computation failed")
                result = cp(pil_image)
                assert result is None

    def test_compute_phash_deterministic(self, pil_image):
        """pHash should be deterministic for the same image."""
        phash1 = compute_phash(pil_image)
        phash2 = compute_phash(pil_image)
        if phash1 is not None and phash2 is not None:
            assert phash1 == phash2

    def test_compute_phash_different(self, pil_image, pil_image_red):
        """Different images should have different pHashes."""
        phash1 = compute_phash(pil_image)
        phash2 = compute_phash(pil_image_red)
        if phash1 is not None and phash2 is not None:
            assert phash1 != phash2


# ======================================================================
# Tests: Hamming distance
# ======================================================================


class TestHammingDistance:
    def test_same_hash_distance_zero(self):
        """Same hash should have distance 0."""
        assert hamming_distance("aabb", "aabb") == 0

    def test_different_hash_nonzero(self):
        """Different hashes should have non-zero distance."""
        # 'a' = 0b01100001, 'b' = 0b01100010 → 2 bits differ
        dist = hamming_distance("a", "b")
        assert dist > 0

    def test_known_distance(self):
        """Verify known Hamming distance."""
        # 'ff' = 0b11111111, '00' = 0b00000000 → 8 bits differ
        dist = hamming_distance("ff", "00")
        assert dist == 8

    def test_inverse_symmetry(self):
        """Hamming distance should be symmetric."""
        d1 = hamming_distance("abc", "def")
        d2 = hamming_distance("def", "abc")
        assert d1 == d2

    def test_single_bit_diff(self):
        """Single bit difference should give distance 1."""
        # '00' = 0b00000000, '01' = 0b00000001 → 1 bit differs
        dist = hamming_distance("00", "01")
        assert dist == 1

    def test_empty_strings(self):
        """Empty strings cannot be converted to int with base 16."""
        with pytest.raises(ValueError):
            hamming_distance("", "")

    def test_long_hashes(self):
        """64-char hex hashes should compute correctly."""
        h1 = "a" * 64
        h2 = "b" * 64
        dist = hamming_distance(h1, h2)
        assert dist > 0

    def test_edge_case_all_ones(self):
        """All bits set vs all bits clear."""
        # 'ffff' = 65535, '0000' = 0 → 16 bits differ
        dist = hamming_distance("ffff", "0000")
        assert dist == 16


# ======================================================================
# Tests: Dedup pipeline integration
# ======================================================================


class TestDedupPipelineIntegration:
    """Test that dedup methods integrate with the image pipeline."""

    def test_sha256_dedup_in_pipeline(self):
        """SHA256 check should prevent duplicate image records."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.domain.models import ImageRecord, ImageStatus, Prompt
        from pinterest_agent.generators.base import GenerationResult
        from pinterest_agent.generators.pipeline import ImagePipeline
        from PIL import Image
        import tempfile

        cm = ConnectionManager(":memory:")
        cm.connect()

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)

        # Create two prompts with the same text (will produce same image)
        p1 = Prompt(
            aesthetic="test", template_id="t", text="same prompt", variable_seed=1
        )
        p1.id = prompt_repo.enqueue(p1)
        cm.execute(
            "UPDATE prompts SET status = ? WHERE id = ?",
            ("pending", p1.id),
        )

        p2 = Prompt(
            aesthetic="test", template_id="t", text="same prompt", variable_seed=2
        )
        p2.id = prompt_repo.enqueue(p2)
        cm.execute(
            "UPDATE prompts SET status = ? WHERE id = ?",
            ("pending", p2.id),
        )

        class ConstImageGenerator:
            """Generator that always returns the same image."""

            @property
            def name(self):
                return "const"

            def is_available(self):
                return True

            def generate(self, prompt, seed=None, **kwargs):
                img = Image.new("RGB", (100, 100), color=(50, 100, 150))
                return GenerationResult(
                    success=True,
                    image=img,
                    width=100,
                    height=100,
                    generation_time=0.1,
                    provider="const",
                    seed=seed or 0,
                )

        pipeline = ImagePipeline(
            prompt_repo=prompt_repo,
            image_repo=image_repo,
            generators=[ConstImageGenerator()],
            storage_root=tempfile.mkdtemp(),
            phash_threshold=0,  # Disable phash for this test
        )

        # Run once to process both prompts
        stats = pipeline.run()
        # The first one succeeds, the second is detected as SHA256 duplicate
        assert stats.succeeded == 1
        assert stats.skipped_duplicate == 1

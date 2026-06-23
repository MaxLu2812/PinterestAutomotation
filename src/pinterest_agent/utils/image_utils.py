"""Image processing utilities — resizing, cropping, saving, and safety checks."""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def process_image(
    image: object,
    target_width: int = 1000,
    target_height: int = 1500,
    crop_strategy: str = "center",
) -> object:
    """Crop and resize a PIL Image to the target dimensions.

    Preserves aspect ratio by cropping to the target aspect ratio first,
    then resizing to the exact dimensions.

    Args:
        image: A PIL.Image instance.
        target_width: Target width in pixels.
        target_height: Target height in pixels.
        crop_strategy: Cropping strategy ('center' or 'smart').

    Returns:
        Processed PIL.Image in RGB mode.

    Raises:
        ValueError: If an unknown crop_strategy is provided.
        ImportError: If PIL is not installed.
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Pillow is required for image processing. Install with: pip install Pillow"
        )

    # Ensure RGB mode
    if image.mode != "RGB":
        image = image.convert("RGB")

    target_ratio = target_width / target_height
    src_width, src_height = image.size
    src_ratio = src_width / src_height

    if crop_strategy == "center":
        # Crop to target aspect ratio from center
        if src_ratio > target_ratio:
            # Source is wider — crop width
            new_width = int(src_height * target_ratio)
            left = (src_width - new_width) // 2
            image = image.crop((left, 0, left + new_width, src_height))
        elif src_ratio < target_ratio:
            # Source is taller — crop height
            new_height = int(src_width / target_ratio)
            top = (src_height - new_height) // 2
            image = image.crop((0, top, src_width, top + new_height))
        # If ratios match exactly, no crop needed
    else:
        raise ValueError(f"Unknown crop_strategy: {crop_strategy}")

    # Resize to exact target dimensions
    image = image.resize((target_width, target_height), Image.LANCZOS)  # type: ignore[attr-defined]

    return image


def save_image(
    image: object,
    output_dir: Path,
    niche: str,
    date_str: str,
    seed: int,
    short_hash: str,
    quality: int = 90,
) -> Path:
    """Save a PIL Image as WEBP with Pinterest-optimized naming.

    Filename format: ``{date_str}_{niche}_{seed}_{short_hash}.webp``

    Directory structure: ``{output_dir}/{niche}/{date_str}/``

    Args:
        image: A PIL.Image instance.
        output_dir: Root output directory for processed images.
        niche: Aesthetic niche for subdirectory naming.
        date_str: Date string in YYYY-MM-DD format.
        seed: Generation seed (included in filename for traceability).
        short_hash: First 8 characters of the SHA256 hash.
        quality: WEBP quality (1-100, default 90).

    Returns:
        Path to the saved file.
    """
    # Create directory structure
    niche_dir = output_dir / niche
    date_dir = niche_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    # Build filename
    filename = f"{date_str}_{niche}_{seed}_{short_hash}.webp"
    filepath = date_dir / filename

    # Save as WEBP
    image.save(  # type: ignore[union-attr]
        str(filepath),
        format="WEBP",
        quality=quality,
        method=6,  # best compression
    )

    logger.info("Saved image: %s (%d×%d, %d bytes)", filepath, image.width, image.height, filepath.stat().st_size)  # type: ignore[union-attr]
    return filepath


def compute_sha256(image: object) -> str:
    """Compute the SHA256 hex digest of a PIL Image's bytes.

    Args:
        image: A PIL.Image instance.

    Returns:
        Hex string of the SHA256 hash.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")  # type: ignore[union-attr]
    return hashlib.sha256(buf.getvalue()).hexdigest()


# ---------------------------------------------------------------------------
# Safety checker (placeholder for NSFW detection)
# ---------------------------------------------------------------------------


class SafetyCheckResult:
    """Result of a safety check on an image."""

    def __init__(self, safe: bool, reason: Optional[str] = None) -> None:
        self.safe = safe
        self.reason = reason


def safety_check(image: object) -> SafetyCheckResult:
    """Run a basic safety check on an image.

    In V1, this is a placeholder that always passes.
    Future versions may integrate with NSFW detection models.

    Args:
        image: A PIL.Image instance.

    Returns:
        SafetyCheckResult with safe=True if the image is clean.
    """
    _ = image  # placeholder — no-op in V1
    return SafetyCheckResult(safe=True)

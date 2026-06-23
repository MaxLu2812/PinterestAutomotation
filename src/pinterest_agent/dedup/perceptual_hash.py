"""Perceptual hash computation for image deduplication.

Uses the ``imagehash`` library to compute pHash values that are robust
to minor compression and resizing differences.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_phash(image: object, hash_size: int = 8) -> Optional[str]:
    """Compute the perceptual hash (pHash) of a PIL Image.

    Uses ``imagehash.phash`` which is robust against resizing, compression,
    and minor color changes.

    Args:
        image: A PIL.Image instance.
        hash_size: Size of the hash (8 → 64-bit hash). Larger values are
                   more discriminating but less robust.

    Returns:
        Hex string of the pHash, or None if ``imagehash`` is not installed
        or computation fails.
    """
    try:
        import imagehash
    except ImportError:
        logger.warning(
            "imagehash not installed. Install with: pip install imagehash"
        )
        return None

    try:
        phash = imagehash.phash(image, hash_size=hash_size)  # type: ignore[arg-type]
        return str(phash)
    except Exception as exc:
        logger.warning("pHash computation failed: %s", exc)
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute the Hamming distance between two hex-encoded pHash values.

    Args:
        hash1: First pHash hex string.
        hash2: Second pHash hex string.

    Returns:
        Number of differing bits. < 10 is typically a near-duplicate.
    """
    # Convert hex strings to integers and XOR
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    xor_val = val1 ^ val2
    # Count set bits
    return xor_val.bit_count()

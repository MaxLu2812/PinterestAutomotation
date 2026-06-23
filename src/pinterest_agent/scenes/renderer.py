"""SceneRenderer — compose collected component values into fluent prompts.

Also builds context-aware negative prompts via ``build_negative_prompt``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_BASE_NEGATIVE = (
    "blurry, low quality, watermark, text, logo, "
    "extra fingers, bad anatomy, deformed"
)

_PLURAL_CLOTHING = frozenset({
    "leggings", "shorts", "tights", "pants", "jeans", "sweatpants", "trousers",
})

_INDOOR_KEYWORDS = frozenset(
    {
        "interior",
        "library",
        "cafe",
        "bedroom",
        "studio",
        "hallway",
        "mansion",
        "office",
        "vanity",
        "window",
        "indoor",
        "reformer",
        "home gym",
        "lounge",
        "bed",
        "nook",
        "fireplace",
    }
)


def _article(word: str) -> str:
    """Return ``'an'``, ``'a'``, or ``''`` depending on the word.

    Returns empty string for pluralia tantum (e.g. leggings, shorts, tights)
    when they appear in the first noun phrase (before ``and`` / ``with``).
    """
    if not word:
        return "a"
    word_lower = word.lower()
    first_part = word_lower.split(" and ")[0].split(" with ")[0]
    if any(plural in first_part for plural in _PLURAL_CLOTHING):
        return ""
    return "an" if word_lower[0] in "aeiou" else "a"


class SceneRenderer:
    """Render component values into a natural-language prompt string."""

    @staticmethod
    def render(components: dict[str, str]) -> str:
        """Compose a fluent, natural prompt from *components*.

        Expected component keys
        -----------------------
        subject, ethnicity, hair, outfit, pose, background,
        lighting, camera, mood, style, composition, accessories

        Returns a multi-sentence prompt string.
        """
        subject = components.get("subject", "woman")
        ethnicity = components.get("ethnicity", "")
        hair = components.get("hair", "")

        # --- Subject phrase ---
        # ethnicity looks like "with chestnut hair"
        # hair looks like "styled in a sleek blowout"
        # → "Elegant woman with chestnut hair styled in a sleek blowout"
        subject_parts = ["Elegant", subject]
        if ethnicity:
            subject_parts.append(ethnicity)
        if hair:
            subject_parts.append(hair)
        subject_phrase = " ".join(subject_parts)

        # --- Outfit phrase ---
        outfit = components.get("outfit", "")
        if outfit:
            a_or_an = _article(outfit)
            if a_or_an:
                outfit_phrase = f"wearing {a_or_an} {outfit}"
            else:
                outfit_phrase = f"wearing {outfit}"
        else:
            outfit_phrase = ""

        # --- Pose + Background ---
        pose = components.get("pose", "")
        background = components.get("background", "")
        if pose and background:
            bg_article = _article(background)
            if bg_article:
                pose_phrase = f"{pose} in {bg_article} {background}"
            else:
                pose_phrase = f"{pose} in {background}"
        elif pose:
            pose_phrase = pose
        else:
            pose_phrase = background or ""

        # --- Lighting + Camera ---
        lighting = components.get("lighting", "")
        camera = components.get("camera", "")
        lighting_suffix = "" if lighting.rstrip().lower().endswith("lighting") else " lighting"
        if lighting and camera:
            light_cam = f"{lighting}{lighting_suffix}, {camera}"
        elif lighting:
            light_cam = f"{lighting}{lighting_suffix}"
        else:
            light_cam = camera or ""

        # --- Mood + Style ---
        mood = components.get("mood", "")
        style = components.get("style", "")
        if mood and style:
            mood_style = f"{mood}, {style}"
        else:
            mood_style = mood or style or ""

        # --- Composition ---
        composition = components.get("composition", "")

        # --- Accessories ---
        accessories = components.get("accessories", "")
        accessories_phrase = f"accessorized with {accessories}" if accessories else ""

        # ---- Build fluent text ----
        # Sentence 1: subject + outfit + pose/background (comma separated)
        first_parts = [subject_phrase]
        if outfit_phrase:
            first_parts.append(outfit_phrase)
        if pose_phrase:
            first_parts.append(pose_phrase)

        sentences: list[str] = [", ".join(first_parts) + "."]

        # Sentence 2: lighting + camera
        if light_cam:
            sentences.append(f"{light_cam[0].upper()}{light_cam[1:]}.")

        # Sentence 3: mood + style
        if mood_style:
            sentences.append(f"{mood_style[0].upper()}{mood_style[1:]}.")

        # Sentence 4: composition
        if composition:
            sentences.append(f"{composition[0].upper()}{composition[1:]}.")

        # Sentence 5: accessories
        if accessories_phrase:
            sentences.append(f"{accessories_phrase[0].upper()}{accessories_phrase[1:]}.")

        return " ".join(sentences)

    @staticmethod
    def build_negative_prompt(components: dict[str, str]) -> str:
        """Build a context-aware negative prompt from *components*.

        Base negative is always included.  Context-specific additions
        are appended when detected:
        - swimwear / lingerie outfits → add suggestive/nudity terms
        - indoor backgrounds → add overexposed window / harsh shadows
        """
        additions: list[str] = []

        outfit = components.get("outfit", "")
        outfit_lower = outfit.lower()

        if "swimwear" in outfit_lower or "lingerie" in outfit_lower or "bikini" in outfit_lower:
            additions.extend(["suggestive", "nudity", "explicit"])

        background = components.get("background", "")
        bg_lower = background.lower()
        is_indoor = any(kw in bg_lower for kw in _INDOOR_KEYWORDS)
        if is_indoor:
            additions.append("overexposed window, harsh shadows")

        if additions:
            return _BASE_NEGATIVE + ", " + ", ".join(additions)
        return _BASE_NEGATIVE

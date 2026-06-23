# Design: Procedural SceneComposer Engine

## Intent
Replace the current flat YAML-template prompt engine with a procedural, constraint-driven SceneComposer that generates millions of unique, coherent prompts without LLM dependency.

## Architecture

```
SceneComposer
├── SceneDefinition      (YAML: niche, archetypes, components)
├── ConstraintEngine     (rules: if X then Y)
├── BiasResolver         (archetype → weighted component biases)
├── WeightedSelector     (deterministic weighted random: seed→choice)
├── Renderer             (component values → natural language prompt)
└── NegativePromptEngine (computes negative prompt from scene)
```

## Data Flow

```
Seed (int)
  │
  ▼
SceneComposer.generate(niche, archetype, seed)
  │
  ├── 1. Load SceneDefinition (YAML)
  ├── 2. Resolve archetype biases
  ├── 3. For each component:
  │     ├── Apply constraints (filter invalid choices)
  │     ├── Apply biases (adjust weights)
  │     └── WeightedSelect(seed + component_offset)
  ├── 4. Render scene to prompt string
  ├── 5. Build negative prompt
  └── 6. Return Scene (all choices + prompt string)
```

## Component Architecture

### 1. SceneDefinition (YAML)

```yaml
niche: old_money
description: "Timeless luxury, neutral tones, refined elegance"

archetypes:
  old_money_student:
    description: "Young Ivy-league aesthetic"
    biases:
      age: { "18-25": 80, "20-30": 20 }
      outfit: { "linen_blouse_trousers": 40, "tweed_jacket": 30, "cashmere_sweater": 30 }
      background: { "university_library": 50, "campus_garden": 30, "cozy_cafe": 20 }
      pose: { "reading": 40, "candid_walking": 30, "studying": 30 }
      accessories: { "backpack": 50, "book": 40, "watch": 10 }

  old_money_businesswoman:
    description: "Powerful, elegant executive"
    biases:
      age: { "35-50": 60, "40-60": 40 }
      outfit: { "cream_blazer": 35, "silk_blouse_tailored": 35, "trench_coat": 30 }
      background: { "modern_office": 30, "marble_hallway": 25, "rooftop_terrace": 25, "luxury_cafe": 20 }
      pose: { "confident_gaze": 35, "walking_with_purpose": 35, "seated_professional": 30 }
      accessories: { "watch": 40, "handbag": 35, "laptop": 25 }

  old_money_traveler:
    description: "Jet-set luxury traveler"
    biases:
      age: { "25-35": 50, "35-50": 50 }
      outfit: { "trench_coat": 40, "linen_set": 30, "cashmere_wrap": 30 }
      background: { "european_plaza": 30, "yacht_club": 25, "luxury_hotel": 25, "airport_lounge": 20 }
      pose: { "candid_walking": 40, "looking_at_distance": 30, "seated_suitcase": 30 }
      accessories: { "sunglasses": 40, "hat": 30, "leather_bag": 30 }

  old_money_reader:
    description: "Introspective, cultured, literary"
    biases:
      age: { "25-35": 40, "35-50": 40, "40-60": 20 }
      outfit: { "cashmere_sweater": 40, "linen_blouse_trousers": 35, "tweed_jacket": 25 }
      background: { "cozy_library": 40, "cafe_with_books": 25, "garden_bench": 20, "window_nook": 15 }
      pose: { "reading": 50, "looking_up_from_book": 30, "holding_book": 20 }
      accessories: { "book": 60, "glasses": 30, "tea_cup": 10 }

components:
  subject:
    options:
      - { value: "woman", weight: 80 }
      - { value: "man", weight: 15 }
      - { value: "couple", weight: 5 }

  ethnicity:
    options:
      - { value: "with dark brown hair", weight: 30 }
      - { value: "with chestnut hair", weight: 25 }
      - { value: "with blonde hair", weight: 20 }
      - { value: "with silver hair", weight: 10 }
      - { value: "with auburn hair", weight: 15 }

  hair:
    options:
      - { value: "styled in a sleek blowout", weight: 30 }
      - { value: "in soft waves", weight: 25 }
      - { value: "in an elegant updo", weight: 20 }
      - { value: "worn naturally straight", weight: 15 }
      - { value: "in a low chignon", weight: 10 }

  outfit:
    depends_on: []  # no hard constraints, but archetype biases apply
    options:
      - { value: "cream cashmere sweater", weight: 25 }
      - { value: "navy silk blouse with tailored trousers", weight: 25 }
      - { value: "beige trench coat", weight: 20 }
      - { value: "linen blazer and matching trousers", weight: 15 }
      - { value: "cream silk dress", weight: 10 }
      - { value: "tweed jacket with turtleneck", weight: 5 }

  pose:
    options:
      - { value: "reading a book", weight: 20 }
      - { value: "walking confidently", weight: 20 }
      - { value: "gazing at the camera", weight: 15 }
      - { value: "looking out a window", weight: 15 }
      - { value: "seated with crossed legs", weight: 10 }
      - { value: "holding a coffee cup", weight: 10 }
      - { value: "adjusting a blazer", weight: 5 }
      - { value: "leaning against a doorframe", weight: 5 }

  background:
    constraints:
      - if: { outfit_contains: "swimwear" }
        then: { only: ["beach", "pool_deck", "boardwalk"] }
      - if: { outfit_contains: ["cashmere", "blazer", "tweed"] }
        then: { only: ["luxury_cafe", "library", "mansion_interior", "office"] }
    options:
      - { value: "luxury cafe with natural light", weight: 25 }
      - { value: "grand library with tall windows", weight: 20 }
      - { value: "minimalist modern mansion interior", weight: 20 }
      - { value: "elegant marble hallway", weight: 15 }
      - { value: "rooftop terrace overlooking the city", weight: 10 }
      - { value: "garden path with classical statues", weight: 10 }

  lighting:
    options:
      - { value: "golden hour", weight: 30 }
      - { value: "soft natural window light", weight: 25 }
      - { value: "candlelit warm glow", weight: 20 }
      - { value: "overcast diffused", weight: 15 }
      - { value: "dramatic chiaroscuro", weight: 10 }

  camera:
    options:
      - { value: "85mm lens", weight: 35 }
      - { value: "50mm lens", weight: 25 }
      - { value: "35mm lens", weight: 20 }
      - { value: "medium format", weight: 20 }

  mood:
    options:
      - { value: "effortless sophistication", weight: 30 }
      - { value: "quiet luxury", weight: 25 }
      - { value: "timeless grace", weight: 20 }
      - { value: "refined confidence", weight: 15 }
      - { value: "contemplative elegance", weight: 10 }

  accessories:
    options:
      - { value: "a classic watch", weight: 25 }
      - { value: "a structured leather handbag", weight: 25 }
      - { value: "gold hoop earrings", weight: 20 }
      - { value: "a silk scarf", weight: 15 }
      - { value: "a leather-bound journal", weight: 10 }
      - { value: "pearl necklace", weight: 5 }

  style:
    options:
      - { value: "editorial fashion photography", weight: 35 }
      - { value: "timeless portraiture", weight: 25 }
      - { value: "candid lifestyle", weight: 20 }
      - { value: "vintage film aesthetic", weight: 20 }

  composition:
    options:
      - { value: "portrait orientation, subject in center frame", weight: 30 }
      - { value: "full body shot", weight: 25 }
      - { value: "three-quarter length", weight: 20 }
      - { value: "environmental portrait", weight: 15 }
      - { value: "detail shot", weight: 10 }
```

### 2. ConstraintEngine

Rules that override component choices based on other selections:

```python
class ConstraintEngine:
    rules: list[ConstraintRule]
    
    def apply(self, scene: Scene) -> Scene:
        """Filter invalid options, raise conflicts, resolve dependencies."""
```

Rule types:
- `if_outfit_then_background` — if outfit has X, background must be from Y set
- `if_archetype_then_accessories` — archetype biases accessories
- `excludes` — certain combinations cannot coexist (e.g. swimwear + library)

### 3. BiasResolver

Archetype biases that adjust component weights before selection:

```python
class BiasResolver:
    def resolve(self, niche_def: dict, archetype: str) -> dict:
        """Return a bias map: component → { choice → weight_modifier }"""
```

Biases are **multiplied** with base weights, not replaced. An archetype can make a choice 3x more likely, but never force it to 100%.

### 4. WeightedSelector

Deterministic weighted random selection:

```python
class WeightedSelector:
    @staticmethod
    def select(options: list[WeightedOption], seed: int) -> str:
        """
        Weighted random selection using seed.
        Same seed + same options = same result.
        Uses random.Random(seed) for determinism.
        """
```

Each component gets a unique seed offset: `seed + hash(component_name)`. This ensures changing one component doesn't cascade to others.

### 5. Renderer

```python
class SceneRenderer:
    @staticmethod
    def render(scene: Scene) -> str:
        """Compose scene components into a natural, fluent prompt."""
        
    @staticmethod
    def build_negative_prompt(scene: Scene) -> str:
        """Build context-aware negative prompt."""
```

Rendering logic:
- Subject + ethnicity + hair → "Elegant brunette woman with chestnut hair in soft waves"
- Outfit → "wearing a cream cashmere sweater"
- Pose + background → "reading a book in a grand library with tall windows"
- Lighting + camera → "golden hour lighting, 85mm lens"
- Style + mood + composition → "editorial fashion photography, timeless grace, portrait orientation"
- Accessories → "accessorized with a classic watch and gold hoop earrings"

### 6. NegativePromptEngine

```python
class NegativePromptEngine:
    @staticmethod
    def build(scene: Scene) -> str:
        """
        Base negative: blurry, low quality, watermark, text, logo, extra fingers, bad anatomy
        Context additions:
          - If swimwear: "suggestive, nudity, explicit"
          - If indoor: "overexposed window, harsh shadows"
        """
```

## Scene Output Object

```python
@dataclass
class Scene:
    niche: str
    archetype: str
    seed: int
    components: dict[str, str]  # component_name → chosen value
    prompt: str                 # rendered prompt
    negative_prompt: str        # rendered negative prompt
    weights_used: dict          # for analytics/debug
    constraints_applied: list[str]  # which constraints fired
```

## File Layout

```
src/pinterest_agent/scenes/
├── __init__.py
├── composer.py              # SceneComposer — main orchestrator
├── renderer.py              # SceneRenderer — component→text
├── negative_prompt.py       # NegativePromptEngine
├── constraints.py           # ConstraintEngine
├── bias.py                  # BiasResolver
├── selector.py              # WeightedSelector
└── definitions/             # YAML scene definitions
    ├── old_money.yaml
    ├── coquette.yaml
    ├── pilates.yaml
    └── ...
```

## Backward Compatibility

The current `prompts/engine.py` (PromptEngine) and the new SceneComposer coexist. The CLI flag `--composer` switches between them:

```
pinterest-agent generate-prompts --composer scene --niche old_money --archetype businesswoman --count 10
```

Default remains the current template engine. SceneComposer is opt-in during V1.

## Millions of Combinations

For `old_money` with 4 archetypes:
- Subject: 3
- Ethnicity: 5
- Hair: 5
- Outfit: 6
- Pose: 8
- Background: 6
- Lighting: 5
- Camera: 4
- Mood: 5
- Accessories: 6
- Style: 4
- Composition: 5

= 3×5×5×6×8×6×5×4×5×6×4×5 = **51,840,000** combinations per niche

With 9 niches = **~466 million** unique scenes. Each with a unique prompt.

## Risks

- Complexity: constraint engine can have conflicts (resolved deterministically by priority)
- YAML size: each niche definition is larger than current templates (acceptable)
- Migration: existing template workflows unaffected

## Next Steps

1. Implement `scenes/` package with composer, renderer, selector
2. Create 2-3 YAML definitions (old_money, coquette, pilates)
3. CLI flag `--composer scene`
4. Tests: deterministic seed output, constraint enforcement, archetype biases

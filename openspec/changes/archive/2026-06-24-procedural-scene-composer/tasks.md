# Tasks: Procedural SceneComposer Engine

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

## Phase 1: Core Engine

- [x] 1.1 `scenes/selector.py` — WeightedSelector: deterministic weighted random with seed
- [x] 1.2 `scenes/bias.py` — BiasResolver: archetype → component weight multipliers
- [x] 1.3 `scenes/constraints.py` — ConstraintEngine: if-outfit-then-background rules
- [x] 1.4 `scenes/renderer.py` — SceneRenderer: component values → fluent natural prompt (NegativePromptEngine inlined)
- [x] 1.5 `scenes/negative_prompt.py` — NegativePromptEngine: inlined into renderer.py (no separate module needed)
- [x] 1.6 `scenes/composer.py` — SceneComposer: orchestrator tying all components together
- [x] 1.7 `scenes/__init__.py` — package init, public exports

## Phase 2: YAML Definitions

- [x] 2.1 `scenes/definitions/old_money.yaml` — 4 archetypes, 12 components with weights
- [x] 2.2 `scenes/definitions/coquette.yaml` — coquette aesthetic scene definition
- [x] 2.3 `scenes/definitions/pilates.yaml` — pilates/fitness scene definition

## Phase 3: CLI Integration

- [x] 3.1 `cli/generate.py` — `--composer scene` flag, archetype parameter
- [x] 3.2 Wire SceneComposer into existing generate-prompts command

## Phase 4: Tests

- [x] 4.1 Test: WeightedSelector determinism (same seed → same result)
- [x] 4.2 Test: BiasResolver archetype weight adjustments
- [x] 4.3 Test: ConstraintEngine outfit→background rules
- [x] 4.4 Test: SceneRenderer output format
- [x] 4.5 Test: SceneComposer end-to-end (seed → valid prompt)
- [x] 4.6 Test: CLI flag registration
- [x] 4.7 Test: ~466M combination projection (verify no hardcoded limits)

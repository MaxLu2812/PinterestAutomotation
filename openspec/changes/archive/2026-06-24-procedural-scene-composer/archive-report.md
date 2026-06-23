# Archive Report: Procedural SceneComposer Engine

**Archived**: 2026-06-24
**Change**: procedural-scene-composer
**Status**: success — cycle complete

## Summary

Replaced flat YAML template variable substitution with a weighted, constraint-driven procedural scene composition engine. Generates millions of unique, coherent prompts without LLM dependency.

## What Was Built

- **SceneComposer** — orchestrator tying all components together (`scenes/composer.py`)
- **WeightedSelector** — deterministic weighted random with seed (`scenes/selector.py`)
- **BiasResolver** — archetype → component weight multipliers (`scenes/bias.py`)
- **ConstraintEngine** — if-outfit-then-background rules (`scenes/constraints.py`)
- **SceneRenderer** — component values → fluent natural prompt with inline NegativePromptEngine (`scenes/renderer.py`)
- **CLI integration** — `--composer scene` flag in `cli/generate.py`
- **YAML definitions** — 3 scene definition files (old_money, coquette, pilates)

## Files Created

10 new files:
| File | Purpose |
|------|---------|
| `src/pinterest_agent/scenes/__init__.py` | Package init, public exports |
| `src/pinterest_agent/scenes/composer.py` | SceneComposer orchestrator |
| `src/pinterest_agent/scenes/selector.py` | WeightedSelector |
| `src/pinterest_agent/scenes/bias.py` | BiasResolver |
| `src/pinterest_agent/scenes/constraints.py` | ConstraintEngine |
| `src/pinterest_agent/scenes/renderer.py` | SceneRenderer (with NegativePromptEngine inlined) |
| `src/pinterest_agent/scenes/definitions/old_money.yaml` | Old Money aesthetic definition |
| `src/pinterest_agent/scenes/definitions/coquette.yaml` | Coquette aesthetic definition |
| `src/pinterest_agent/scenes/definitions/pilates.yaml` | Pilates/fitness definition |
| `tests/test_scenes.py` | Integration tests for scene composer |

## Files Modified

2 files modified:
| File | Change |
|------|--------|
| `cli/generate.py` | Added `--composer scene` flag, wired SceneComposer into generate-prompts command |
| `cli/__init__.py` | Exposed new CLI module |

## Task Completion

**15/15 tasks** — all marked [x] in tasks.md

- Phase 1 (Core Engine): 7/7 ✅
- Phase 2 (YAML Definitions): 3/3 ✅
- Phase 3 (CLI Integration): 2/2 ✅
- Phase 4 (Tests): 3/3 ✅

## Verification

- **59 unit tests pass**: 49 original + 10 regression tests for judgment-day fixes
- **16 snapshot tests pass**: 1000-scene generation quality suite
- **245/247 total pass** (2 pre-existing publishing failures unrelated to SceneComposer)
- **Judgment Day (Round 1)**: APPROVED ✅ after 4 confirmed fixes
- **Linguistic Polish (Round 2)**: APPROVED ✅

## Round 2 — Linguistic Polish (2026-06-24)

Applied after initial archive based on user request for final quality pass:

| Fix | Description |
|-----|-------------|
| Background article | `pose in {article} {background}` — adds proper article before all backgrounds |
| Plural clothing | Added "trousers" to `_PLURAL_CLOTHING` |
| Indoor keywords | Added "bed", "nook", "fireplace" to `_INDOOR_KEYWORDS` for negative prompt |
| Lighting dedup | Skip "lighting" suffix when value already ends in "lighting" (e.g. "dramatic side lighting") |
| Snapshot suite | `tests/test_scene_renderer_snapshot.py` — 16 tests over 1000 generated scenes |

### Snapshot Metrics (1000 scenes)
- **Uniqueness ratio**: 99.90% (999/1000 unique prompts)
- **Avg prompt length**: 312 chars (min=257, max=369)
- **Archetypes seen**: 10/10
- **Backgrounds seen**: 17/17
- **Impossible combinations**: 0
- **Malformed English**: 0
- **Adjacent duplicates**: 0
- **Repeated phrases**: 0

## Archive Contents

- `proposal.md` ✅
- `design.md` ✅ (served as single spec artifact — no delta specs directory)
- `tasks.md` ✅ (15/15 tasks complete)
- `archive-report.md` ✅ (this file)

## Notes

- No delta specs in `specs/` directory existed — the design document was the single spec artifact. Spec merge step was skipped as intentional per the orchestrator.
- Round 2 (linguistic polish) added after initial archive — archive report retroactively updated with snapshot results.
- All artifacts preserved in archive for audit trail.

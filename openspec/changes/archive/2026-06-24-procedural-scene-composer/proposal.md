# Proposal: Procedural SceneComposer Engine

## Intent
Replace flat YAML template variable substitution with a weighted, constraint-driven procedural scene composition engine. Generate millions of unique, coherent prompts without LLM dependency.

## Scope

### In Scope
- SceneDefinition YAML format (niche, archetypes, components, constraints)
- WeightedSelector (deterministic weighted random with seed)
- ConstraintEngine (if-outfit-then-background rules)
- BiasResolver (archetype → component weight multipliers)
- SceneRenderer (component values → fluent natural prompt)
- NegativePromptEngine (context-aware negative prompt builder)
- SceneComposer orchestrator
- CLI `--composer scene` flag (parallel to existing engine)
- 2–3 initial YAML definitions (old_money, coquette, pilates)

### Out of Scope (V1 of this feature)
- LLM enhancement (disabled by default)
- Cross-niche archetypes
- Scene validation/lint tool
- Analytics on which choices perform best

## Key Design Decisions
1. **No LLM dependency** — pure procedural generation works offline
2. **Deterministic seeds** — same seed always produces the same scene
3. **Weighted + biased** — base weights × archetype bias multipliers
4. **~466M+ combinations** across 9 niches
5. **Coexists with current engine** — opt-in via CLI flag

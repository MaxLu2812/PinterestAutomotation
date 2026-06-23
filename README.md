# Pinterest Aesthetic Automation

Automated Pinterest content agent for SFW aesthetic niches.
Generates AI prompts → creates images → publishes pins.

## Architecture

```
Prompt Sources ─┬── GPT-4o-mini (LLM)
                │
                └── SceneComposer V1 (procedural) ◄── 2.38B combinations
                        │
                   Prompt Queue (SQLite)
                        ↓
               Image Generation (local/cloud)
                        ↓
                  Image Store (FS + SQLite)
                        ↓
               Pin Publisher (Pinterest API v5)
                        ↓
                  Scheduler (APScheduler)
```

### SceneComposer V1 — Procedural Prompt Engine

Replaces LLM dependency with deterministic weighted-random scene generation.
Generates 2.38 billion unique, coherent prompts across 3 niche definitions.

| Component | Role |
|-----------|------|
| **WeightedSelector** | Deterministic pick via `random.Random(seed)` — same seed always produces same scene |
| **BiasResolver** | Archetype-specific weight multipliers (× bias / 100); unlisted options get ×0.1 deprioritisation |
| **ConstraintEngine** | Filters invalid outfit→background pairs; falls back to all options if constraint would empty the list |
| **SceneRenderer** | Composes components into fluent English sentences with context-aware negative prompts |
| **NegativePromptEngine** | Adds suggestive/nudity terms for swimwear/lingerie; adds overexposed window for indoor scenes |

Key properties:
- **Deterministic**: seed 42 always produces identical scene
- **No LLM**: pure procedural generation, zero API cost
- **Variety**: 2.38B unique combinations across 10 archetypes
- **Safety**: constraint rules prevent impossible outfit/background pairs
- **Quality**: validated across 1000-scene snapshot corpus (99.9% uniqueness, 0 malformed)

Usage:

```bash
# List available scene niches
pinterest-agent generate-prompts --composer scene

# Generate 10 old_money scenes with random archetypes
pinterest-agent generate-prompts --composer scene --niche old_money --count 10

# Generate with specific archetype
pinterest-agent generate-prompts --composer scene --niche old_money --archetype old_money_reader --count 5
```

Snapshot corpus metrics (1000 scenes):

| Metric | Value |
|--------|-------|
| Uniqueness ratio | 99.90% |
| Average length | 312 chars |
| Archetypes seen | 10/10 |
| Impossible combos | 0 |
| Adjacent duplicates | 0 |
| Repeated phrases | 0 |

## Quick Start

1. **Install:**

   ```bash
   pip install -e ".[dev]"
   ```

   For local image generation (AMD GPU on Windows, or NVIDIA GPU):

   ```bash
   pip install -e ".[dev,local]"
   ```

2. **Configure:**

   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml with your settings
   ```

3. **Set tokens:**

   ```bash
   export PINTEREST_TOKEN=your_pinterest_token
   export OPENAI_API_KEY=your_openai_key
   ```

4. **Generate prompts:**

   ```bash
   pinterest-agent generate-prompts --niche old_money --count 10
   ```

5. **Generate images:**

   ```bash
   pinterest-agent generate-images --count 10
   ```

6. **Publish:**

   ```bash
   pinterest-agent publish-pins --count 5
   ```

7. **Schedule:**

   ```bash
   pinterest-agent scheduler-run
   ```

## Configuration

See `config.yaml` for all settings. Key sections:

| Section     | Description                             |
| ----------- | --------------------------------------- |
| `pinterest` | API credentials and OAuth settings      |
| `publishing`| Schedule, windows, rate limits          |
| `generator` | AI backends, output size, quality       |
| `retry`     | Retry/backoff settings                  |
| `boards`    | Niche → board name mapping              |
| `logging`   | Level, file, rotation                   |

## CLI Reference

| Command             | Description                       |
| ------------------- | --------------------------------- |
| `generate-prompts`  | Generate prompts (LLM or `--composer scene` with `--archetype`)|
| `generate-images`   | Generate images from prompt queue |
| `publish-pins`      | Publish images to Pinterest       |
| `scheduler-run`     | Start scheduled publishing        |
| `list-prompts`      | List prompt queue                 |
| `list-images`       | List image store                  |
| `list-publications` | List publication history          |
| `status`            | System overview                   |
| `stats`             | Usage statistics                  |
| `doctor`            | Run diagnostics                   |
| `show-config`       | Display current configuration     |
| `validate-config`   | Validate config file              |
| `reload-config`     | Re-read config file               |

## Doctor

Run diagnostics before first use to verify everything is set up correctly:

```bash
pinterest-agent doctor --fix
```

The `--fix` flag auto-creates missing directories.

## Supported Niches

- Old Money Women
- Coquette Aesthetic
- Lingerie Aesthetic (SFW)
- Pilates Girl
- Luxury Beauty
- Dark Feminine
- Soft Glam Makeup
- Elegant Swimwear
- Fashion Photography

## Requirements

- Python 3.11+
- SQLite (included)
- GPU recommended for local generation (AMD/NVIDIA)

## License

MIT

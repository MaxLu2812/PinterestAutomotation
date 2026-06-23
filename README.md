# Pinterest Aesthetic Automation

Automated Pinterest content agent for SFW aesthetic niches.
Generates AI prompts → creates images → publishes pins.

## Architecture

```
Prompt Engine (GPT-4o-mini)
       ↓
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
| `generate-prompts`  | Generate AI prompts from templates|
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

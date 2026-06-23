# Design: Pinterest Aesthetic Automation

## Technical Approach

Three standalone CLI phases decoupled through SQLite — no daemon, no broker.

```
Phase 1 (Prompt Gen)    GPT-4o-mini → prompt_queue (SQLite)
Phase 2 (Image Gen)     CLI batch → failover chain → FS + metadata
Phase 3 (Publishing)    APScheduler → Pinterest API v5 → live pins
```

Each phase runs independently, supports resumption, and communicates exclusively through database state (status columns: `pending → processing → done/failed`).

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Package layout | `src/pinterest_agent/` domain subpackages | Flat module | PEP 517 src-layout prevents import confusion |
| Generator backend | `abc.ABC` base + factory | Protocol classes | Zero-dep contract, runtime selection from config |
| Data access | Repository pattern w/ SQLite impl | Raw SQL, ORM | Isolates persistence — swapping to PostgreSQL means one new impl per repo |
| Queue mechanism | SQLite status column | Redis, RabbitMQ | Zero infra, 3 CLI-batch phases don't need event-driven broker. `SELECT WHERE status=pending` is sufficient |
| Image storage | FS + SQLite metadata | S3, BLOBs | ~500MB for 1000 images. Local FS is free and fast. Metadata in DB enables querying without FS scans |
| AMD GPU | `diffusers` + `torch-directml` (Win) / ROCm (Linux) | ONNX Runtime | `torch-directml` maps PyTorch to DirectML on AMD. Diffusers is community standard for SD pipelines |
| Provider failover | Chain-of-responsibility | Round-robin | Cost-optimal: tries free/cheapest first, iterates on failure |
| Prompt templates | YAML files w/ `{variable}` placeholders | JSON, code dicts | Most human-editable format for non-technical aesthetic content |

## Data Flow

```
Phase 1: GPT-4o-mini + YAML template → prompt_text → prompt_queue (status=pending)
Phase 2: dequeue(pending) → ImageGenerator.generate() [local→HF→Replicate→Together]
         → image .png → image_store table + FS file
Phase 3: APScheduler cron → find_unpublished() → PinterestClient.create_pin()
         → update pin_id, status=published
```

Dedup checkpoints: (1) prompt hash before enqueue, (2) perceptual hash before FS write, (3) Pinterest API dedup on publish.

## File Changes (all Create — greenfield)

| File | Role |
|------|------|
| `pyproject.toml` | Project metadata, deps, entry points |
| `src/pinterest_agent/domain/models.py` | Prompt, Image, Pin dataclasses |
| `src/pinterest_agent/domain/repositories.py` | Abstract repo interfaces |
| `src/pinterest_agent/generators/base.py` | `ImageGenerator` ABC |
| `src/pinterest_agent/generators/local_diffusers.py` | Primary: AMD DirectML/ROCm |
| `src/pinterest_agent/generators/hf_inference.py` | Secondary: HF Inference API |
| `src/pinterest_agent/generators/replicate_gen.py` | Fallback |
| `src/pinterest_agent/generators/together_gen.py` | Fallback |
| `src/pinterest_agent/prompts/engine.py` | GPT-4o-mini prompt generation |
| `src/pinterest_agent/prompts/templates/*.yaml` | Aesthetic YAML templates |
| `src/pinterest_agent/publishers/pinterest_client.py` | Pinterest API v5 client |
| `src/pinterest_agent/scheduler/scheduler.py` | APScheduler daily jobs |
| `src/pinterest_agent/db/connection.py` | SQLite connection manager |
| `src/pinterest_agent/db/repositories/prompt_repo.py` | PromptRepository impl |
| `src/pinterest_agent/db/repositories/image_repo.py` | ImageRepository impl |
| `src/pinterest_agent/db/repositories/analytics_repo.py` | Analytics tracking impl |
| `src/pinterest_agent/dedup/perceptual_hash.py` | pHash computation |
| `src/pinterest_agent/utils/image_utils.py` | Resize, safety check |
| `src/pinterest_agent/cli/main.py` | Click root |
| `src/pinterest_agent/cli/generate.py` | `generate prompts/images` |
| `src/pinterest_agent/cli/publish.py` | `publish run/schedule` |
| `src/pinterest_agent/config/loader.py` | YAML + env config |
| `tests/` | Unit, integration, E2E test files |

## Interfaces / Contracts

**`ImageGenerator`** (ABC): `generate(prompt) → ImageResult`, `is_available() → bool`, `model_name() → str`. All backends implement this.

**`PromptRepository`** (ABC): `enqueue(prompt)`, `dequeue(limit)`, `mark_done(id)`, `mark_failed(id, error)`.

**`ImageRepository`** (ABC): `save(image)`, `find_by_prompt_hash(h)`, `find_by_perceptual_hash(h)`, `find_unpublished(limit)`.

**`PinPublisher`** (ABC): `create_pin(image, board_id) → PinResult`, `refresh_token()`.

**Core entities**: `Prompt(id, aesthetic, template, variables, text, status)`, `Image(id, prompt_id, prompt_hash, phash, file_path, status, pin_id)` — both `@dataclass`.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Repositories | In-memory SQLite, test CRUD + transitions |
| Unit | Generator interface | Mock backends, test failover chain |
| Unit | Dedup | Known images, verify hash collision |
| Integration | HF Inference | 1 real API call (free tier) |
| Integration | Pinterest | Sandbox board, verify pin_id returned |
| E2E | Full pipeline | Mock GPT + image API, real SQLite |

## Migration / Rollout

Greenfield — no migration. Schema applied via `db/migrations/` on first CLI invocation.

## Open Questions

- [ ] Pinterest developer app registration — user action needed at developers.pinterest.com
- [ ] DirectML compatibility matrix — which AMD GPUs (RX 6000/7000?) support `torch-directml` (Windows)


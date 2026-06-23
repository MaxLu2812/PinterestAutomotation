# Tasks: Pinterest Aesthetic Automation

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR |
|------|------|-----------|
| 1 | Project scaffold + config + DB schema | PR 1 |
| 2 | Prompt engine: YAML templates + GPT-4o-mini queue | PR 2 |
| 3 | Image gen: provider abstraction + backends + resize | PR 3 |
| 4 | Publishing: Pinterest API v5 + APScheduler | PR 4 |
| 5 | Reliability: retries, failover, dedup, logging | PR 5 |
| 6 | CLI polish, tests, docs | PR 6 |

## Phase 1: Foundation (PR1)

- [x] 1.1 `pyproject.toml` — project metadata, deps, entry points
- [x] 1.2 `src/pinterest_agent/__init__.py` — package layout with domain stubs
- [x] 1.3 `config/loader.py` — YAML + env-var config with startup validation
- [x] 1.4 `domain/models.py` — Prompt, Image, Pin dataclasses
- [x] 1.5 `domain/repositories.py` — abstract repo interfaces
- [x] 1.6 `db/connection.py` — SQLite connection manager + schema init
- [x] 1.7 `db/repositories/prompt_repo.py` — PromptRepository SQLite impl
- [x] 1.8 `db/repositories/image_repo.py` — ImageRepository SQLite impl
- [x] 1.9 `db/repositories/analytics_repo.py` — analytics tracking impl

## Phase 2: Prompt Engine (PR2)

- [x] 2.1 `prompts/templates/*.yaml` — sample templates for Old Money + Coquette niches (also pilates, lingerie_aesthetic)
- [x] 2.2 `prompts/engine.py` — GPT-4o-mini rendering, variable seeding, dup detection, retry
- [x] 2.3 Tests: template validation, API retry, duplicate skip, FIFO queue

## Phase 3: Image Generation (PR3)

- [x] 3.1 `generators/base.py` — ImageGenerator ABC + provider registry
- [x] 3.2 `generators/local_diffusers.py` — Diffusers (DirectML/ROCm)
- [x] 3.3 `generators/hf_inference.py` — HF Inference API backend
- [ ] 3.4 `generators/replicate_gen.py` — Replicate API fallback (deferred to V2)
- [ ] 3.5 `generators/together_gen.py` — Together AI fallback (deferred to V2)
- [x] 3.6 `dedup/perceptual_hash.py` — pHash computation
- [x] 3.7 `utils/image_utils.py` — resize 1000×1500, safety checker

## Phase 4: Publishing (PR4)

- [x] 4.1 `publishers/pinterest_client.py` — Pinterest API v5: OAuth2, board resolution, pin creation
- [x] 4.2 `scheduler/scheduler.py` — APScheduler: time windows, rate limits, oldest-unused selection

## Phase 5: Reliability (PR5)

- [x] 5.1 Retry + provider failover chain in `generators/base.py`
- [x] 5.2 Prompt hash dedup in `prompts/engine.py`
- [x] 5.3 Perceptual hash dedup wired into image save pipeline
- [x] 5.4 Structured logging across all phases

## Phase 6: Polish (PR6)

- [x] 6.1 `cli/main.py` — Click root group (cleaned up, added --version, epilog, status/stats/doctor imports)
- [x] 6.2 `cli/generate.py` — final polish (verified — commands are clean and well-documented)
- [x] 6.3 `cli/publish.py` — already done, verified
- [x] 6.4 Unit tests: config loader, repositories, dedup (in-memory SQLite, mock backends)
- [x] 6.5 Integration tests: DB lifecycle, config loading, file system operations, repository counts
- [x] 6.6 E2E test: mock GPT + image API, real SQLite — full pipeline tested
- [x] 6.7 README with setup, config, usage

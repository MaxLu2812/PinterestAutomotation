# Proposal: Pinterest Aesthetic Automation

## Intent

3-phase agent: separate prompt gen, image gen, Pinterest publishing. Weekly batch gen + daily scheduled publishing across accounts, no cloud GPU needed.

## Scope

### In Scope
- GPT-4o-mini prompt pipeline with template variables
- Pluggable image gen (HF Inference API, local Diffusers, ComfyUI)
- Pinterest API v5 publisher + APScheduler (~10 pins/day)
- Multi-account YAML config, SQLite, Click CLI
- 3-level dedup (prompt hash, perceptual hash, Pinterest)

### Out of Scope
- Web UI / analytics / auto-scaling
- Platforms beyond Pinterest
- User registration flow

## Capabilities

### New Capabilities
- `prompt-engine`: Template prompts via GPT-4o-mini → SQLite queue
- `image-generation`: Pluggable backend, 1000×1500 resize
- `pinterest-publisher`: OAuth, pin creation, board mgmt (API v5)
- `scheduler`: APScheduler daily publishing + rate limiting
- `config-management`: YAML per-account config, env-var tokens, multi-niche

### Modified Capabilities
None — greenfield.

## Free Image Generation Research

| Option | Free? | Quality | Verdict |
|--------|-------|---------|---------|
| **HF Inference Providers** | $0.10/mo | Excellent | **Primary cloud** |
| Replicate | None ($0.003/img) | Excellent | Paid fallback |
| Together AI | None ($0.0027/img) | Good | Cheaper paid |
| Google Colab | Free T4, sessions expire | Excellent | Prototyping |
| Local Diffusers | Free (needs GPU) | Excellent | **Primary local** |

HF covers ~80 free FLUX.1-dev images/mo. Local Diffusers for bulk at $0 API cost. Backend abstraction makes both swappable.

## Approach

1. **Prompt gen** → GPT-4o-mini fills templates → SQLite queue
2. **Image gen** → CLI batch processes queue → local fs + metadata
3. **Publish** → APScheduler reads image store → 10 pins/day via Pinterest SDK

Dedup at every stage. Winners auto-boost.

## Affected Areas

| Area | Impact |
|------|--------|
| `src/pinterest_agent/` | New (greenfield) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Pinterest API approval | Med | Sandbox boards, appeal with use case |
| OAuth token expiry | High | Refresh token rotation |
| HF credits insufficient | Med | Pluggable backends; local gen free |
| Gen quality inconsistency | Med | Track + boost winning templates |

## Rollback Plan

Stop scheduler → halt publishing. Pins stay. Image gen re-runnable. Git revert for config.

## Dependencies

- Pinterest Developer app registration (user action)
- OpenAI API key (GPT-4o-mini)
- Hugging Face token (HF Inference)
- Python 3.11+ with `diffusers`, `pillow`, `apscheduler`, `click`

## Success Criteria

- [ ] 10 pins/day across 2+ boards
- [ ] 1000 images in single CLI batch run
- [ ] Multi-account config with different niches works
- [ ] At least one free cloud + one local backend operational

# Proposal: Production Onboarding v1

## Intent

Take the V1 codebase from dev (mocked) to production with a real Pinterest account and AI services. Each stage is a gate — the next only starts when the previous is verified.

## Scope

### In Scope
- Pinterest OAuth 2.0 setup guide (app registration, auth code flow, token storage)
- API key provisioning: OpenAI (GPT-4o-mini), Hugging Face Inference, Pinterest credentials
- Production-ready `config.yaml` defaults (single-niche, correct board mapping)
- First board "Old Money Women" creation + board mapping config + CLI verification
- First niche `old_money` with template verification
- Generate 10 prompts via CLI → verify in SQLite
- Generate 5 images via CLI (local AMD GPU) → verify in `storage/`
- Publish 3 pins to real Pinterest → verify in DB + pin exists on board
- Scheduler config verification
- Troubleshooting guide for credentials, rate limits, GPU issues

### Out of Scope
- Multi-account or multi-niche publishing (others deferred)
- Analytics, A/B testing, or pin performance tracking
- Cloud image generation (user runs local GPU only)
- CI/CD pipeline or automated deployment

## Capabilities

### New Capabilities
None — pure config changes + onboarding documentation, no spec-level behavior changes.

### Modified Capabilities
None — all existing specs (config-management, prompt-engine, image-generation, pinterest-publisher, scheduler) cover the required behavior as-is.

## Approach

8 sequential gates. Each stage has a verification command; failure means stop, troubleshoot, and retry before proceeding.

1. **Credentials** → Register Pinterest app → OAuth 2.0 auth-code flow → tokens → `.env`
2. **API Keys** → Set OpenAI key, HF token, Pinterest client_id/secret in env vars
3. **Board** → Create "Old Money Women" in Pinterest UI → map in `config.yaml` → `pinterest-agent list-boards`
4. **Niche** → Configure `old_money` in `config.yaml` → verify template loads from `prompts/templates/`
5. **Prompts** → `pinterest-agent generate-prompts --niche old_money --count 10` → verify in SQLite
6. **Images** → `pinterest-agent generate-images --count 5` → verify images in `storage/` + metadata in DB
7. **Publish** → `pinterest-agent publish-pins --count 3` → verify pin on Pinterest + publication records in DB
8. **Scheduler** → Verify scheduler config, confirm daily windows and rate limits

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `config.yaml` | Modified | Production credentials, single-niche defaults (old_money only), correct board IDs |
| `.env` | New | User-created env file for tokens/secrets |
| `data/pinterest_agent.db` | Populated | First prompts, images, publication records |
| `storage/` | Populated | First generated images |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Pinterest app approval delay | Med | Apply for standard access early; trial access works for initial test pin |
| OAuth token expiry during guide | Low | Include refresh-token flow in guide steps |
| GPU compatibility (AMD DirectML) | Med | Document fallback to HF Inference API free tier |
| First-pin rate limit | Low | 3 pins within 10/day limit; 30-min interval enforced by scheduler |

## Rollback Plan

- **Config**: `git checkout config.yaml` to restore dev defaults
- **Tokens**: Delete `.env` or unset env vars
- **Board**: Delete "Old Money Women" in Pinterest UI
- **DB**: Delete `data/pinterest_agent.db` to reset all state
- **Images**: Clear `storage/` directory

## Dependencies

- Pinterest developer account (user registers at developers.pinterest.com)
- OpenAI API key with GPT-4o-mini access
- Hugging Face token (free tier at huggingface.co/settings/tokens)
- AMD GPU + DirectML (optional — HF Inference API works without GPU)

## Success Criteria

- [ ] First pin published on a real Pinterest board via `pinterest-agent publish-pins`
- [ ] Publication record visible in SQLite (`SELECT * FROM publications`)
- [ ] Scheduler configured and ready for daily publishing
- [ ] All 8 stages verified with passing checks

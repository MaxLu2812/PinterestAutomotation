# First-Run Checklist

> Use this checklist to track your progress through the 8 onboarding gates.
> Check off each item as you complete it.

---

## Before Starting

- [ ] **Python 3.11+ installed**
      Verify: `python --version` → should show `Python 3.11.x` or higher
- [ ] **Pinterest account created**
      At [pinterest.com](https://pinterest.com)
- [ ] **AMD GPU drivers updated** (for local image generation)
      Download from [amd.com](https://www.amd.com/en/support)

---

## Gate 1 — Pinterest Developer App

- [ ] **App registered** at [developers.pinterest.com](https://developers.pinterest.com)
- [ ] **App approved** for standard access (or trial)
- [ ] `client_id` and `client_secret` saved to a secure location

---

## Gate 2 — OAuth Tokens

- [ ] **Access token obtained** (starts with `pina-`)
- [ ] **Refresh token obtained** (starts with `pinr-`)
- [ ] **Tokens added to `.env` file**
      Verify: `pinterest-agent doctor` shows `Pinterest: API reachable`

---

## Gate 3 — API Keys

- [ ] **`.env` file created** from `.env.example`
- [ ] **`OPENAI_API_KEY` set** (or leave blank for passthrough mode)
- [ ] **`HF_TOKEN` set** (or leave blank)
- [ ] **`.env` file sourced** (the CLI reads it automatically from the project root)
      Verify: `pinterest-agent doctor` shows no critical errors

---

## Gate 4 — Board

- [ ] **"Old Money Women" board created** on Pinterest
- [ ] **Board mapped in `config.yaml`** under `boards:`
      Verify: `pinterest-agent doctor` shows Pinterest API reachable

---

## Gate 5 — Niche

- [ ] **`old_money` template file exists** at `src/pinterest_agent/prompts/templates/old_money.yaml`
- [ ] **Template verified**:
      Verify: `pinterest-agent generate-prompts` lists `old_money` in available templates

---

## Gate 6 — Prompts

- [ ] **10 prompts generated** for the `old_money` niche
      Command: `pinterest-agent generate-prompts --niche old_money --count 10`
- [ ] **Prompts visible** in the database
      Verify: `pinterest-agent list-prompts --niche old_money` shows 10 rows

---

## Gate 7 — Images

- [ ] **Images generated** (or skip if no local GPU / HF fallback)
      Command: `pinterest-agent generate-images --count 5`
- [ ] **Images visible** in the database and on disk
      Verify: `pinterest-agent list-images` shows 5 rows with status `generated`
- [ ] **Images exist on disk** at `storage/images/processed/old_money/`

---

## Gate 8 — Publication

- [ ] **First pin published**
      Command: `pinterest-agent publish-pins --count 1`
- [ ] **Pin visible on Pinterest**
      Check your "Old Money Women" board at [pinterest.com](https://pinterest.com)
- [ ] **Publication recorded**
      Verify: `pinterest-agent list-publications` shows 1 record with status `published`
- [ ] **Scheduler configured and ready**
      Verify: `pinterest-agent scheduler-run --dry-run` runs without errors

---

## Done! 🎉

You have a functioning Pinterest automation pipeline. The agent will:

- Generate prompts daily from the Old Money template
- Generate images using your local GPU (or HF fallback)
- Publish pins according to the schedule in `config.yaml`
- Track everything in the SQLite database

### Next Steps

- Monitor daily with `pinterest-agent status` and `pinterest-agent stats --days 7`
- Handle failures with `pinterest-agent retry-prompts`, `pinterest-agent retry-images`,
  `pinterest-agent retry-publications`
- Check the log file at `storage/logs/` for detailed diagnostics

# Production Onboarding Guide

> **Goal**: Take the V1 Pinterest agent from a development setup to a running
> production pipeline — generating prompts, images, and publishing real pins
> to Pinterest.
>
> This guide has **8 sequential gates**. Do NOT skip ahead. Each gate depends
> on the previous one being verified.

---

## Prerequisites

- **Python 3.11+** installed ([python.org](https://python.org))
- **Pinterest account** — create one at [pinterest.com](https://pinterest.com)
- **(Optional) OpenAI account** — for GPT-4o-mini prompt refinement. Skip if
  you only want template-based prompts (passthrough mode).
- **(Optional) Hugging Face account** — for HF Inference API image generation
  fallback if your GPU isn't supported.

---

## Gate 1: Pinterest Developer App

**Goal**: Register a Pinterest app and get `client_id` / `client_secret`.

**Time**: 15–30 minutes (may include approval wait time).

**Prerequisites**: Pinterest account.

**Steps**:

1. Go to [developers.pinterest.com](https://developers.pinterest.com).
2. Click **Create app** (top-right).
3. Enter an app name (e.g., `Pinterest Automotation V1`).
4. Under **App owner** select your personal account.
5. Click **Create**.
6. Once created, note your **App ID** (`client_id`) and **App Secret**
   (`client_secret`). Store them securely.
7. Request **Standard Access** (not trial-only). Trial access works for
   initial testing but has strict rate limits.
   - Go to your app settings → **Access** → change from **Trial** to
     **Standard** and submit the request.
   - Approval can take a few hours to a few days. You can proceed with
     subsequent gates once approved.

**Expected output**:
```
Client ID:    1234567890123456789
Client Secret: abcdef1234567890abcdef1234567890abcdef12
```

**Verify**:
- Your app shows **Active** status in the Pinterest Developer Console.
- You have the `client_id` and `client_secret` values saved somewhere safe.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| "App name already taken" | Choose a more specific name |
| "Access denied, trial only" | You must request standard access before publishing |
| Can't find App Secret | Regenerate it in the app settings page |

---

## Gate 2: OAuth Tokens

**Goal**: Generate `PINTERNET_TOKEN` (access token) and
`PINTEREST_REFRESH_TOKEN` via the OAuth 2.0 Authorization Code flow.

**Time**: 10 minutes.

**Prerequisites**: Gate 1 completed (client_id and client_secret saved).

**Steps**:

1. Open your browser and build the authorization URL:

   ```
   https://www.pinterest.com/oauth/?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:8000/callback&response_type=code&scope=boards:read,boards:write,pins:read,pins:write
   ```

   Replace `YOUR_CLIENT_ID` with your actual App ID from Gate 1.

2. Visit that URL. You'll be prompted to log in and authorize the app.
3. After authorizing, Pinterest redirects to:

   ```
   http://localhost:8000/callback?code=AUTHORIZATION_CODE
   ```

   Your browser will show a connection error (since nothing is listening on
   that port). **Copy the `code` value from the URL**.

4. Exchange the authorization code for tokens using a REST client or
   PowerShell:

   ```powershell
   $body = @{
       grant_type   = "authorization_code"
       code         = "AUTHORIZATION_CODE"
       redirect_uri = "http://localhost:8000/callback"
   }
   $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("YOUR_CLIENT_ID:YOUR_CLIENT_SECRET"))
   $headers = @{ Authorization = "Basic $cred" }
   Invoke-RestMethod -Uri "https://api.pinterest.com/v5/oauth/token" -Method Post -Body $body -Headers $headers
   ```

   Replace `AUTHORIZATION_CODE`, `YOUR_CLIENT_ID`, and `YOUR_CLIENT_SECRET`
   with your values.

5. The response contains:

   ```json
   {
       "access_token": "pina-...",
       "refresh_token": "pinr-...",
       "expires_in": 3600
   }
   ```

6. Copy both tokens. The access token expires in 1 hour — the refresh token
   lets the agent get new ones automatically.

**Expected output**:
```
access_token:  pina-ABCD1234...
refresh_token: pinr-EFGH5678...
```

**Verify**:
- Tokens start with the `pina-` and `pinr-` prefixes (Pinterest standard).

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| `invalid_grant` error | The auth code expired (valid ~1 hour). Restart from step 1. |
| `redirect_uri_mismatch` | Make sure the redirect_uri exactly matches what's in your app settings |
| `invalid_client` | Check your client_id and client_secret are correct |
| 401 on token exchange | Ensure you applied Base64 encoding of `client_id:client_secret` |

---

## Gate 3: API Keys

**Goal**: Set up your `.env` file with Pinterest tokens, and optionally add
OpenAI and Hugging Face keys.

**Time**: 10 minutes.

**Prerequisites**: Gate 2 completed (access + refresh tokens).

**Steps**:

1. Copy the template env file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` (use Notepad or any text editor):

   ```powershell
   notepad .env
   ```

3. Fill in the Pinterest tokens from Gate 2:

   ```env
   PINTEREST_TOKEN=pina-ABCD1234...
   PINTEREST_REFRESH_TOKEN=pinr-EFGH5678...
   PINTEREST_CLIENT_ID=1234567890123456789
   PINTEREST_CLIENT_SECRET=abcdef1234567890abcdef1234567890abcdef12
   ```

4. **(Optional) OpenAI key** — get from [platform.openai.com/api-keys](https://platform.openai.com/api-keys):

   ```env
   OPENAI_API_KEY=sk-proj-...
   ```

5. **(Optional) Hugging Face token** — get from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens):

   ```env
   HF_TOKEN=hf_...
   ```

6. Run the doctor command to verify everything is accessible:

   ```powershell
   pinterest-agent doctor
   ```

**Expected output**:
```
  ✓ Pinterest: API reachable (1 board(s) found)
  ✓ Config:    config.yaml — valid (9 sections)
  ✓ Database:  data/pinterest_agent.db — ...
  ✓ ...
Diagnostics complete: N checks passed, all good.
```

Note: You haven't created a board yet — "0 boards" is fine at this stage.

**Verify**:
- `pinterest-agent doctor` exits with code 0.
- All checks show `✓` (warnings for optional missing keys like OpenAI/HF
  are acceptable).

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| Config file not found | Run from the project root where `config.yaml` lives, or set `PINTEREST_CONFIG` |
| Token not found | Verify the env var names match exactly (case-sensitive on some systems) |
| doctor command not found | Run `pip install -e .` from the project root |

---

## Gate 4: Create First Board

**Goal**: Create an "Old Money Women" board on Pinterest and map it in config.

**Time**: 5 minutes.

**Prerequisites**: Gate 3 completed (tokens working, doctor passes).

**Steps**:

1. Log in to [pinterest.com](https://pinterest.com).
2. Click your profile icon → **Create** → **Board**.
3. Set the board name to exactly:

   ```
   Old Money Women
   ```

4. Choose **Secret** if you want it private during testing, or **Public**.
5. Click **Create**.
6. In `config.yaml`, verify the board mapping matches:

   ```yaml
   boards:
     old_money: "Old Money Women"
   ```

7. Verify connectivity with doctor:

   ```powershell
   pinterest-agent doctor
   ```

**Expected output**:
```
  ✓ Pinterest: API reachable (1 board(s) found)
```

If you have multiple boards, "N board(s) found" is fine.

**Verify**:
- The board shows in your Pinterest profile.
- `pinterest-agent doctor` reports Pinterest as reachable.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| "0 board(s) found" | Check your token has `boards:read` scope; create a public board |
| Board name mismatch | The name in config.yaml must **exactly** match the Pinterest board name |
| Wrong board showing | You can use `pinterest-agent validate-config` to check the config |

---

## Gate 5: First Niche — Old Money Women

**Goal**: Verify the `old_money` template loads and configurations are correct.

**Time**: 5 minutes.

**Prerequisites**: Gate 4 completed (board created).

**Steps**:

1. Run a dry-run prompt generation to verify the template:

   ```powershell
   pinterest-agent generate-prompts --niche old_money --count 1 --dry-run
   ```

   Note: `--dry-run` may not exist in V1. If it doesn't, you can run without
   it and the prompts will be generated and stored:

   ```powershell
   pinterest-agent generate-prompts --niche old_money --count 1
   ```

2. Verify the template is found:

   ```powershell
   pinterest-agent generate-prompts
   ```

   (Without `--niche`, it lists available templates.)

**Expected output** (templates list):
```
Available templates:

  - coquette
  - lingerie_aesthetic
  - old_money
  - pilates
```

Or when generating:

```
Generating 1 prompt(s) for niche 'old_money' (seed=1) ...
Done. Generated 1 prompt(s).
```

**Verify**:
- `old_money` appears in the available templates list.
- Generating a prompt produces no errors.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| "No templates found" | Check templates exist at `src/pinterest_agent/prompts/templates/old_money.yaml` |
| "Template not found" | Run from project root so relative paths resolve correctly |
| Validation error | Run `pinterest-agent validate-config` |

---

## Gate 6: Generate 10 Prompts

**Goal**: Generate your first batch of prompts for the `old_money` niche.

**Time**: 2 minutes.

**Prerequisites**: Gate 5 completed (template verified).

**Steps**:

1. Generate 10 prompts:

   ```powershell
   pinterest-agent generate-prompts --niche old_money --count 10
   ```

2. List the generated prompts:

   ```powershell
   pinterest-agent list-prompts --niche old_money
   ```

3. Check overall status:

   ```powershell
   pinterest-agent status
   ```

**Expected output**:

```
Generating 10 prompt(s) for niche 'old_money' (seed=1) ...
Done. Generated 10 prompt(s).
```

Then from `list-prompts`:

```
  ID  Status     Niche                Template             Seed  Text Preview
------------------------------------------------------------------------------------------------------------------------
   1  generated  old_money             old_money              1  Elegant 25-35 woman with dark brown...
   2  generated  old_money             old_money              2  Elegant 35-50 woman with chestnut...
  ...
  10  generated  old_money             old_money             10  Elegant 40-60 woman with blonde...
```

**Verify**:
- `list-prompts --niche old_money` shows 10 prompts with status `generated`.
- `status` shows `Prompts: 10 total, Generated: 10`.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| 0 prompts generated | Check `--niche old_money` spelling; run `pinterest-agent generate-prompts` first to list templates |
| Duplicate warnings | Normal — same template+seed combinations are deduplicated |
| Database error | Ensure the `data/` directory exists: `New-Item -ItemType Directory -Path data -Force` |

---

## Gate 7: Generate Images

**Goal**: Generate 5 images from the queued prompts using your local GPU or
Hugging Face fallback.

**Time**: 5–20 minutes (depends on GPU speed and provider).

**Prerequisites**: Gate 6 completed (10 prompts generated and in
`generated` status).

**Steps**:

1. Check what providers are available:

   ```powershell
   pinterest-agent doctor
   ```

2. Generate 5 images (uses auto-priority: local → huggingface):

   ```powershell
   pinterest-agent generate-images --count 5
   ```

3. List the generated images:

   ```powershell
   pinterest-agent list-images
   ```

**Expected output**:

```
Generating images for 5 pending prompt(s) ...
Done. 5 generated, 0 skipped, 0 failed.
```

From `list-images`:

```
  ID  Prompt  Status     Niche                Provider         Seed  Size       File
---------------------------------------------------------------------------------------------------------------------------------
   1       1  generated  old_money             local_diffusers     1  1000×1500  old_money/1_old_money_...
   2       2  generated  old_money             local_diffusers     2  1000×1500  old_money/2_old_money_...
  ...
   5       5  generated  old_money             local_diffusers     5  1000×1500  old_money/5_old_money_...
```

**Verify**:
- `list-images` shows 5 images with status `generated`.
- Images exist on disk in `storage/images/processed/old_money/`.
- `pinterest-agent status` shows `Images: 5 total, Generated: 5`.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| "No module named 'torch'" | Install torch: `pip install torch torch-directml` |
| "CUDA not available" | AMD detected. Use DirectML: `pip install torch-directml` |
| "DirectML not available" | See [AMD ROCm docs](https://rocm.docs.amd.com) or use huggingface backend |
| Generation fails silently | Try with explicit provider: `pinterest-agent generate-images --count 5 --provider huggingface` |
| HF Inference rate limit | Wait 1 minute and retry, or reduce batch size |
| All failed — "Provider not available" | Run `pinterest-agent doctor` to check provider status |

---

## Gate 8: Publish First Pin

**Goal**: Publish 1 pin to your "Old Money Women" board on real Pinterest.

**Time**: 5 minutes.

**Prerequisites**: Gate 7 completed (at least 1 image in `generated`
status).

**Steps**:

1. Publish 1 pin:

   ```powershell
   pinterest-agent publish-pins --count 1
   ```

2. List publications:

   ```powershell
   pinterest-agent list-publications
   ```

3. Check overall system status:

   ```powershell
   pinterest-agent status
   ```

4. Verify on Pinterest:
   - Go to your "Old Money Women" board on [pinterest.com](https://pinterest.com).
   - Confirm the pin appears.

**Expected output**:

```
Fetching up to 1 unpublished image(s) ...
Published 1/1 image(s).
  ✓ Image 1 → pin_id=1234567890123456789
```

From `list-publications`:

```
  ID  Image  Status     Board                Pin ID               Published At
----------------------------------------------------------------------------------------------------
   1      1  published  Old Money Women      1234567890123456789  2026-06-23T12:00:00
```

**Verify**:
- `pinterest-agent publish-pins` exits with code 0.
- `list-publications` shows 1 record with status `published`.
- The pin is visible on your Pinterest board.
- `pinterest-agent status` shows `Publications: 1 total, Published: 1`.

**Troubleshooting**:

| Problem | Solution |
|---------|----------|
| "Board not found" | Check board name in config.yaml; must match Pinterest exactly |
| "No images available to publish" | Generate images first (Gate 7) |
| "401 Unauthorized" | Token expired. Run Gate 2 OAuth flow again to get fresh tokens |
| Rate limited (429) | Wait 30 minutes. Check `pins_per_day` in config |
| Pin rejected | Content may violate Pinterest policies. Check images are appropriate |
| "ssl certificate" errors | Windows: ensure your system CA certs are up to date |

---

## Production Schedule

Once Gate 8 is verified, you can enable the scheduler for daily publishing:

```powershell
# Dry-run first to see what would be published
pinterest-agent scheduler-run --dry-run

# Start the scheduler daemon (runs indefinitely)
pinterest-agent scheduler-run --daemon
```

The scheduler publishes according to the windows defined in `config.yaml`.
Default: 3 windows per day (morning 9:00, afternoon 14:00, evening 20:00),
10 pins/day total.

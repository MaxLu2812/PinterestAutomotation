# Troubleshooting Guide

> Always start diagnosis with `pinterest-agent doctor`. It checks:
> - Config validity
> - Database connection
> - Output directories
> - API keys availability
> - Provider availability
> - Pinterest API connectivity

---

## Config Issues

### `config.yaml not found`

```
✗ Config:    config.yaml — file not found
```

**Cause**: The CLI looks for `config.yaml` in the current working directory.
If you're running from a different directory, it won't find it.

**Fix**:
```powershell
# Run from project root
cd E:\projects\PinterestAutomotation

# Or set the config path explicitly
$env:PINTEREST_CONFIG = "E:\projects\PinterestAutomotation\config.yaml"
```

### `Validation error`

```
✗ Config:    config.yaml — validation error
```

**Cause**: The YAML is malformed or a required field is missing/wrong type.

**Fix**:
```powershell
# Get detailed error messages
pinterest-agent validate-config
```

Common issues:
- Indentation errors — YAML is whitespace-sensitive, use spaces not tabs
- Missing required fields like `token_ref` in accounts section
- Wrong data types (e.g., string instead of number for `pins_per_day`)

### Config section not loading

**Cause**: Unrecognized keys or sections.

**Fix**: Comment out custom keys or remove them. Only recognized sections
are loaded.

---

## Token Issues

### `401 Unauthorized` on publish

```
✗ Image 1 failed: 401 Client Error: Unauthorized for url
```

**Cause**: The Pinterest access token has expired (valid for 1 hour).

**Fix**: Generate new tokens via the OAuth 2.0 flow (see ONBOARDING.md Gate 2):

```powershell
# Run the full OAuth code flow again
# Steps:
# 1. Visit the authorization URL in your browser
# 2. Copy the code from the redirect
# 3. Exchange code for tokens via PowerShell
# 4. Update .env with new tokens
```

### `Invalid refresh token`

```
Token refresh failed: invalid_grant
```

**Cause**: The refresh token has been invalidated (happens if you regenerate
the app secret or revoke the app in Pinterest settings).

**Fix**: Generate a completely new set of tokens using the OAuth flow.
You may need to re-authorize the app from scratch.

### Tokens not being read

**Cause**: `.env` file is missing or the variables aren't loaded.

**Fix**:
```powershell
# Verify the .env file exists
Test-Path .env

# Check the env vars are actually set
$env:PINTEREST_TOKEN
```

The CLI loads `.env` automatically. If you're running from a different
directory, the file won't be found. Set them manually:

```powershell
# Load env vars for the current session
Get-Content .env | ForEach-Object {
    if ($_ -match "^\s*([^#]\w+)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}
```

---

## Generation Issues

### `No module named 'torch'`

```
✗ Provider:  local_diffusers — not available (import failed)
```

**Cause**: PyTorch is not installed. Required for local image generation.

**Fix**:
```powershell
# For AMD GPUs (DirectML)
pip install torch torch-directml diffusers transformers safetensors

# Or use the project's optional dependency group
pip install -e ".[local]"
```

### `CUDA not available`

**Cause**: AMD GPU detected. PyTorch's default CUDA backend is NVIDIA-only.

**Fix**: This is expected on AMD hardware. Use DirectML backend:

```powershell
pip install torch-directml
```

If DirectML doesn't work with your GPU model, switch to the Hugging Face
Inference API fallback:

```powershell
# Set your HF token in .env
HF_TOKEN=hf_...

# Generate using HF explicitly
pinterest-agent generate-images --count 5 --provider huggingface
```

### `DirectML not available`

```
✗ Provider:  local_diffusers — not available (import failed)
```

**Cause**: `torch-directml` has limited GPU support. Not all AMD GPUs are
compatible.

**Fix**:

1. Check AMD ROCm compatibility at [rocm.docs.amd.com](https://rocm.docs.amd.com)
2. If your GPU is not supported, use Hugging Face Inference API:

   ```powershell
   pip install huggingface_hub
   ```

3. Set `HF_TOKEN` in `.env` and run with:

   ```powershell
   pinterest-agent generate-images --count 5 --provider huggingface
   ```

### `HF Inference rate limit`

```
429 Too Many Requests
```

**Cause**: Free Hugging Face tier has rate limits.

**Fix**:
- Wait 1–2 minutes and retry
- Reduce batch size: `pinterest-agent generate-images --count 1`
- Consider upgrading to HF Pro for higher limits
- Use local generation if your GPU supports it

### All images failed

**Cause**: Provider configuration error, missing dependencies, or API issue.

**Fix**:
```powershell
# Run diagnostics first
pinterest-agent doctor

# Retry failed images
pinterest-agent retry-images

# Try explicit provider
pinterest-agent generate-images --count 5 --provider huggingface
```

---

## Publishing Issues

### `Board not found`

**Cause**: The board name in `config.yaml` does not match any board on your
Pinterest account.

**Fix**:
1. Verify the board exists on Pinterest (check your profile → Boards).
2. Check the board name in `config.yaml` (must match **exactly**, including
   spaces and capitalization):

   ```yaml
   boards:
     old_money: "Old Money Women"   # <- must match Pinterest exactly
   ```

3. Run doctor to verify Pinterest API connectivity:

   ```powershell
   pinterest-agent doctor
   ```

### `No images available to publish`

**Cause**: No images with status `generated` exist in the database.

**Fix**:
```powershell
# Check current image status
pinterest-agent list-images

# Generate new images
pinterest-agent generate-images --count 5
```

### Rate limited (429)

```
429 Too Many Requests
```

**Cause**: Pinterest API rate limit exceeded. Pinterest allows roughly
10–50 pins/day for standard access, fewer for trial.

**Fix**:
- Wait 30 minutes before retrying.
- Check your `pins_per_day` config value (default: 10).
- Consider reducing the rate if you're hitting limits.
- Verify your app has **Standard Access** (not trial).

### Pin rejected

```
Pin rejected: content may violate Pinterest policies
```

**Cause**: The generated image or its description violates Pinterest
content policies (e.g., adult content, misleading information, poor image
quality).

**Fix**:
- Review the generated image and description.
- Modify the template variables in
  `src/pinterest_agent/prompts/templates/old_money.yaml` to be more
  conservative.
- Ensure images are original and high quality (1000×1500 recommended).
- Check [Pinterest Content Guidelines](https://policy.pinterest.com/community-guidelines).

### SSL / certificate errors (Windows)

```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Cause**: Windows certificate store may be outdated or missing CA bundles.

**Fix**:
```powershell
# Update Python certifi
pip install --upgrade certifi

# Or set the REQUESTS_CA_BUNDLE if you have a corporate proxy
$env:REQUESTS_CA_BUNDLE = "C:\path\to\custom-ca-bundle.crt"
```

---

## Database Issues

### `data/pinterest_agent.db not found`

**Cause**: Database hasn't been created yet (first run).

**Fix**: The database is auto-created on first interaction. Run any command:

```powershell
pinterest-agent generate-prompts --niche old_money --count 1
```

### Database corruption

**Cause**: Unexpected shutdown, disk error, or concurrent access.

**Fix**:
```powershell
# Backup the corrupted database first
Copy-Item data/pinterest_agent.db data/pinterest_agent.db.bak

# Delete and restart
Remove-Item data/pinterest_agent.db
# The database will be recreated on next command
```

---

## Scheduler Issues

### Scheduler won't start

**Cause**: APScheduler not installed or config validation fails.

**Fix**:
```powershell
# Install publish dependencies
pip install -e ".[publish]"

# Verify config
pinterest-agent validate-config
```

### No pins published during scheduled window

**Cause**: No images in `generated` status when scheduler runs.

**Fix**:
```powershell
# Check if there are pending images
pinterest-agent list-images --status generated

# Generate more if needed
pinterest-agent generate-images --count 5
```

### Scheduler dry-run shows 0 pins

**Cause**: Either no images are ready, or rate limiting is preventing
publication.

**Fix**:
```powershell
# Check publication records
pinterest-agent list-publications

# Check overall status
pinterest-agent status
```

---

## Platform-Specific (Windows / AMD GPU)

### `pip install` fails with build errors

**Cause**: Missing C++ build tools for some packages.

**Fix**: Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
or use pre-built wheels:

```powershell
# Use pre-built wheels where possible
pip install --only-binary :all: torch torch-directml
```

### PowerShell encoding issues

**Cause**: PowerShell outputs Unicode, which may render incorrectly in
some terminals.

**Fix**: Set the console to UTF-8:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
```

### Path too long on Windows

**Cause**: Deeply nested generated image paths may exceed Windows MAX_PATH
(260 characters).

**Fix**: Enable long paths in Windows:
1. Open **Group Policy Editor** (gpedit.msc)
2. Navigate to: Computer Configuration → Administrative Templates → System → Filesystem
3. Enable **Enable Win32 long paths**
4. Restart

Or configure `storage` to a shorter path in `config.yaml`.

# Privacy Policy

**Last updated:** June 24, 2026

## 1. Introduction

This Privacy Policy explains how Pinterest Automotation ("the tool," "we," or "us") handles information when you use this personal Pinterest content management tool.

**This tool is designed for personal use by a single individual. It is not a service, platform, or multi-user application.**

By using this tool, you agree to the practices described in this policy.

## 2. What Data We Collect

### 2.1 Pinterest Account Data (via API)

With your explicit authorization via OAuth 2.0, the tool accesses the following data from your personal Pinterest account through Pinterest's official API v5:

- **Public profile information** — username, display name, profile image URL
- **Your boards** — board names, descriptions, privacy settings
- **Your pins** — pin titles, descriptions, image URLs, destination links, board assignments

**The tool does not access:** other users' data, comments, messages, email addresses, or any data outside the authenticated user's own account.

### 2.2 Locally Generated Content

The tool creates and stores the following data exclusively on **your personal computer**:

- **Prompts** — text descriptions used to create images (stored in local SQLite database)
- **Generated images** — images created from prompts (stored in local filesystem)
- **Publication records** — timestamps and metadata of published pins (stored in local SQLite database)

### 2.3 What We Do NOT Collect

We explicitly do NOT collect, transmit, or process:

- Personal identifiers (name, email, phone number)
- Location data
- Browsing history or behavior
- Device information or fingerprints
- IP addresses
- Cookies or tracking data
- Analytics or telemetry
- Any data from non-authenticated Pinterest users

## 3. Token Handling

Authentication tokens are handled with strict security measures:

- **Access tokens** are stored exclusively in a local `.env` file on your machine
- **Tokens are never** transmitted to any server other than Pinterest's official API endpoints
- **Tokens are never** logged, printed, or displayed in the application output
- **Tokens are never** shared with third parties
- **Token refresh** happens only through Pinterest's official OAuth token endpoint
- **Token revocation** can be performed at any time through your Pinterest Developer settings

The `.env` file is protected by `.gitignore` and will never be committed to version control.

## 4. Local Storage Explained

All application data resides on your local computer:

| Data Type | Storage Location | Format |
|-----------|-----------------|--------|
| Prompts | `data/pinterest_agent.db` | SQLite database |
| Generated images | `storage/images/` | WEBP files (1000×1500) |
| Publication history | `data/pinterest_agent.db` | SQLite database |
| Configuration | `config.yaml` | YAML file |
| API tokens | `.env` | Environment variables |

**No data is stored in the cloud.** The application has no cloud backend, no remote database, and no telemetry server.

## 5. Data Flow — How Content Is Created and Published

```
User creates prompts → prompts stored locally
       ↓
User generates images → images stored locally
       ↓
User REVIEWS content manually
       ↓
User approves publication → pin sent to Pinterest API
       ↓
Publication record saved locally
```

**Every step requires explicit user action.** The tool does not generate, approve, or publish content automatically without the user's direct instruction.

## 6. Data Sharing

We do NOT:

- Sell, trade, or rent your personal information
- Share your data with third parties
- Use your data for advertising, analytics, or training
- Transfer data across borders or to external servers
- Process data on behalf of any third party

The **only** external communication is with Pinterest's official API v5 endpoints (`https://api.pinterest.com/v5/`), and only when you explicitly perform actions such as publishing a pin or fetching your boards.

## 7. Third-Party Services

This tool uses the following third-party services, each triggered only by your explicit action:

| Service | Purpose | Data Sent |
|---------|---------|-----------|
| Pinterest API v5 | Publish pins, list boards, manage content | OAuth token, pin data, board references |
| OpenAI API (optional) | Generate prompt text descriptions | Prompt context (no personal data) |
| Hugging Face Inference API (optional) | Generate images | Text prompt (no personal data) |

Each service operates under its own privacy policy. You may choose to disable optional services and use the local scene composer and local image generation instead.

## 8. User Control and Deletion

You have full control over your data:

- **Delete local data**: Delete the `data/` and `storage/` directories to remove all locally stored information
- **Revoke API access**: Revoke the application from your Pinterest Developer settings at any time
- **Remove tokens**: Delete or edit the `.env` file
- **Uninstall**: Delete the project directory — no residual data remains

## 9. Changes to This Policy

We may update this Privacy Policy to reflect improvements or regulatory requirements. Changes will be documented with an updated date at the top of this document.

## 10. Contact

For questions regarding this application or this Privacy Policy:

**Email:**
hgusaa228@gmail.com

**GitHub Issues:**
https://github.com/MaxLu2812/PinterestAutomotation/issues

---

*This is a personal open-source project. We are not affiliated with or endorsed by Pinterest.*

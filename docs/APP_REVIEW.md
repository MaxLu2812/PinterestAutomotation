# Pinterest API Resubmission Kit

## App Description

> Pinterest Automotation is a personal content management tool that helps individual users organize their Pinterest boards, schedule pins, and manage their content calendar efficiently. Designed for hobbyists and personal content creators who want to maintain a consistent and organized Pinterest presence through manual curation and scheduled publishing.

## Recommended Use Cases

1. **Content Organization** — Organize pins and boards by theme, aesthetic, or category for a cohesive Pinterest profile
2. **Pin Scheduling** — Plan content publication across multiple time windows to reach different audiences
3. **Board Management** — Maintain themed boards with curated, manually reviewed content
4. **Content Calendar** — Keep a consistent posting schedule without daily manual intervention

## Recommended Scopes

When setting up your Pinterest app, request the following OAuth 2.0 scopes:

| Scope | Purpose |
|-------|---------|
| `boards:read` | List and view your boards |
| `boards:write` | Create and update boards |
| `pins:read` | View your existing pins |
| `pins:write` | Create new pins |

## Resubmission Checklist

Before resubmitting your Pinterest app for review, confirm each item:

- [ ] **Privacy Policy URL** is live at a public URL (GitHub Pages)
- [ ] **Terms of Service URL** is live at a public URL (GitHub Pages)
- [ ] **App Icon** is uploaded in the Pinterest Developer Console
- [ ] **App Description** clearly states personal use case
- [ ] **Redirect URI** configured as `http://localhost:8000/callback`
- [ ] **Scopes** set to minimum required (`boards:read`, `boards:write`, `pins:read`, `pins:write`)
- [ ] **Privacy Policy** explains local-only data storage and no third-party sharing
- [ ] **Terms of Service** prohibits adult content, spam, and policy violations
- [ ] **App Name** does not imply Pinterest endorsement
- [ ] **Developer Account** verified email address

## Support Email

For Pinterest review purposes, use your GitHub-associated email or create a dedicated contact:

```
Support contact: Open a GitHub issue at https://github.com/MaxLu2812/PinterestAutomotation
```

## App Review Notes

- The tool is strictly for **personal use**
- All content is **manually reviewed** before publication
- No content is generated, scraped, or repurposed without user action
- The tool does **not** use Pinterest user data for any purpose other than serving the authenticated user
- The app communicates **only** with the official Pinterest API v5
- No data is shared with third parties
- No advertising or monetization is involved

## Common Resubmission Pitfalls

| Issue | Solution |
|-------|----------|
| "App not compliant with brand guidelines" | Ensure app name/icon doesn't imply Pinterest endorsement |
| "Privacy Policy URL inaccessible" | Verify GitHub Pages is enabled and URL is public |
| "Scope request too broad" | Remove unused scopes (ads, analytics, etc.) |
| "Use case unclear" | Submit clear, specific use case — "personal content scheduling" |
| "No demo video provided" | Consider recording a 30-second screen recording showing manual pin creation |

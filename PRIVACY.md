# Privacy Policy

**Last updated:** June 23, 2026

## Overview

This application ("Pinterest Aesthetic Automation") is a personal automation tool that generates and publishes AI-assisted aesthetic content to Pinterest. This privacy policy explains what data the application handles and how it is processed.

## Data Collected

### Pinterest Account Data
- **Access tokens**: OAuth 2.0 tokens required to authenticate with the Pinterest API. These are stored locally in environment variables and never transmitted outside your machine.
- **Board and pin metadata**: Board names, pin titles, descriptions, and image metadata required for publishing content to your Pinterest account.

### AI Generation Data
- **Prompts**: Text prompts sent to OpenAI (GPT-4o-mini) or Hugging Face Inference API for image generation. Prompts are generated from local YAML templates.
- **Generated images**: Images created by AI models are stored locally on your machine. If you publish them to Pinterest, they are subject to Pinterest's privacy policy.

## Data Storage

All data is stored **locally** on your machine:

| Data | Storage Location |
|------|------------------|
| SQLite database | `data/pinterest_agent.db` (local) |
| Generated images | `storage/images/` (local) |
| Configuration | `config.yaml` (local) |
| API tokens | Environment variables (local) |

## Data Sharing

This application **does not**:
- Collect analytics or telemetry
- Share your data with third parties
- Use your data for training AI models
- Store data on external servers (except what you explicitly publish to Pinterest)

Data sent to external APIs:
- **OpenAI API**: Prompt text for GPT-4o-mini refinement (if configured)
- **Hugging Face API**: Prompt text for image generation (if configured)
- **Pinterest API**: Generated images, titles, and descriptions (when you publish)

Each API provider has its own privacy policy governing data handling.

## User Control

You have full control over all data:
- All configuration and tokens are in local files you can edit or delete
- The SQLite database can be deleted at any time
- Generated images are yours to keep, modify, or delete
- You choose what and when to publish to Pinterest

## Security

- API tokens are stored in environment variables, not in code
- The application does not expose any network services
- No user data is transmitted without explicit action (generation or publishing commands)

## Changes to This Policy

Updates will be reflected in this file. Continued use after changes constitutes acceptance.

## Contact

For questions about this privacy policy, open an issue on the GitHub repository.

## Compliance

This application is provided as-is for personal use. It is your responsibility to ensure compliance with Pinterest's Terms of Service and applicable laws when publishing content.

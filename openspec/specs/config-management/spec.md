# Config Management Specification

## Purpose

Load, validate, and serve per-account YAML configuration with environment-variable secrets, multi-niche support, and live reload capability.

## Requirements

### Requirement: YAML Configuration Loading

The system MUST load account configuration from YAML files.

#### Scenario: Config loaded successfully
- GIVEN a valid YAML file `accounts/alice.yaml`
- WHEN the config loader reads it
- THEN all keys are parsed into a typed configuration object

#### Scenario: Malformed YAML
- GIVEN a YAML file with invalid syntax
- WHEN the loader attempts to parse it
- THEN it raises a parse error with the file path and line number

### Requirement: Per-Account Configuration

The system MUST support per-account settings: access token, enabled niches, pins per day, and enabled image backends.

#### Scenario: Account config parsed
- GIVEN an account file with `token_ref`, `niches: [cozy-living-room, modern-kitchen]`, `pins_per_day: 10`, `backends: [huggingface, replicate]`
- WHEN the config is loaded
- THEN all four fields are accessible on the account object

#### Scenario: Missing required field
- GIVEN an account file missing `pins_per_day`
- WHEN validation runs
- THEN the system reports a validation error citing the missing field

### Requirement: Per-Niche Configuration

The system MUST support per-niche settings: template directory, board ID, and generation parameters.

#### Scenario: Niche config resolved
- GIVEN an account with niche `cozy-living-room` configured with `template_dir: templates/cozy-living-room`, `board_id: "1234567890"`, `generation: {steps: 30, guidance_scale: 7.5}`
- WHEN the config is loaded
- THEN all niche-specific settings are available

#### Scenario: Niche missing board ID
- GIVEN a niche config without a `board_id`
- WHEN validation runs
- THEN the system warns about the missing board ID and skips that niche for publishing

### Requirement: Environment Variable Secrets

The system MUST load API keys and secrets from environment variables, never from YAML files.

#### Scenario: Token loaded from env
- GIVEN `PINTEREST_ALICE_TOKEN` set in the environment
- WHEN the config loader initializes for account `alice`
- THEN the access token is read from the environment variable

#### Scenario: Missing environment variable
- GIVEN `OPENAI_API_KEY` is not set
- WHEN the system starts
- THEN it logs a fatal error listing the missing variables

### Requirement: Startup Validation

The system SHOULD validate the full configuration tree on startup and report all errors at once.

#### Scenario: Validation reports all errors
- GIVEN a config with 3 validation errors (missing token, invalid board ID, unknown backend)
- WHEN startup validation runs
- THEN all 3 errors are reported together, not one at a time

#### Scenario: Valid config passes
- GIVEN a fully valid configuration
- WHEN startup validation runs
- THEN no errors are reported and the system starts normally

### Requirement: Live Config Reload

The system SHOULD support reloading configuration without restarting the process.

#### Scenario: Config reloaded on SIGHUP or API call
- GIVEN a running system with an active scheduler
- WHEN config reload is triggered
- THEN new account settings take effect for the next scheduled batch without interrupting current operations

#### Scenario: Invalid reload rejected
- GIVEN a running system
- WHEN a reload is triggered with an invalid config file
- THEN the system retains the previous valid configuration and logs the reload error

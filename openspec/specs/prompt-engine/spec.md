# Prompt Engine Specification

## Purpose

Generate Pinterest-optimized image prompts from YAML templates via GPT-4o-mini, queue them in SQLite with full metadata, and hand them off to the image generation phase.

## Requirements

### Requirement: Prompt Generation from Templates

The system MUST generate prompts by rendering YAML template files with variable substitutions via GPT-4o-mini.

#### Scenario: Template renders to prompt
- GIVEN a YAML template `cozy-living-room.yaml` with variables `{style}`, `{color}`, `{angle}`
- WHEN the prompt engine requests GPT-4o-mini to fill the template with `rustic`, `warm-beige`, `wide-angle`
- THEN the result is a complete prompt string stored in the SQLite queue

#### Scenario: Missing variable in template
- GIVEN a template referencing a variable `{undefined_var}` not supplied in the variable set
- WHEN the engine attempts generation
- THEN it MUST reject with a validation error and NOT call the API

### Requirement: SQLite Queue with Status Tracking

The system MUST store generated prompts in a SQLite queue with status: `pending`, `generated`, or `failed`.

#### Scenario: Prompt stored after generation
- GIVEN a successful GPT-4o-mini response
- WHEN the prompt is inserted into the queue
- THEN its status is `generated` and it includes `niche`, `template_id`, `variable_seed`, and `timestamp`

#### Scenario: Prompt marked failed on error
- GIVEN an API error during generation
- WHEN the error is unrecoverable after retries
- THEN the prompt entry status is `failed` with the error reason recorded

### Requirement: Per-Niche Template Files

The system MUST load templates from YAML files organized by niche directory.

#### Scenario: Load templates for a niche
- GIVEN a directory `templates/cozy-living-room/` containing 3 YAML template files
- WHEN the prompt engine initializes for the `cozy-living-room` niche
- THEN all 3 templates are loaded and available for generation

### Requirement: Prompt Metadata

The system MUST attach metadata `niche`, `template_id`, `variable_seed`, and `timestamp` to every queued prompt.

#### Scenario: Metadata recorded on insert
- GIVEN a generated prompt for niche `cozy-living-room`, template `warm-scene`, seed `42`
- WHEN the prompt is written to the queue
- THEN the row contains matching `niche`, `template_id`, `variable_seed`, and `timestamp` columns

### Requirement: Prompt Reuse Detection

The system SHOULD skip generation when the same template ID and variable seed already exist in the queue with `generated` status.

#### Scenario: Duplicate template+seed skipped
- GIVEN an existing queue entry with `template_id=warm-scene`, `variable_seed=42`, status `generated`
- WHEN the engine is asked to generate the same combination again
- THEN it returns the existing prompt ID without calling GPT-4o-mini

### Requirement: Graceful API Failure Handling

The system MUST retry transient GPT-4o-mini failures with exponential backoff and give up after a configurable limit.

#### Scenario: Transient API error recovers
- GIVEN GPT-4o-mini returns a 429 rate-limit error
- WHEN the engine retries after a backoff delay
- THEN the request succeeds on retry and the prompt is stored as `generated`

#### Scenario: Persistent API failure
- GIVEN GPT-4o-mini returns 5 consecutive 5xx errors
- WHEN the engine exhausts all retries
- THEN the prompt is marked `failed` and the error is logged

### Requirement: Ready for Image Generation

The system MUST expose a query for prompts with status `generated` that the image generation phase can consume.

#### Scenario: Queue consumed by image gen
- GIVEN 50 prompts with status `generated` in the queue
- WHEN the image generation batch queries for ready prompts
- THEN all 50 are returned in FIFO order with full metadata

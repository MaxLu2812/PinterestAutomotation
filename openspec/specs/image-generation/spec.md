# Image Generation Specification

## Purpose

Generate Pinterest-optimized images (1000×1500) from queued prompts using pluggable backends with perceptual-hash deduplication, safety checks, and automatic provider failover.

## Requirements

### Requirement: Pluggable Backend Interface

The system MUST define a common abstract interface that all image generation backends implement.

#### Scenario: All backends conform to interface
- GIVEN backends Local Diffusers, Hugging Face Inference API, Replicate, and Together AI
- WHEN each backend is instantiated
- THEN it implements `generate(prompt: str, settings: dict) -> ImageResult`

#### Scenario: Backend registration
- GIVEN a new backend implementation
- WHEN it registers via the provider registry
- THEN it is available for selection by name in configuration

### Requirement: Image Resizing to Pinterest Standard

The system MUST resize ALL generated images to 1000×1500 pixels regardless of backend.

#### Scenario: Non-standard input resized
- GIVEN a generated image at 512×512
- WHEN the pipeline processes it
- THEN the output is a 1000×1500 image with content-aware cropping or letterboxing

#### Scenario: Correct aspect ratio resized
- GIVEN a generated image at 768×1024
- WHEN the pipeline processes it
- THEN the output is exactly 1000×1500 pixels

### Requirement: Batch Processing

The system MUST support batch generation of 500—1000 images in a single CLI run.

#### Scenario: Batch processes queue
- GIVEN 600 prompts with status `generated` in the queue
- WHEN the batch command is invoked
- THEN all 600 images are generated, resized, and stored

### Requirement: Perceptual Hash Deduplication

The system MUST compute a pHash for every generated image and reject duplicates against stored hashes.

#### Scenario: Duplicate image detected
- GIVEN an image whose pHash matches an existing stored image
- WHEN the pipeline computes the hash
- THEN the duplicate is discarded and the prompt is marked `failed` with reason `duplicate`

#### Scenario: Unique image stored
- GIVEN an image with no matching pHash in the store
- WHEN the pipeline computes the hash
- THEN the image is saved with its pHash in the metadata record

### Requirement: Image Metadata Storage

The system MUST store each image with `niche`, `prompt_id`, `backend_used`, `pHash`, and `timestamp`.

#### Scenario: Full metadata recorded
- GIVEN a generated image from backend `huggingface`, prompt ID `42`, niche `cozy-living-room`
- WHEN the image is persisted
- THEN the metadata record contains all five fields

### Requirement: Prompt Queue Status Update

The system MUST update the source prompt's status to `generated` or `failed` after each image is processed.

#### Scenario: Success updates queue
- GIVEN a prompt that produced a unique image
- WHEN the image is stored
- THEN the prompt status changes to `generated`

#### Scenario: Failure updates queue
- GIVEN a prompt that caused a backend error
- WHEN the error is logged
- THEN the prompt status changes to `failed`

### Requirement: Provider Failover Chain

The system SHOULD fail over through a configured provider chain when the primary backend fails.

#### Scenario: Primary fails, secondary succeeds
- GIVEN a configured chain: `local-diffusers` → `huggingface` → `replicate`
- WHEN `local-diffusers` returns an unrecoverable error
- THEN the system attempts `huggingface`, and if successful, the image is tagged `backend_used=huggingface`

#### Scenario: All providers exhausted
- GIVEN all three providers in the chain fail
- WHEN the last provider errors
- THEN the prompt is marked `failed` with the aggregate error

### Requirement: NSFW Content Prevention

The system MUST NOT generate or store NSFW content, enforced via safety checker on local models.

#### Scenario: Local safety checker blocks content
- GIVEN a local Diffusion model with safety checker enabled
- WHEN an unsafe image is detected in the output
- THEN the image is discarded and the prompt is marked `failed` with reason `nsfw-blocked`

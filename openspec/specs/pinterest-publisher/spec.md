# Pinterest Publisher Specification

## Purpose

Authenticate with Pinterest OAuth 2.0, create pins via API v5, manage board selection per niche, and enforce rate limits across multiple accounts.

## Requirements

### Requirement: OAuth 2.0 Authentication

The system MUST authenticate with Pinterest using OAuth 2.0 with automatic token refresh.

#### Scenario: Successful authentication
- GIVEN valid Pinterest app credentials and an authorization code
- WHEN the publisher exchanges the code for an access token
- THEN it receives a valid access token and refresh token

#### Scenario: Token refresh
- GIVEN an expired access token (expires after 30 days)
- WHEN the publisher attempts an API call
- THEN it refreshes the token using the refresh token and retries the request

### Requirement: Pin Creation via API v5

The system MUST create pins using Pinterest API v5 endpoint `POST /v5/pins` with either `image_url` or `image_base64`.

#### Scenario: Pin created from image URL
- GIVEN an accessible image URL and a board ID
- WHEN the publisher calls `POST /v5/pins` with `image_url`
- THEN the API returns a pin ID and a public pin URL

#### Scenario: Pin created from base64
- GIVEN a local image encoded as base64
- WHEN the publisher calls `POST /v5/pins` with `image_base64`
- THEN the pin is created successfully and the pin ID is stored

### Requirement: Board Selection per Niche

The system MUST select the target Pinterest board based on the image's niche mapping.

#### Scenario: Board resolved from niche config
- GIVEN an image tagged with niche `cozy-living-room`
- WHEN the publisher resolves the target board
- THEN it uses the board ID configured under `niches.cozy-living-room.board_id`

#### Scenario: Missing board mapping
- GIVEN an image with niche `unknown-niche`
- WHEN the publisher attempts to resolve the board
- THEN it raises a configuration error and skips the pin

### Requirement: Rate Limit Enforcement

The system MUST enforce a maximum of 10 pins per day per Pinterest account, with at least 30 minutes between pins.

#### Scenario: Daily limit reached
- GIVEN an account that has published 10 pins today
- WHEN the scheduler requests another pin
- THEN the publisher rejects the request with reason `daily-limit-reached`

#### Scenario: Minimum interval enforced
- GIVEN a pin published 15 minutes ago
- WHEN the scheduler requests another pin
- THEN the publisher rejects with reason `min-interval-not-met`

### Requirement: Pinterest API Error Handling

The system MUST handle Pinterest API errors: rate limits, auth failures, and content rejections.

#### Scenario: API rate limit
- GIVEN a 429 response from Pinterest
- WHEN the publisher receives it
- THEN it backs off and retries after the `Retry-After` header duration

#### Scenario: Content rejection
- GIVEN a 400 response citing content policy violation
- WHEN the publisher receives it
- THEN the pin is skipped and the prompt is marked `failed` with reason `content-rejected`

### Requirement: Publish Logging

The system MUST log the pin ID and public URL for every successful publish.

#### Scenario: Success logged
- GIVEN a successful `POST /v5/pins` response with `{"id": "12345", "link": "https://pin.it/abc"}`
- WHEN the publisher completes
- THEN it logs `[PUBLISHED] pin_id=12345 url=https://pin.it/abc`

### Requirement: Multi-Account Support

The system SHOULD support publishing to multiple Pinterest accounts, each with independent rate limit tracking.

#### Scenario: Pin to account B after account A limits
- GIVEN account A at 10/10 daily pins and account B at 2/10
- WHEN the scheduler picks the next item
- THEN it routes the pin to account B

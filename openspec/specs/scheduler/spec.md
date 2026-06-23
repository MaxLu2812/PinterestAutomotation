# Scheduler Specification

## Purpose

Schedule daily Pinterest publishing via APScheduler, respecting per-account rate limits, spreading pins across time windows, and selecting images by priority.

## Requirements

### Requirement: APScheduler Integration

The system MUST use APScheduler to manage daily publishing schedules.

#### Scenario: Scheduler starts daily jobs
- GIVEN the scheduler is initialized with an account configuration
- WHEN the scheduler starts
- THEN APScheduler registers daily jobs that respect the configured `pins_per_day`

#### Scenario: Missed window recovers
- GIVEN the system was offline during a scheduled time window
- WHEN it restarts
- THEN APScheduler's misfire grace period triggers the missed job if within threshold

### Requirement: Per-Account Pin Limit

The scheduler MUST respect each account's configured daily pin maximum.

#### Scenario: Account limit enforced
- GIVEN an account with `pins_per_day: 5`
- WHEN the scheduler plans the day's jobs
- THEN exactly 5 publish jobs are scheduled across the configured windows

### Requirement: Time Window Spreading

The system MUST spread scheduled pins across 2—3 daily time windows (morning, afternoon, evening).

#### Scenario: Pins spread across windows
- GIVEN an account with `pins_per_day: 6` and 3 windows configured
- WHEN the scheduler plans the day
- THEN 2 pins are scheduled in each window

#### Scenario: Uneven distribution
- GIVEN an account with `pins_per_day: 5` and 3 windows
- WHEN the scheduler plans the day
- THEN the distribution is 2—2—1, spreading the remainder evenly across earlier windows

### Requirement: Image Selection by Priority

The scheduler MUST pick the next image from the image store based on oldest unused first.

#### Scenario: Oldest unused selected
- GIVEN images with timestamps T1(day 1), T2(day 3), T3(day 5), all unused
- WHEN the scheduler requests an image
- THEN image T1 is selected

#### Scenario: All images used
- GIVEN all stored images have been published
- WHEN the scheduler requests an image
- THEN it logs a warning and skips the window

### Requirement: Minimum Publish Interval

The scheduler MUST enforce at least 30 minutes between consecutive pins on the same account.

#### Scenario: Interval enforced between windows
- GIVEN an evening window at 18:00 and a morning window at 09:00 the next day
- WHEN the scheduler calculates the interval
- THEN it is valid (exceeds 30 minutes)

#### Scenario: Interval adjusted within window
- GIVEN 2 pins scheduled in the same window at 09:00
- WHEN the planner runs
- THEN the second pin is scheduled at 09:30 or later

### Requirement: Pause and Resume

The scheduler SHOULD support pausing and resuming all publishing without losing queued items.

#### Scenario: Pause stops publishing
- GIVEN an actively publishing scheduler
- WHEN pause is requested
- THEN all pending jobs are paused and no new pins are created

#### Scenario: Resume continues
- GIVEN a paused scheduler
- WHEN resume is requested
- THEN pending jobs continue from where they stopped

### Requirement: Action Logging

The system MUST log every scheduled action: pin creation, skipped windows, errors.

#### Scenario: All actions logged
- GIVEN a scheduler run that publishes 3 pins and skips 1 window
- WHEN the run completes
- THEN the log contains 4 entries with timestamps and outcomes

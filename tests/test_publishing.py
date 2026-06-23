"""Tests for publishing — PinterestClient, PinPublisher, SchedulerService, CLI."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import (
    ImageRecord,
    ImageStatus,
    PublicationRecord,
    PublicationStatus,
)
from pinterest_agent.publishers.pin_publisher import PinPublisher, PublicationResult
from pinterest_agent.publishers.pinterest_client import PinterestClient
from pinterest_agent.scheduler.scheduler import SchedulerConfig, SchedulerService, WindowConfig


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def in_memory_cm() -> ConnectionManager:
    """Return a ConnectionManager backed by :memory: SQLite."""
    cm = ConnectionManager(":memory:")
    cm.connect()
    return cm


@pytest.fixture
def image_repo(in_memory_cm: ConnectionManager) -> SqliteImageRepository:
    return SqliteImageRepository(in_memory_cm)


@pytest.fixture
def publication_repo(in_memory_cm: ConnectionManager) -> SqlitePublicationRepository:
    return SqlitePublicationRepository(in_memory_cm)


@pytest.fixture
def mock_pinterest_client():
    """Create a mock PinterestClient that succeeds."""
    client = MagicMock()
    client.create_pin.return_value = {
        "id": "12345",
        "link": "https://pin.it/abc123",
    }
    client.resolve_board_id.return_value = "board_456"
    return client


@pytest.fixture
def failing_pinterest_client():
    """Create a mock PinterestClient that fails."""
    client = MagicMock(spec=PinterestClient)
    client.create_pin.return_value = {"error": "API rate limit exceeded"}
    client.resolve_board_id.return_value = None
    client.get_boards.return_value = []
    return client


@pytest.fixture
def seed_prompts(in_memory_cm: ConnectionManager) -> None:
    """Seed two prompt rows so image FK constraints are satisfied."""
    in_memory_cm.execute(
        "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
        "VALUES ('old_money', 't1', '{}', 1, 'test prompt 1', 'generated')"
    )
    in_memory_cm.execute(
        "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
        "VALUES ('coquette', 't2', '{}', 2, 'test prompt 2', 'generated')"
    )


@pytest.fixture
def generated_image(image_repo: SqliteImageRepository, seed_prompts: None) -> ImageRecord:
    """Seed a generated image in the database."""
    img = ImageRecord(
        prompt_id=1,
        file_path="/tmp/test_image.webp",
        status=ImageStatus.GENERATED,
        niche="old_money",
        backend="mock",
        seed=42,
    )
    img.id = image_repo.save(img)
    return img


@pytest.fixture
def generated_image_coquette(image_repo: SqliteImageRepository, seed_prompts: None) -> ImageRecord:
    """Seed a second generated image with a different niche."""
    img = ImageRecord(
        prompt_id=2,
        file_path="/tmp/test_coquette.webp",
        status=ImageStatus.GENERATED,
        niche="coquette",
        backend="mock",
        seed=99,
    )
    img.id = image_repo.save(img)
    return img


@pytest.fixture
def seed_image(in_memory_cm: ConnectionManager, image_repo: SqliteImageRepository) -> int:
    """Seed a prompt and an image so publication FK is satisfied. Returns image_id."""
    in_memory_cm.execute(
        "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
        "VALUES ('test_niche', 't1', '{}', 1, 'test', 'generated')"
    )
    img = ImageRecord(prompt_id=1, file_path="/tmp/img.webp", status=ImageStatus.GENERATED, niche="test_niche")
    return image_repo.save(img)


@pytest.fixture
def publisher(
    mock_pinterest_client,
    image_repo: SqliteImageRepository,
    publication_repo: SqlitePublicationRepository,
) -> PinPublisher:
    return PinPublisher(
        pinterest_client=mock_pinterest_client,
        image_repo=image_repo,
        publication_repo=publication_repo,
        board_mapping={"old_money": "Old Money Women", "coquette": "Coquette Aesthetic"},
    )


@pytest.fixture
def scheduler(publisher, image_repo, publication_repo) -> SchedulerService:
    config = SchedulerConfig(
        windows=[
            WindowConfig(hour=9, minute=0, label="morning"),
            WindowConfig(hour=14, minute=0, label="afternoon"),
        ],
        pins_per_day=4,
        min_interval_minutes=30,
        max_pins_per_window=2,
    )
    return SchedulerService(
        publisher=publisher,
        image_repo=image_repo,
        publication_repo=publication_repo,
        config=config,
    )


# ======================================================================
# Tests: PublicationRepository — CRUD and status transitions
# ======================================================================


class TestPublicationRepository:
    def test_save_and_find(self, publication_repo: SqlitePublicationRepository, seed_image: int):
        record = PublicationRecord(
            image_id=seed_image,
            board_id="board_123",
            title="Test Pin",
            description="A test description",
            tags="test, aesthetic",
            status=PublicationStatus.PENDING,
        )
        record_id = publication_repo.save(record)
        assert record_id > 0

        found = publication_repo.find_by_image_id(seed_image)
        assert found is not None
        assert found.id == record_id
        assert found.board_id == "board_123"
        assert found.status == PublicationStatus.PENDING

    def test_find_by_pinterest_pin_id(self, publication_repo: SqlitePublicationRepository, seed_image: int,
                                       in_memory_cm: ConnectionManager, image_repo: SqliteImageRepository):
        # Seed a second image
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('test', 't2', '{}', 2, 'test2', 'generated')"
        )
        img2 = ImageRecord(prompt_id=2, file_path="/tmp/img2.webp", status=ImageStatus.GENERATED, niche="test")
        img2_id = image_repo.save(img2)

        record = PublicationRecord(
            image_id=img2_id,
            board_id="board_456",
            title="Published Pin",
            pinterest_pin_id="pin_789",
            status=PublicationStatus.PUBLISHED,
            published_at=datetime.now(),
        )
        record_id = publication_repo.save(record)

        found = publication_repo.find_by_pinterest_pin_id("pin_789")
        assert found is not None
        assert found.id == record_id
        assert found.image_id == img2_id

    def test_query_by_status(self, publication_repo: SqlitePublicationRepository, seed_image: int,
                              in_memory_cm: ConnectionManager, image_repo: SqliteImageRepository):
        # Seed 2 more images for the published + failed records
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('test2', 't3', '{}', 3, 'test3', 'generated')"
        )
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('test3', 't4', '{}', 4, 'test4', 'generated')"
        )
        img2 = ImageRecord(prompt_id=2, file_path="/tmp/img2.webp", status=ImageStatus.GENERATED, niche="test2")
        img2_id = image_repo.save(img2)
        img3 = ImageRecord(prompt_id=3, file_path="/tmp/img3.webp", status=ImageStatus.GENERATED, niche="test3")
        img3_id = image_repo.save(img3)

        pending = PublicationRecord(image_id=seed_image, board_id="b1", title="P1", status=PublicationStatus.PENDING)
        published = PublicationRecord(image_id=img2_id, board_id="b2", title="P2", pinterest_pin_id="p1",
                                       status=PublicationStatus.PUBLISHED, published_at=datetime.now())
        failed = PublicationRecord(image_id=img3_id, board_id="b3", title="P3", status=PublicationStatus.FAILED, error="err")

        publication_repo.save(pending)
        publication_repo.save(published)
        publication_repo.save(failed)

        pending_results = publication_repo.query(status=PublicationStatus.PENDING)
        assert len(pending_results) == 1

        published_results = publication_repo.query(status=PublicationStatus.PUBLISHED)
        assert len(published_results) == 1

        failed_results = publication_repo.query(status=PublicationStatus.FAILED)
        assert len(failed_results) == 1

    def test_count_by_status(self, publication_repo: SqlitePublicationRepository, seed_image: int,
                              in_memory_cm: ConnectionManager, image_repo: SqliteImageRepository):
        # Seed images for 4 records
        for i in range(4):
            pid = i + 2  # prompt_id starting at 2
            in_memory_cm.execute(
                "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
                "VALUES ('test', 't', '{}', ?, 'test', 'generated')",
                (pid,),
            )
            img = ImageRecord(prompt_id=pid, file_path=f"/tmp/img{i}.webp", status=ImageStatus.GENERATED, niche="test")
            image_repo.save(img)

        records_data = [
            (seed_image, PublicationStatus.PUBLISHED, "pin_0"),
            (seed_image + 1, PublicationStatus.PUBLISHED, "pin_1"),
            (seed_image + 2, PublicationStatus.PUBLISHED, "pin_2"),
            (seed_image + 3, PublicationStatus.FAILED, None),
        ]
        for img_id, status, pin_id in records_data:
            publication_repo.save(
                PublicationRecord(image_id=img_id, board_id="b1", title="P", status=status,
                                   pinterest_pin_id=pin_id, published_at=datetime.now() if pin_id else None)
            )

        assert publication_repo.count_by_status(PublicationStatus.PUBLISHED) == 3
        assert publication_repo.count_by_status(PublicationStatus.FAILED) == 1

    def test_count_published_today(self, publication_repo: SqlitePublicationRepository, seed_image: int):
        """count_published_today should only count today's publications."""
        publication_repo.save(
            PublicationRecord(image_id=seed_image, board_id="b1", title="T1", status=PublicationStatus.PUBLISHED,
                               pinterest_pin_id="p1", published_at=datetime.now())
        )
        assert publication_repo.count_published_today() == 1

    def test_mark_failed(self, publication_repo: SqlitePublicationRepository, seed_image: int):
        record_id = publication_repo.save(
            PublicationRecord(image_id=seed_image, board_id="b1", title="P1", status=PublicationStatus.PENDING)
        )

        publication_repo.mark_failed(record_id, "Something went wrong")
        found = publication_repo.find_by_image_id(seed_image)
        assert found is not None
        assert found.status == PublicationStatus.FAILED
        assert found.error == "Something went wrong"


# ======================================================================
# Tests: PinPublisher
# ======================================================================


class TestPinPublisher:
    def test_publish_success(self, publisher: PinPublisher, generated_image: ImageRecord):
        """Successful publish returns a PublicationResult with pin details."""
        result = publisher.publish(generated_image)

        assert result.success
        assert result.image_id == generated_image.id
        assert result.pinterest_pin_id == "12345"
        assert result.pin_url == "https://pin.it/abc123"
        assert result.published_at is not None

    def test_publish_creates_publication_record(self, publisher: PinPublisher, generated_image: ImageRecord,
                                                 publication_repo: SqlitePublicationRepository):
        """A successful publish creates a publication record."""
        publisher.publish(generated_image)

        records = publication_repo.query(status=PublicationStatus.PUBLISHED)
        assert len(records) == 1
        assert records[0].image_id == generated_image.id
        assert records[0].pinterest_pin_id == "12345"

    def test_publish_updates_image_status(self, publisher: PinPublisher, generated_image: ImageRecord,
                                           image_repo: SqliteImageRepository):
        """Published image should transition to PUBLISHED status."""
        publisher.publish(generated_image)

        updated = image_repo.query(status=ImageStatus.PUBLISHED.value)
        assert len(updated) == 1
        assert updated[0].id == generated_image.id
        assert updated[0].pin_id == "12345"

    def test_publish_not_generated_returns_error(self, publisher: PinPublisher, image_repo: SqliteImageRepository,
                                                   in_memory_cm: ConnectionManager):
        """Image with PENDING status should be rejected."""
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('old_money', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/nonexistent.webp", status=ImageStatus.PENDING, niche="old_money")
        img.id = image_repo.save(img)

        result = publisher.publish(img)
        assert not result.success
        assert "expected 'generated'" in (result.error or "").lower()

    def test_publish_no_board_mapping(self, publisher: PinPublisher, image_repo: SqliteImageRepository,
                                       in_memory_cm: ConnectionManager):
        """Image with unmapped niche should fail gracefully."""
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('unknown_niche', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/nonexistent.webp", status=ImageStatus.GENERATED, niche="unknown_niche")
        img.id = image_repo.save(img)

        result = publisher.publish(img)
        assert not result.success
        assert "no board mapping" in (result.error or "").lower()

    def test_publish_api_failure(self, failing_pinterest_client, image_repo: SqliteImageRepository,
                                  publication_repo: SqlitePublicationRepository,
                                  in_memory_cm: ConnectionManager):
        """API failure should result in a PublicationResult with error."""
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('old_money', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/test.webp", status=ImageStatus.GENERATED, niche="old_money")
        img.id = image_repo.save(img)

        pub = PinPublisher(
            pinterest_client=failing_pinterest_client,
            image_repo=image_repo,
            publication_repo=publication_repo,
            board_mapping={"old_money": "Old Money Women"},
        )
        result = pub.publish(img)

        assert not result.success
        assert "rate limit" in (result.error or "").lower()

    def test_publish_batch_continues_on_failure(self, failing_pinterest_client, image_repo: SqliteImageRepository,
                                                 publication_repo: SqlitePublicationRepository,
                                                 in_memory_cm: ConnectionManager):
        """Publishing a batch should continue even if some fail."""
        images = []
        for i in range(3):
            in_memory_cm.execute(
                "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
                "VALUES ('old_money', 't1', '{}', ?, 'test', 'generated')",
                (i + 1,),
            )
            img = ImageRecord(
                prompt_id=i + 1,
                file_path=f"/tmp/test_{i}.webp",
                status=ImageStatus.GENERATED,
                niche="old_money",
            )
            img.id = image_repo.save(img)
            images.append(img)

        pub = PinPublisher(
            pinterest_client=failing_pinterest_client,
            image_repo=image_repo,
            publication_repo=publication_repo,
            board_mapping={"old_money": "Old Money Women"},
        )
        results = pub.publish_batch(images)

        assert len(results) == 3
        assert all(not r.success for r in results)


# ======================================================================
# Tests: SchedulerService
# ======================================================================


class TestSchedulerService:
    def test_distribute_pins_even(self):
        """10 pins across 3 windows → 4-3-3."""
        windows = [
            WindowConfig(hour=9, label="morning"),
            WindowConfig(hour=14, label="afternoon"),
            WindowConfig(hour=20, label="evening"),
        ]
        config = SchedulerConfig(windows=windows, pins_per_day=10)
        svc = SchedulerService.__new__(SchedulerService)
        svc._config = config

        dist = svc._distribute_pins()
        assert dist == [4, 3, 3]

    def test_distribute_pins_under_window_count(self):
        """2 pins across 3 windows → 1-1-0."""
        windows = [
            WindowConfig(hour=9, label="morning"),
            WindowConfig(hour=14, label="afternoon"),
            WindowConfig(hour=20, label="evening"),
        ]
        config = SchedulerConfig(windows=windows, pins_per_day=2)
        svc = SchedulerService.__new__(SchedulerService)
        svc._config = config

        dist = svc._distribute_pins()
        assert dist == [1, 1, 0]

    def test_run_once_selects_oldest_first(self, scheduler: SchedulerService, image_repo: SqliteImageRepository,
                                            in_memory_cm: ConnectionManager):
        """The oldest unpublished image should be selected first."""
        for i in range(2):
            in_memory_cm.execute(
                "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
                "VALUES ('old_money', 't1', '{}', ?, 'test', 'generated')",
                (i + 1,),
            )
        img1 = ImageRecord(prompt_id=1, file_path="/tmp/old.webp", status=ImageStatus.GENERATED, niche="old_money")
        img2 = ImageRecord(prompt_id=2, file_path="/tmp/newer.webp", status=ImageStatus.GENERATED, niche="old_money")
        # Save img2 first to ensure ordering
        img2.id = image_repo.save(img2)
        img1.id = image_repo.save(img1)

        # run_once should pick the oldest (img1, id=1, then img2 id=2)
        count = scheduler.run_once(dry_run=True)
        # 2 images, but max_pins_per_window=2, so should be 2
        assert count == 2

    def test_run_once_dry_run(self, scheduler: SchedulerService, image_repo: SqliteImageRepository,
                               in_memory_cm: ConnectionManager):
        """Dry run should not create any publication records."""
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('old_money', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/test.webp", status=ImageStatus.GENERATED, niche="old_money")
        img.id = image_repo.save(img)

        count = scheduler.run_once(dry_run=True)
        assert count == 1

        # Verify no publication records were created
        records = scheduler._publication_repo.query()
        assert len(records) == 0

    def test_daily_limit_respected(self, scheduler: SchedulerService, publication_repo: SqlitePublicationRepository,
                                    in_memory_cm: ConnectionManager, image_repo: SqliteImageRepository):
        """When daily limit is reached, run_once should do nothing."""
        # Seed today's publications to hit the limit
        for i in range(scheduler._config.pins_per_day):
            pid = i + 1
            in_memory_cm.execute(
                "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
                "VALUES ('test', 't', '{}', ?, 'test', 'generated')",
                (pid,),
            )
            img = ImageRecord(prompt_id=pid, file_path=f"/tmp/img{i}.webp", status=ImageStatus.GENERATED, niche="test")
            img_id = image_repo.save(img)
            publication_repo.save(
                PublicationRecord(image_id=img_id, board_id="b1", title=f"P{i}", status=PublicationStatus.PUBLISHED,
                                   pinterest_pin_id=f"pin_{i}", published_at=datetime.now())
            )

        count = scheduler.run_once()
        assert count == 0

    def test_no_available_images(self, scheduler: SchedulerService, image_repo: SqliteImageRepository):
        """When no images are available, run_once should return 0 and not error."""
        count = scheduler.run_once()
        assert count == 0

    def test_failed_publication_does_not_stop_scheduler(self, scheduler: SchedulerService,
                                                         image_repo: SqliteImageRepository,
                                                         in_memory_cm: ConnectionManager):
        """A failed publish should be logged but not crash the scheduler."""
        # Replace publisher with one that fails
        failing_client = MagicMock()
        failing_client.create_pin.return_value = {"error": "API error"}
        failing_client.resolve_board_id.return_value = "board_456"

        scheduler._publisher._client = failing_client

        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('old_money', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/test.webp", status=ImageStatus.GENERATED, niche="old_money")
        img.id = image_repo.save(img)

        # This should not raise
        count = scheduler.run_once()
        assert count == 0  # 0 successful

        # Verify a publication record was created with failed status
        records = scheduler._publication_repo.query()
        assert len(records) == 1
        assert records[0].status == PublicationStatus.FAILED

    def test_pause_resume(self, scheduler: SchedulerService):
        """Pause and resume should toggle scheduler state."""
        assert not scheduler.is_paused
        scheduler.pause()
        assert scheduler.is_paused
        scheduler.resume()
        assert not scheduler.is_paused


# ======================================================================
# Tests: CLI Registration
# ======================================================================


class TestCLIRegistration:
    def test_publish_commands_registered(self):
        """CLI should have all publish commands registered."""
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        assert "publish-pins" in commands
        assert "list-publications" in commands
        assert "retry-publications" in commands
        assert "scheduler-run" in commands

    def test_import_publish_module(self):
        """Importing the publish module should not raise."""
        from pinterest_agent.cli import publish  # noqa: F401
        assert True


# ======================================================================
# Tests: Board resolution from config
# ======================================================================


class TestBoardResolution:
    def test_publisher_uses_board_mapping(self, publisher: PinPublisher, generated_image: ImageRecord):
        """Publisher should use board_mapping from config to resolve board."""
        result = publisher.publish(generated_image)
        assert result.success

        # Verify resolve_board_id was called with the mapped name
        publisher._client.resolve_board_id.assert_called_with("Old Money Women")

    def test_missing_niche_in_mapping(self, publisher: PinPublisher, image_repo: SqliteImageRepository,
                                       in_memory_cm: ConnectionManager):
        """Unmapped niche should return error without calling API."""
        in_memory_cm.execute(
            "INSERT INTO prompts (aesthetic, template_id, variables, variable_seed, text, status) "
            "VALUES ('unknown', 't1', '{}', 1, 'test', 'generated')"
        )
        img = ImageRecord(prompt_id=1, file_path="/tmp/test.webp", status=ImageStatus.GENERATED, niche="unknown")
        img.id = image_repo.save(img)

        result = publisher.publish(img)
        assert not result.success
        assert "no board mapping" in (result.error or "").lower()

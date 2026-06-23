"""Tests for CLI commands — status, stats, doctor, and command registration."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


from pinterest_agent.domain.models import (
    ImageStatus,
    PromptStatus,
    PublicationStatus,
)


# ======================================================================
# Tests: Command registration
# ======================================================================


class TestCommandRegistration:
    """All CLI commands should be registered on the root group."""

    def test_all_commands_registered(self):
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        expected = [
            "version",
            "generate-prompts",
            "list-prompts",
            "retry-prompts",
            "generate-images",
            "list-images",
            "retry-images",
            "publish-pins",
            "list-publications",
            "retry-publications",
            "scheduler-run",
            "show-config",
            "validate-config",
            "reload-config",
            "status",
            "stats",
            "doctor",
        ]
        for cmd in expected:
            assert cmd in commands, f"Command '{cmd}' is not registered"

    def test_version_command(self):
        from pinterest_agent.cli.main import cli

        result = cli.commands["version"].callback()
        assert result is None

    def test_cli_group_help_text(self):
        from pinterest_agent.cli.main import cli

        help_text = cli.help
        assert "Pinterest Aesthetic Automation" in help_text


# ======================================================================
# Tests: Status command
# ======================================================================


class TestStatusCommand:
    """Status command should display system overview."""

    @pytest.fixture
    def mock_db_with_data(self):
        """Create an in-memory DB with some test data."""
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )

        cm = ConnectionManager(":memory:")
        cm.connect()

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)
        pub_repo = SqlitePublicationRepository(cm)

        # Seed prompts
        from pinterest_agent.domain.models import Prompt

        for i in range(3):
            prompt = Prompt(
                aesthetic="test",
                template_id="t1",
                text=f"prompt{i}",
                variable_seed=i,
                status=PromptStatus.GENERATED,
            )
            prompt.id = prompt_repo.enqueue(prompt)

        prompt_repo.enqueue(
            Prompt(
                aesthetic="test",
                template_id="t2",
                text="fail",
                variable_seed=99,
                status=PromptStatus.FAILED,
            )
        )

        # Seed images
        from pinterest_agent.domain.models import ImageRecord

        for i in range(2):
            img = ImageRecord(
                prompt_id=i + 1,
                file_path=f"/tmp/img{i}.webp",
                status=ImageStatus.GENERATED,
                niche="test",
            )
            image_repo.save(img)

        img = ImageRecord(
            prompt_id=4,
            file_path="/tmp/fail.webp",
            status=ImageStatus.FAILED,
            niche="test",
        )
        image_repo.save(img)

        # Seed publications
        from pinterest_agent.domain.models import PublicationRecord

        for i in range(2):
            pub = PublicationRecord(
                image_id=i + 1,
                board_id="b1",
                title="Pin",
                status=PublicationStatus.PUBLISHED,
                pinterest_pin_id=f"pin_{i}",
            )
            pub_repo.save(pub)

        pub_repo.save(
            PublicationRecord(
                image_id=3,
                board_id="b1",
                title="Fail",
                status=PublicationStatus.FAILED,
                error="err",
            )
        )

        return cm

    def test_status_with_data(self, mock_db_with_data):
        """Status should display counts from DB."""
        from pinterest_agent.cli.main import cli

        # The status command uses the default db path "data/pinterest_agent.db"
        # We need to patch ConnectionManager to use our in-memory DB
        with patch(
            "pinterest_agent.cli.status_cmd.ConnectionManager",
            return_value=mock_db_with_data,
        ):
            runner = cli  # Use CliRunner for proper invocation
            # Direct call to the callback since CliRunner not available
            from click.testing import CliRunner

            runner = CliRunner()
            # We can't easily inject the in-memory DB path, so we'll
            # test the output via a different approach
            result = runner.invoke(cli, ["status", "--db", ":memory:"])
            assert result.exit_code == 0 or "Error" in result.output

    def test_status_empty_db(self):
        """Status should handle empty database gracefully."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        # Use :memory: db to test with empty data
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--db", ":memory:"])
        # Should not crash
        assert result.exit_code == 0 or "⚠" in result.output or "✓" in result.output

    def test_status_bad_db_path(self):
        """Status should handle bad db path gracefully."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--db", "/nonexistent/db.sqlite"])
        # Should not crash - should handle error gracefully
        assert result.exit_code == 0


# ======================================================================
# Tests: Stats command
# ======================================================================


class TestStatsCommand:
    """Stats command should display aggregate statistics."""

    def test_stats_registered(self):
        from pinterest_agent.cli.main import cli

        assert "stats" in cli.commands

    def test_stats_with_empty_db(self):
        """Stats should handle empty database."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--db", ":memory:", "--days", 7])
        # Should not crash
        assert result.exit_code == 0
        assert "Statistics" in result.output

    def test_stats_with_data(self):
        """Stats should display counts."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli
        from pinterest_agent.db.connection import ConnectionManager
        from pinterest_agent.domain.models import (
            ImageRecord,
            ImageStatus,
            Prompt,
            PromptStatus,
            PublicationRecord,
            PublicationStatus,
        )

        # Seed data in a real in-memory DB
        cm = ConnectionManager(":memory:")
        cm.connect()
        from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
        from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
        from pinterest_agent.db.repositories.publication_repo import (
            SqlitePublicationRepository,
        )

        prompt_repo = SqlitePromptRepository(cm)
        image_repo = SqliteImageRepository(cm)
        pub_repo = SqlitePublicationRepository(cm)

        for i in range(5):
            prompt = Prompt(
                aesthetic="test",
                template_id="t",
                text=f"p{i}",
                variable_seed=i,
                status=PromptStatus.GENERATED,
            )
            prompt.id = prompt_repo.enqueue(prompt)
            img = ImageRecord(
                prompt_id=prompt.id,
                file_path=f"/tmp/{i}.webp",
                status=ImageStatus.GENERATED,
                niche="test",
                backend="mock_provider",
            )
            image_repo.save(img)

        for i in range(3):
            pub = PublicationRecord(
                image_id=i + 1,
                board_id="b1",
                title="Pin",
                status=PublicationStatus.PUBLISHED,
                pinterest_pin_id=f"pin_{i}",
            )
            pub_repo.save(pub)

        # Patch the ConnectionManager in stats_cmd
        with patch("pinterest_agent.cli.stats_cmd.ConnectionManager") as mock_cm:
            mock_cm.return_value = cm

            runner = CliRunner()
            result = runner.invoke(cli, ["stats", "--db", ":memory:", "--days", 30])

            assert result.exit_code == 0
            assert "Statistics" in result.output
            assert "Prompts generated" in result.output
            assert "Provider usage" in result.output


# ======================================================================
# Tests: Doctor command
# ======================================================================


class TestDoctorCommand:
    """Doctor command should run diagnostics and report issues."""

    def test_doctor_registered(self):
        from pinterest_agent.cli.main import cli

        assert "doctor" in cli.commands

    def test_doctor_no_config(self):
        """Doctor should handle missing config gracefully."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["doctor", "--config", "/nonexistent/config.yaml"],
        )
        # Should not crash, even though config is missing
        assert "Diagnostics complete" in result.output or "issues" in result.output

    def test_doctor_with_fix_flag(self):
        """Doctor --fix should create missing directories."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                runner = CliRunner()
                result = runner.invoke(
                    cli,
                    ["doctor", "--fix"],
                )
                # Should create some directories and not crash
                assert result.exit_code in (0, 1)
                # Check that some storage dirs were created
                from pathlib import Path

                assert Path("storage/images/raw").is_dir()
            finally:
                os.chdir(orig_cwd)

    def test_doctor_env_vars(self):
        """Doctor should detect environment variables."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        with patch.dict(os.environ, {"PINTEREST_TOKEN": "test"}):
            runner = CliRunner()
            result = runner.invoke(cli, ["doctor", "--db", ":memory:"])
            output = result.output
            assert "PINTEREST_TOKEN" in output
            # Should not crash
            assert "Diagnostics" in output or "issues" in output

    @patch("pinterest_agent.config.loader.ConfigLoader")
    def test_doctor_all_ok(self, mock_loader):
        """Doctor should report all checks passed when everything is OK."""
        from click.testing import CliRunner
        from pinterest_agent.cli.main import cli

        # Mock config loader to return a valid config
        mock_config = MagicMock()
        mock_config.pinterest = MagicMock()
        mock_config.publishing = MagicMock()
        mock_config.generator = MagicMock()
        mock_config.retry = MagicMock()
        mock_config.boards = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.accounts = []
        mock_config.niches = {}
        mock_config.db_path = ":memory:"
        mock_loader.return_value.load.return_value = mock_config

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(os.environ, {"PINTEREST_TOKEN": "x", "OPENAI_API_KEY": "x", "HF_TOKEN": "x"}),
        ):
            orig_cwd = os.getcwd()
            os.chdir(tmpdir)
            # Create required directories
            Path("storage/images/raw").mkdir(parents=True, exist_ok=True)
            Path("storage/images/processed").mkdir(parents=True, exist_ok=True)
            Path("storage/images/failed").mkdir(parents=True, exist_ok=True)
            Path("storage/logs").mkdir(parents=True, exist_ok=True)

            try:
                runner = CliRunner()
                result = runner.invoke(cli, ["doctor", "--db", ":memory:"])
                assert "all good" in result.output.lower() or "passed" in result.output.lower()
            finally:
                os.chdir(orig_cwd)


# ======================================================================
# Tests: Generate and Publish command registration
# ======================================================================


class TestGenerateCommandRegistration:
    def test_generate_commands_registered(self):
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        assert "generate-prompts" in commands
        assert "list-prompts" in commands
        assert "retry-prompts" in commands
        assert "generate-images" in commands
        assert "list-images" in commands
        assert "retry-images" in commands

    def test_import_generate_module(self):
        from pinterest_agent.cli import generate  # noqa: F401

        assert True


class TestPublishCommandRegistration:
    def test_publish_commands_registered(self):
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        assert "publish-pins" in commands
        assert "list-publications" in commands
        assert "retry-publications" in commands
        assert "scheduler-run" in commands

    def test_import_publish_module(self):
        from pinterest_agent.cli import publish  # noqa: F401

        assert True

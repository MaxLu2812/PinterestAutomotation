"""Tests for configuration loading and validation.

Covers:
- Config loading from YAML dict
- Default values for all sections
- Env-var resolution
- Validation errors
- CLI commands
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from pinterest_agent.config.loader import (
    AccountSettings,
    AppConfig,
    BoardMappingConfig,
    ConfigLoader,
    GeneratorConfig,
    LoggingConfig,
    NicheSettings,
    PinterestAuthConfig,
    PublishingConfig,
    RetryConfig,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def sample_config_yaml() -> dict:
    """Return a full sample configuration as a Python dict."""
    return {
        "pinterest": {
            "client_id": "test_id",
            "client_secret": "test_secret",
            "redirect_uri": "http://localhost:8000/callback",
        },
        "publishing": {
            "pins_per_day": 5,
            "publish_windows": [
                {"hour": 10, "minute": 0, "label": "late_morning"},
            ],
            "minimum_interval_minutes": 60,
            "timezone": "America/New_York",
        },
        "generator": {
            "primary_provider": "local_diffusers",
            "fallback_provider": "huggingface",
            "output_directory": "custom/output",
            "target_width": 512,
            "target_height": 768,
            "image_quality": 85,
        },
        "retry": {
            "max_generation_retries": 5,
            "max_publish_retries": 2,
            "exponential_backoff": False,
            "base_delay_seconds": 2.0,
        },
        "boards": {
            "old_money": "Old Money Luxury",
            "coquette": "Coquette Dreams",
        },
        "logging": {
            "level": "DEBUG",
            "file": "/tmp/test.log",
            "max_bytes": 1048576,
            "backup_count": 3,
            "rotation": True,
            "format_string": "%(message)s",
        },
        "accounts": [
            {
                "name": "main",
                "token_ref": "TEST_TOKEN",
                "refresh_token_ref": "TEST_REFRESH",
                "pins_per_day": 10,
                "niches": ["old_money"],
                "enabled_backends": ["local_diffusers"],
                "board_mapping": {"old_money": "Old Money Luxury"},
            },
        ],
        "niches": {
            "old_money": {
                "name": "Old Money Women",
                "board_name": "Old Money Luxury",
                "template_dir": "custom/templates",
            },
        },
        "db_path": "custom/db.sqlite",
    }


@pytest.fixture
def config_file_path(sample_config_yaml: dict) -> Path:
    """Write a temporary YAML config file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(sample_config_yaml, f)
        tmp_path = Path(f.name)
    yield tmp_path
    tmp_path.unlink(missing_ok=True)


# ======================================================================
# Tests: Default values
# ======================================================================


class TestDefaultValues:
    """All config sections should have sensible defaults."""

    def test_pinterest_auth_defaults(self):
        config = PinterestAuthConfig()
        assert config.client_id == ""
        assert config.client_secret == ""
        assert config.redirect_uri == "http://localhost:8000/callback"

    def test_publishing_defaults(self):
        config = PublishingConfig()
        assert config.pins_per_day == 10
        assert len(config.publish_windows) == 3
        assert config.publish_windows[0]["label"] == "morning"
        assert config.minimum_interval_minutes == 30
        assert config.timezone == "UTC"

    def test_generator_defaults(self):
        config = GeneratorConfig()
        assert config.primary_provider == "local_diffusers"
        assert config.target_width == 1000
        assert config.target_height == 1500
        assert config.image_quality == 90

    def test_retry_defaults(self):
        config = RetryConfig()
        assert config.max_generation_retries == 3
        assert config.max_publish_retries == 3
        assert config.exponential_backoff is True
        assert config.base_delay_seconds == 1.0

    def test_board_mapping_defaults(self):
        config = BoardMappingConfig()
        assert config.old_money == "Old Money Women"
        assert config.coquette == "Coquette Aesthetic"

    def test_logging_defaults(self):
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.file is None
        assert config.max_bytes == 10 * 1024 * 1024
        assert config.backup_count == 5
        assert config.rotation is True
        assert "%(asctime)s" in config.format_string

    def test_account_settings_defaults(self):
        config = AccountSettings(name="test")
        assert config.name == "test"
        assert config.token_ref == ""
        assert config.pins_per_day is None
        assert config.niches == []
        assert config.tokens == {}

    def test_niche_settings_defaults(self):
        config = NicheSettings(name="test")
        assert config.name == "test"
        assert config.board_name == ""
        assert config.template_dir == ""
        assert config.gen_settings == {}

    def test_app_config_defaults(self):
        config = AppConfig()
        assert config.db_path == "data/pinterest_agent.db"
        assert config.accounts == []
        assert config.niches == {}
        # Sub-configs should have defaults
        assert config.generator.target_width == 1000
        assert config.publishing.pins_per_day == 10
        assert config.retry.max_generation_retries == 3
        assert config.logging.level == "INFO"
        assert config.boards.old_money == "Old Money Women"
        assert config.pinterest.client_id == ""


# ======================================================================
# Tests: Config loading from dict
# ======================================================================


class TestConfigLoading:
    """Validate config loading from YAML dicts."""

    def test_load_full_config(self, sample_config_yaml: dict):
        """A full config should parse without errors."""
        config = AppConfig.model_validate(sample_config_yaml)
        assert config.pinterest.client_id == "test_id"
        assert config.publishing.pins_per_day == 5
        assert len(config.publishing.publish_windows) == 1
        assert config.generator.target_width == 512
        assert config.retry.max_generation_retries == 5
        assert config.retry.exponential_backoff is False
        assert config.logging.level == "DEBUG"
        assert config.logging.file == "/tmp/test.log"
        assert len(config.accounts) == 1
        assert config.accounts[0].name == "main"
        assert config.accounts[0].pins_per_day == 10
        assert "old_money" in config.niches
        assert config.niches["old_money"].board_name == "Old Money Luxury"
        assert config.db_path == "custom/db.sqlite"

    def test_load_minimal_config(self):
        """A minimal config with only required fields should work."""
        config = AppConfig.model_validate({
            "accounts": [{"name": "test"}],
            "niches": {"test": {"name": "Test Niche"}},
        })
        assert config.accounts[0].name == "test"
        assert config.niches["test"].name == "Test Niche"
        # Defaults should fill the rest
        assert config.db_path == "data/pinterest_agent.db"
        assert config.publishing.pins_per_day == 10

    def test_empty_config_works(self):
        """An empty config dict should use all defaults."""
        config = AppConfig.model_validate({})
        assert config.accounts == []
        assert config.niches == {}
        assert config.db_path == "data/pinterest_agent.db"

    def test_niche_reference_validation(self):
        """Accounts referencing undefined niches should fail."""
        with pytest.raises(ValueError, match="references niche.*not defined"):
            AppConfig.model_validate({
                "accounts": [
                    {
                        "name": "test",
                        "token_ref": "TOKEN",
                        "niches": ["nonexistent"],
                    }
                ],
            })


# ======================================================================
# Tests: Env-var resolution
# ======================================================================


class TestEnvResolution:
    """Environment variable token resolution."""

    def test_token_resolution(self, sample_config_yaml: dict):
        """Token references should be resolved from environment."""
        with (
            patch.dict(os.environ, {"TEST_TOKEN": "env_access_token"}),
            patch.dict(os.environ, {"TEST_REFRESH": "env_refresh_token"}),
        ):
            config = AppConfig.model_validate(sample_config_yaml)
            account = config.accounts[0]
            # Tokens should be populated by _resolve_tokens
            # (This tests model validation directly; _resolve_tokens happens
            #  as a separate step in ConfigLoader.load())
            assert account.token_ref == "TEST_TOKEN"
            assert account.refresh_token_ref == "TEST_REFRESH"

    def test_missing_token_validation(self, config_file_path: Path):
        """ConfigLoader should report missing env vars."""
        loader = ConfigLoader(str(config_file_path))
        # Ensure the env vars are NOT set
        for key in ["TEST_TOKEN", "TEST_REFRESH"]:
            os.environ.pop(key, None)

        with pytest.raises(ValueError, match="environment variable.*not set"):
            loader.load(str(config_file_path))

    def test_loader_resolves_tokens(self, config_file_path: Path, sample_config_yaml: dict):
        """ConfigLoader.load() should resolve env vars and populate tokens."""
        with (
            patch.dict(os.environ, {"TEST_TOKEN": "resolved_access"}),
            patch.dict(os.environ, {"TEST_REFRESH": "resolved_refresh"}),
        ):
            loader = ConfigLoader(str(config_file_path))
            config = loader.load(str(config_file_path))

            account = config.accounts[0]
            assert account.tokens.get("access_token") == "resolved_access"
            assert account.tokens.get("refresh_token") == "resolved_refresh"


# ======================================================================
# Tests: Validation errors
# ======================================================================


class TestValidationErrors:
    """Config validation should report errors clearly."""

    def test_invalid_logging_level(self):
        """Logging level must match the allowed pattern."""
        with pytest.raises(Exception):
            LoggingConfig(level="INVALID")

    def test_negative_pins_per_day(self):
        """Pins per day must be >= 1."""
        with pytest.raises(Exception):
            PublishingConfig(pins_per_day=0)

    def test_pins_per_day_too_high(self):
        """Pins per day must be <= 100."""
        config = PublishingConfig(pins_per_day=100)  # OK
        assert config.pins_per_day == 100
        with pytest.raises(Exception):
            PublishingConfig(pins_per_day=101)

    def test_image_quality_range(self):
        """Image quality must be 1-100."""
        GeneratorConfig(image_quality=1)  # OK
        GeneratorConfig(image_quality=100)  # OK
        with pytest.raises(Exception):
            GeneratorConfig(image_quality=0)
        with pytest.raises(Exception):
            GeneratorConfig(image_quality=101)

    def test_minimum_interval(self):
        """Minimum interval must be >= 1."""
        PublishingConfig(minimum_interval_minutes=1)  # OK
        with pytest.raises(Exception):
            PublishingConfig(minimum_interval_minutes=0)

    def test_token_ref_empty(self):
        """Token ref must not be empty (if provided)."""
        with pytest.raises(Exception):
            AccountSettings(name="test", token_ref="  ")

    def test_yaml_error(self, config_file_path: Path):
        """Malformed YAML should raise YAMLError."""
        # Write invalid YAML
        config_file_path.write_text("{invalid: yaml: [}", encoding="utf-8")
        loader = ConfigLoader(str(config_file_path))
        import yaml as yaml_module
        with pytest.raises(yaml_module.YAMLError):
            loader.load(str(config_file_path))


# ======================================================================
# Tests: ConfigLoader
# ======================================================================


class TestConfigLoader:
    """ConfigLoader integration tests."""

    def test_load_file(self, config_file_path: Path):
        """ConfigLoader should load and validate a real file."""
        loader = ConfigLoader(str(config_file_path))
        with patch.dict(os.environ, {"TEST_TOKEN": "tok", "TEST_REFRESH": "ref"}):
            config = loader.load(str(config_file_path))
        assert isinstance(config, AppConfig)
        assert config.publishing.pins_per_day == 5

    def test_load_file_not_found(self):
        """Missing config file should raise FileNotFoundError."""
        loader = ConfigLoader("nonexistent_file.yaml")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_config_property_before_load(self):
        """Accessing .config before .load() should raise RuntimeError."""
        loader = ConfigLoader("config.yaml")
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = loader.config

    def test_config_property_after_load(self, config_file_path: Path):
        """Accessing .config after .load() should return the config."""
        loader = ConfigLoader(str(config_file_path))
        with patch.dict(os.environ, {"TEST_TOKEN": "tok", "TEST_REFRESH": "ref"}):
            loader.load(str(config_file_path))
        config = loader.config
        assert isinstance(config, AppConfig)

    def test_validate_config_dict(self, sample_config_yaml: dict):
        """Static validate_config_dict should parse a raw dict."""
        config = ConfigLoader.validate_config_dict(sample_config_yaml)
        assert isinstance(config, AppConfig)
        assert config.publishing.pins_per_day == 5

    def test_validate_config_dict_with_errors(self):
        """validate_config_dict should raise on invalid input."""
        with pytest.raises(ValueError, match="validation failed"):
            ConfigLoader.validate_config_dict({
                "publishing": {"pins_per_day": 0},
            })


# ======================================================================
# Tests: CLI commands
# ======================================================================


class TestCLICommands:
    """Config CLI commands should be registered and functional."""

    def test_config_commands_registered(self):
        """CLI should have all config commands."""
        from pinterest_agent.cli.main import cli

        commands = cli.commands
        assert "show-config" in commands
        assert "validate-config" in commands
        assert "reload-config" in commands

    def test_import_config_module(self):
        """Importing the config_cmd module should not raise."""
        from pinterest_agent.cli import config_cmd  # noqa: F401
        assert True


# ======================================================================
# Tests: PublishingConfig from scheduler
# ======================================================================


class TestSchedulerConfigIntegration:
    """PublishingConfig should integrate correctly with the scheduler."""

    def test_publishing_config_to_windows(self):
        """PublishingConfig publish_windows should map to WindowConfig."""
        pub_config = PublishingConfig(
            pins_per_day=6,
            publish_windows=[
                {"hour": 9, "minute": 0, "label": "morning"},
                {"hour": 14, "minute": 30, "label": "afternoon"},
            ],
            minimum_interval_minutes=45,
            timezone="America/Chicago",
        )

        from pinterest_agent.scheduler.scheduler import SchedulerConfig, WindowConfig

        windows = [
            WindowConfig(hour=w["hour"], minute=w.get("minute", 0), label=w.get("label", ""))
            for w in pub_config.publish_windows
        ]
        scheduler_config = SchedulerConfig(
            windows=windows,
            pins_per_day=pub_config.pins_per_day,
            min_interval_minutes=pub_config.minimum_interval_minutes,
            max_pins_per_window=3,
        )

        assert len(scheduler_config.windows) == 2
        assert scheduler_config.windows[0].hour == 9
        assert scheduler_config.windows[0].label == "morning"
        assert scheduler_config.windows[1].minute == 30
        assert scheduler_config.pins_per_day == 6
        assert scheduler_config.min_interval_minutes == 45

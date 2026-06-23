"""YAML + environment-variable configuration loader with full Pydantic models.

All sections have sensible defaults so an empty config.yaml still produces
a working system. Environment variables are resolved for token references.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ======================================================================
# Config sub-models
# ======================================================================


class PinterestAuthConfig(BaseModel):
    """Pinterest OAuth 2.0 application credentials."""

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/callback"


class PublishingConfig(BaseModel):
    """Daily publishing schedule."""

    pins_per_day: int = Field(default=10, ge=1, le=100)
    publish_windows: list[dict] = Field(default_factory=lambda: [
        {"hour": 9, "minute": 0, "label": "morning"},
        {"hour": 14, "minute": 0, "label": "afternoon"},
        {"hour": 20, "minute": 0, "label": "evening"},
    ])
    minimum_interval_minutes: int = Field(default=30, ge=1)
    timezone: str = "UTC"


class GeneratorConfig(BaseModel):
    """Image generation configuration."""

    primary_provider: str = "local_diffusers"
    fallback_provider: str = "huggingface"
    output_directory: str = "storage/images/processed"
    target_width: int = Field(default=1000, ge=100)
    target_height: int = Field(default=1500, ge=100)
    image_quality: int = Field(default=90, ge=1, le=100)


class RetryConfig(BaseModel):
    """Retry/backoff configuration."""

    max_generation_retries: int = Field(default=3, ge=0)
    max_publish_retries: int = Field(default=3, ge=0)
    exponential_backoff: bool = True
    base_delay_seconds: float = Field(default=1.0, ge=0.1)


class BoardMappingConfig(BaseModel):
    """Niche → board name mapping."""

    old_money: str = "Old Money Women"
    coquette: str = "Coquette Aesthetic"
    pilates: str = "Pilates Girl"
    lingerie_aesthetic: str = "Lingerie Aesthetic"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    file: str | None = None  # path to log file (None = stdout only)
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=0)  # 10 MB
    backup_count: int = Field(default=5, ge=0)
    rotation: bool = True
    format_string: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class AccountSettings(BaseModel):
    """Per-account configuration model."""

    name: str
    token_ref: str = ""
    refresh_token_ref: str = ""
    pins_per_day: int | None = None  # override global
    niches: list[str] = Field(default_factory=list)
    enabled_backends: list[str] = Field(default_factory=list)
    board_mapping: dict[str, str] = Field(default_factory=dict)
    # tokens dict is populated at runtime by _resolve_tokens()
    tokens: dict[str, str] = Field(default_factory=dict)

    @field_validator("token_ref")
    @classmethod
    def token_ref_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("token_ref must not be empty")
        return v


class NicheSettings(BaseModel):
    """Per-niche configuration model."""

    name: str
    board_name: str = ""
    template_dir: str = ""
    gen_settings: dict = Field(default_factory=dict)


class AppConfig(BaseModel):
    """Root application configuration.

    All fields have defaults so an empty config still works.
    """

    pinterest: PinterestAuthConfig = Field(default_factory=PinterestAuthConfig)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    boards: BoardMappingConfig = Field(default_factory=BoardMappingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    accounts: list[AccountSettings] = Field(default_factory=list)
    niches: dict[str, NicheSettings] = Field(default_factory=dict)
    db_path: str = "data/pinterest_agent.db"

    @model_validator(mode="after")
    def validate_niche_references(self) -> AppConfig:
        """Ensure every account's niche references exist in the global niches dict."""
        for account in self.accounts:
            for niche_name in account.niches:
                if niche_name not in self.niches:
                    raise ValueError(
                        f"Account '{account.name}' references niche "
                        f"'{niche_name}' which is not defined in niches section"
                    )
        return self


# ======================================================================
# ConfigLoader
# ======================================================================


class ConfigLoader:
    """Loads and validates configuration from YAML files and environment variables.

    Flow:
        1. Load YAML config from the provided path (default: ``./config.yaml``).
        2. Resolve tokens from environment variables using ``token_ref`` fields.
        3. Validate the full config tree and report all errors at once.

    Usage::

        loader = ConfigLoader()
        config = loader.load("config.yaml")
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = config_path or os.getenv(
            "PINTEREST_CONFIG", "config.yaml"
        )
        self._raw: dict[str, Any] = {}
        self._config: Optional[AppConfig] = None

    def load(self, path: Optional[str] = None) -> AppConfig:
        """Load, validate, and return the application configuration.

        Args:
            path: Optional override for the config file path.

        Returns:
            A validated ``AppConfig`` instance.

        Raises:
            FileNotFoundError: If the config file does not exist.
            yaml.YAMLError: If the YAML is malformed (includes line info).
            ValueError: If validation fails (lists all errors together).
        """
        config_path = Path(path or self._config_path)

        # --- Load YAML ---
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path.resolve()}"
            )

        with config_path.open("r", encoding="utf-8") as fh:
            try:
                self._raw = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                line_info = ""
                if hasattr(exc, "problem_mark"):
                    line_info = f" at line {exc.problem_mark.line + 1}"
                raise yaml.YAMLError(
                    f"Malformed YAML in {config_path}{line_info}: {exc}"
                ) from exc

        # --- Resolve tokens from environment ---
        self._resolve_tokens()

        # --- Validate with Pydantic ---
        errors: list[str] = []
        try:
            self._config = AppConfig.model_validate(self._raw)
        except Exception as exc:
            # Collect all Pydantic validation errors
            if hasattr(exc, "errors"):
                for err in exc.errors():
                    loc = " -> ".join(str(p) for p in err.get("loc", []))
                    msg = err.get("msg", "unknown error")
                    errors.append(f"  - {loc}: {msg}")
            else:
                errors.append(f"  - {exc}")

        # --- Validate environment tokens resolved ---
        for account in self._raw.get("accounts", []):
            token_ref = account.get("token_ref", "")
            if token_ref and token_ref not in os.environ:
                errors.append(
                    f"  - accounts.{account.get('name', '?')}: "
                    f"environment variable '{token_ref}' is not set"
                )

        if errors:
            raise ValueError(
                f"Configuration validation failed with {len(errors)} error(s):\n"
                + "\n".join(errors)
            )

        return self._config  # type: ignore[return-value]

    @property
    def config(self) -> AppConfig:
        """Return the loaded config, or raise if not yet loaded."""
        if self._config is None:
            raise RuntimeError("Config not loaded. Call .load() first.")
        return self._config

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_tokens(self) -> None:
        """Replace ``token_ref`` placeholders with actual env-var values."""
        for account in self._raw.get("accounts", []):
            token_ref = account.get("token_ref", "")
            if token_ref and token_ref in os.environ:
                if "tokens" not in account:
                    account["tokens"] = {}
                account["tokens"]["access_token"] = os.environ[token_ref]

            refresh_ref = account.get("refresh_token_ref", "")
            if refresh_ref and refresh_ref in os.environ:
                if "tokens" not in account:
                    account["tokens"] = {}
                account["tokens"]["refresh_token"] = os.environ[refresh_ref]

    # ------------------------------------------------------------------
    # Utility: validate a config dict without loading from file
    # ------------------------------------------------------------------

    @staticmethod
    def validate_config_dict(data: dict[str, Any]) -> AppConfig:
        """Validate a raw config dict and return the parsed AppConfig.

        Raises:
            ValueError: If validation fails with all error details.
        """
        try:
            return AppConfig.model_validate(data)
        except Exception as exc:
            errors: list[str] = []
            if hasattr(exc, "errors"):
                for err in exc.errors():
                    loc = " -> ".join(str(p) for p in err.get("loc", []))
                    msg = err.get("msg", "unknown error")
                    errors.append(f"  - {loc}: {msg}")
            else:
                errors.append(f"  - {exc}")
            raise ValueError(
                f"Configuration validation failed with {len(errors)} error(s):\n"
                + "\n".join(errors)
            ) from exc

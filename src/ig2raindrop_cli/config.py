"""Configuration management using Pydantic Settings.

Reads from environment variables and an optional TOML config file.
Follows the same patterns as x2raindrop-cli.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Default paths ────────────────────────────────────────────────────


def get_default_config_dir() -> Path:
    """Get the default data directory (.ig2raindrop/ in cwd)."""
    return Path.cwd() / ".ig2raindrop"


def get_default_config_path() -> Path:
    """Get the default config file path (config.toml in cwd)."""
    return Path.cwd() / "config.toml"


def get_default_session_path() -> Path:
    """Get the default Instagram session storage path."""
    return get_default_config_dir() / "ig_session.json"


# ── Settings classes ─────────────────────────────────────────────────


class InstagramSettings(BaseSettings):
    """Instagram authentication settings.

    Supports username/password with optional 2FA via TOTP seed.
    Sessions are cached to disk for reuse.

    Attributes:
        username: Instagram username.
        password: Instagram password (required for first login).
        totp_seed: TOTP seed (base32) for automatic 2FA code generation.
        session_path: Path to store the session file.
    """

    model_config = SettingsConfigDict(
        env_prefix="IG_",
        env_file=".env",
        extra="ignore",
    )

    username: str | None = Field(None, description="Instagram username")
    password: str | None = Field(None, description="Instagram password")
    totp_seed: str | None = Field(None, description="TOTP seed for 2FA (base32)")
    session_path: Path = Field(
        default_factory=get_default_session_path,
        description="Path to store Instagram session",
    )


class RaindropSettings(BaseSettings):
    """Raindrop.io API settings.

    Attributes:
        token: Raindrop.io API test token.
    """

    model_config = SettingsConfigDict(
        env_prefix="RAINDROP_",
        env_file=".env",
        extra="ignore",
    )

    token: str = Field("", description="Raindrop.io API token")


class SyncSettings(BaseSettings):
    """Sync behavior settings.

    Attributes:
        collection_id: Target Raindrop collection ID.
        collection_title: Optional collection title (for lookup).
        ig_collection: Instagram saved collection name to sync.
        tags: Tags to apply to created Raindrops.
        max_count: Maximum number of posts to fetch (0 = all).
        no_batch: Import one-by-one instead of batches.
        dry_run: If True, don't make any changes.
        map_ig_collections: If True, map Instagram collections to Raindrop
            sub-collections under ``collection_id``. Existing sub-collections
            are reused by name, missing ones are created automatically.
    """

    model_config = SettingsConfigDict(
        env_prefix="SYNC_",
        env_file=".env",
        extra="ignore",
    )

    collection_id: int | None = Field(None, description="Target Raindrop collection ID")
    collection_title: str | None = Field(None, description="Collection title for lookup")
    ig_collection: str | None = Field(None, description="Instagram saved collection name")
    tags: list[str] = Field(
        default_factory=lambda: ["instagram", "saved"], description="Tags to apply"
    )
    max_count: int = Field(0, description="Max posts to fetch (0 = all)")
    no_batch: bool = Field(False, description="Import one-by-one instead of batches")
    dry_run: bool = Field(False, description="Dry run mode")
    map_ig_collections: bool = Field(
        False,
        description="Map Instagram collections to Raindrop sub-collections",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


# ── Main settings ────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Main application settings combining all sub-settings.

    Attributes:
        instagram: Instagram API settings.
        raindrop: Raindrop.io API settings.
        sync: Sync behavior settings.
        config_path: Path to the config file.
        log_level: Logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    instagram: InstagramSettings = Field(
        default_factory=lambda: InstagramSettings.model_validate({})
    )
    raindrop: RaindropSettings = Field(default_factory=lambda: RaindropSettings.model_validate({}))
    sync: SyncSettings = Field(default_factory=lambda: SyncSettings.model_validate({}))
    config_path: Path = Field(
        default_factory=get_default_config_path,
        description="Path to config file",
    )
    log_level: str = Field("INFO", description="Logging level")

    @classmethod
    def from_file(cls, config_path: Path | None = None) -> Settings:
        """Load settings, merging config file values with env vars."""
        if config_path is None:
            config_path = get_default_config_path()

        data: dict[str, Any] = {"config_path": str(config_path)}

        if config_path.exists():
            with open(config_path, "rb") as f:
                file_config = tomllib.load(f)
            data = _deep_merge(file_config, data)

        return cls.model_validate(data)


# ── Config file management ───────────────────────────────────────────


def create_default_config(path: Path | None = None) -> Path:
    """Create a default config file template.

    Args:
        path: Path to create the config file. Uses default if None.

    Returns:
        Path to the created config file.
    """
    if path is None:
        path = get_default_config_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    default_config: dict[str, Any] = {
        "log_level": "INFO",
        "instagram": {
            "username": "",
            "password": "",
            "totp_seed": "",
        },
        "raindrop": {
            "token": "YOUR_RAINDROP_TOKEN",
        },
        "sync": {
            "collection_id": 0,
            "collection_title": "",
            "ig_collection": "",
            "tags": ["instagram", "saved"],
            "max_count": 0,
            "no_batch": False,
            "dry_run": False,
            "map_ig_collections": False,
        },
    }

    with open(path, "wb") as f:
        tomli_w.dump(default_config, f)

    return path


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config file and environment variables.

    Args:
        config_path: Optional path to config file. Uses default if None.

    Returns:
        Loaded Settings instance.
    """
    return Settings.from_file(config_path)


# ── Helpers ──────────────────────────────────────────────────────────


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Override wins for non-dict vals."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

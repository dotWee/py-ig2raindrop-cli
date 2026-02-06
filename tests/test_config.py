"""Tests for the configuration module."""

from __future__ import annotations

from pathlib import Path

from ig2raindrop_cli.config import (
    InstagramSettings,
    RaindropSettings,
    Settings,
    SyncSettings,
    _deep_merge,
    create_default_config,
    get_default_config_dir,
    get_default_config_path,
    get_default_session_path,
    load_settings,
)

# ── Default path tests ───────────────────────────────────────────────


class TestDefaultPaths:
    def test_config_dir_in_cwd(self) -> None:
        d = get_default_config_dir()
        assert d.name == ".ig2raindrop"
        assert d.parent == Path.cwd()

    def test_config_path(self) -> None:
        p = get_default_config_path()
        assert p.name == "config.toml"
        assert p.parent == Path.cwd()

    def test_session_path_in_config_dir(self) -> None:
        s = get_default_session_path()
        assert s.name == "ig_session.json"
        assert s.parent == get_default_config_dir()


# ── Settings model tests ─────────────────────────────────────────────


class TestInstagramSettings:
    def test_defaults(self) -> None:
        s = InstagramSettings.model_validate({})
        assert s.username is None
        assert s.password is None
        assert s.totp_seed is None
        assert s.session_path == get_default_session_path()

    def test_from_values(self) -> None:
        s = InstagramSettings.model_validate({"username": "user", "password": "pass"})
        assert s.username == "user"
        assert s.password == "pass"


class TestRaindropSettings:
    def test_defaults(self) -> None:
        s = RaindropSettings.model_validate({})
        assert s.token == ""

    def test_from_values(self) -> None:
        s = RaindropSettings.model_validate({"token": "abc-123"})
        assert s.token == "abc-123"


class TestSyncSettings:
    def test_defaults(self) -> None:
        s = SyncSettings.model_validate({})
        assert s.collection_id is None
        assert s.tags == ["instagram", "saved"]
        assert s.max_count == 0
        assert s.no_batch is False
        assert s.dry_run is False

    def test_parse_tags_from_string(self) -> None:
        s = SyncSettings.model_validate({"tags": "a, b, c"})
        assert s.tags == ["a", "b", "c"]

    def test_parse_tags_from_list(self) -> None:
        s = SyncSettings.model_validate({"tags": ["one", "two"]})
        assert s.tags == ["one", "two"]


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings.model_validate({})
        assert isinstance(s.instagram, InstagramSettings)
        assert isinstance(s.raindrop, RaindropSettings)
        assert isinstance(s.sync, SyncSettings)

    def test_from_file_nonexistent(self, tmp_path: Path) -> None:
        """When config file doesn't exist, returns defaults."""
        s = Settings.from_file(tmp_path / "missing.toml")
        assert s.raindrop.token == ""

    def test_from_file_with_content(self, tmp_path: Path) -> None:
        import tomli_w

        cfg_path = tmp_path / "config.toml"
        with open(cfg_path, "wb") as f:
            tomli_w.dump(
                {
                    "instagram": {"username": "testuser"},
                    "raindrop": {"token": "tok-123"},
                    "sync": {"tags": ["custom"]},
                },
                f,
            )

        s = Settings.from_file(cfg_path)
        assert s.instagram.username == "testuser"
        assert s.raindrop.token == "tok-123"
        assert s.sync.tags == ["custom"]


# ── create_default_config tests ──────────────────────────────────────


class TestCreateDefaultConfig:
    def test_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        result = create_default_config(p)
        assert result == p
        assert p.exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "config.toml"
        create_default_config(p)
        assert p.exists()

    def test_valid_toml(self, tmp_path: Path) -> None:
        import tomllib

        p = tmp_path / "config.toml"
        create_default_config(p)
        with open(p, "rb") as f:
            data = tomllib.load(f)
        assert "instagram" in data
        assert "raindrop" in data
        assert "sync" in data

    def test_default_token_placeholder(self, tmp_path: Path) -> None:
        import tomllib

        p = tmp_path / "config.toml"
        create_default_config(p)
        with open(p, "rb") as f:
            data = tomllib.load(f)
        assert data["raindrop"]["token"] == "YOUR_RAINDROP_TOKEN"


# ── load_settings tests ──────────────────────────────────────────────


class TestLoadSettings:
    def test_load_defaults(self, tmp_path: Path) -> None:
        s = load_settings(tmp_path / "nope.toml")
        assert isinstance(s, Settings)

    def test_load_from_file(self, tmp_path: Path) -> None:
        import tomli_w

        cfg = tmp_path / "cfg.toml"
        with open(cfg, "wb") as f:
            tomli_w.dump({"raindrop": {"token": "real-token"}}, f)

        s = load_settings(cfg)
        assert s.raindrop.token == "real-token"


# ── _deep_merge tests ────────────────────────────────────────────────


class TestDeepMerge:
    def test_flat_merge(self) -> None:
        base = {"a": 1, "b": 2}
        over = {"b": 3, "c": 4}
        assert _deep_merge(base, over) == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        base = {"x": {"a": 1, "b": 2}}
        over = {"x": {"b": 3}}
        assert _deep_merge(base, over) == {"x": {"a": 1, "b": 3}}

    def test_override_wins_non_dict(self) -> None:
        base = {"a": {"nested": True}}
        over = {"a": "replaced"}
        assert _deep_merge(base, over) == {"a": "replaced"}

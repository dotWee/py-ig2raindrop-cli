"""Tests for the Instagram API client (instagrapi wrapper)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ig2raindrop_cli.instagram_api import InstagramClient

# ── Helpers ──────────────────────────────────────────────────────────


def _make_media(
    code: str = "ABC123",
    caption_text: str | None = "test caption",
    taken_at: datetime | None = None,
) -> MagicMock:
    """Create a fake instagrapi Media object."""
    media = MagicMock()
    media.code = code
    media.caption_text = caption_text
    media.taken_at = taken_at or datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    return media


def _make_collection(
    pk: int = 1,
    name: str = "My Collection",
    media_count: int = 5,
) -> MagicMock:
    col = MagicMock()
    col.id = pk
    col.name = name
    col.media_count = media_count
    return col


# ── media_to_item tests ─────────────────────────────────────────────


class TestMediaToItem:
    def test_builds_permalink(self) -> None:
        media = _make_media(code="XYZ789")
        item = InstagramClient._media_to_item(media)
        assert item.href == "https://www.instagram.com/p/XYZ789/"

    def test_uses_caption_as_title(self) -> None:
        media = _make_media(caption_text="Hello world")
        item = InstagramClient._media_to_item(media)
        assert item.title == "Hello world"

    def test_truncates_long_caption(self) -> None:
        long_caption = "A" * 200
        media = _make_media(caption_text=long_caption)
        item = InstagramClient._media_to_item(media)
        assert len(item.title) == 121  # 120 chars + "…"
        assert item.title.endswith("…")

    def test_empty_caption(self) -> None:
        media = _make_media(caption_text="")
        item = InstagramClient._media_to_item(media)
        assert item.title == ""

    def test_none_caption(self) -> None:
        media = _make_media(caption_text=None)
        item = InstagramClient._media_to_item(media)
        assert item.title == ""

    def test_extracts_timestamp(self) -> None:
        dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC)
        media = _make_media(taken_at=dt)
        item = InstagramClient._media_to_item(media)
        assert item.timestamp == int(dt.timestamp())

    def test_naive_datetime_treated_as_utc(self) -> None:
        dt = datetime(2024, 6, 15, 10, 30, 0)  # naive
        media = _make_media(taken_at=dt)
        item = InstagramClient._media_to_item(media)
        expected = int(dt.replace(tzinfo=UTC).timestamp())
        assert item.timestamp == expected

    def test_none_taken_at(self) -> None:
        media = _make_media()
        media.taken_at = None
        item = InstagramClient._media_to_item(media)
        assert item.timestamp > 0  # falls back to now()


# ── fetch_saved_posts tests ──────────────────────────────────────────


class TestFetchSavedPosts:
    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_returns_export(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collection_medias.return_value = [
            _make_media(code="A1"),
            _make_media(code="B2"),
        ]

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        export = client.fetch_saved_posts()

        assert export.count == 2
        assert export.items[0].href == "https://www.instagram.com/p/A1/"
        mock_ig.collection_medias.assert_called_once_with("saved", amount=0)

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_respects_max_count(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collection_medias.return_value = [_make_media()]

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        client.fetch_saved_posts(max_count=10)

        mock_ig.collection_medias.assert_called_once_with("saved", amount=10)

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_empty_saves(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collection_medias.return_value = []

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        export = client.fetch_saved_posts()

        assert export.count == 0


# ── fetch_saved_collection tests ─────────────────────────────────────


class TestFetchSavedCollection:
    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_finds_by_name(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collections.return_value = [
            _make_collection(pk=42, name="Travel"),
            _make_collection(pk=99, name="Food"),
        ]
        mock_ig.collection_medias.return_value = [_make_media(code="T1")]

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        export = client.fetch_saved_collection("Travel")

        assert export.count == 1
        mock_ig.collection_medias.assert_called_once_with(42, amount=0)

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_case_insensitive(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collections.return_value = [_make_collection(pk=10, name="Travel")]
        mock_ig.collection_medias.return_value = []

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        client.fetch_saved_collection("TRAVEL")

        mock_ig.collection_medias.assert_called_once_with(10, amount=0)

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_not_found_raises(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collections.return_value = [_make_collection(name="Travel")]

        client = InstagramClient("user", "pass")
        client._client = mock_ig

        with pytest.raises(ValueError, match="not found"):
            client.fetch_saved_collection("NonExistent")


# ── list_collections tests ───────────────────────────────────────────


class TestListCollections:
    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_returns_list(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collections.return_value = [
            _make_collection(pk=1, name="Travel", media_count=10),
            _make_collection(pk=2, name="Food", media_count=5),
        ]

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        result = client.list_collections()

        assert len(result) == 2
        assert result[0]["name"] == "Travel"
        assert result[0]["count"] == 10
        assert result[1]["name"] == "Food"

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_empty_collections(self, mock_client_cls: MagicMock) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.collections.return_value = []

        client = InstagramClient("user", "pass")
        client._client = mock_ig
        result = client.list_collections()

        assert result == []


# ── login tests ──────────────────────────────────────────────────────


class TestLogin:
    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_fresh_login(self, mock_client_cls: MagicMock, tmp_path: Path) -> None:
        mock_ig = mock_client_cls.return_value
        session_file = tmp_path / "session.json"

        client = InstagramClient("user", "pass", session_path=session_file)
        client._client = mock_ig
        result = client.login()

        assert result is True
        mock_ig.login.assert_called_once()

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_login_failure(self, mock_client_cls: MagicMock, tmp_path: Path) -> None:
        mock_ig = mock_client_cls.return_value
        mock_ig.login.side_effect = Exception("Bad credentials")

        client = InstagramClient("user", "wrong", session_path=tmp_path / "s.json")
        client._client = mock_ig
        result = client.login()

        assert result is False

    @patch("ig2raindrop_cli.instagram_api.Client")
    def test_no_password_raises(self, mock_client_cls: MagicMock, tmp_path: Path) -> None:
        client = InstagramClient("user", session_path=tmp_path / "nope.json")
        client._client = mock_client_cls.return_value

        with pytest.raises(ValueError, match="Password is required"):
            client.login()

"""Tests for data models."""

from __future__ import annotations

from ig2raindrop_cli.models import (
    ImportResult,
    InstagramSavedItem,
    RaindropCreatePayload,
)


class TestInstagramSavedItem:
    def test_saved_at_from_timestamp(self) -> None:
        item = InstagramSavedItem(href="https://example.com", timestamp=1700000000)
        assert item.saved_at.year == 2023

    def test_saved_at_defaults_to_now(self) -> None:
        item = InstagramSavedItem(href="https://example.com", timestamp=0)
        assert item.saved_at is not None


class TestRaindropCreatePayload:
    def test_from_instagram_item_basic(self) -> None:
        item = InstagramSavedItem(
            href="https://www.instagram.com/p/ABC123/",
            title="Test",
            timestamp=1700000000,
        )
        payload = RaindropCreatePayload.from_instagram_item(item)
        assert payload.link == "https://www.instagram.com/p/ABC123/"
        assert payload.title == "Test"
        assert "instagram" in payload.tags

    def test_from_instagram_item_with_collection(self) -> None:
        item = InstagramSavedItem(href="https://example.com", title="X")
        payload = RaindropCreatePayload.from_instagram_item(item, collection_id=42)
        assert payload.collection == {"$id": 42}

    def test_from_instagram_item_custom_tags(self) -> None:
        item = InstagramSavedItem(href="https://example.com")
        payload = RaindropCreatePayload.from_instagram_item(item, tags=["custom"])
        assert payload.tags == ["custom"]

    def test_title_falls_back_to_href(self) -> None:
        item = InstagramSavedItem(href="https://example.com", title="")
        payload = RaindropCreatePayload.from_instagram_item(item)
        assert payload.title == "https://example.com"


class TestImportResult:
    def test_success_rate(self) -> None:
        r = ImportResult(total=10, created=8, failed=2)
        assert r.success_rate == 80.0

    def test_success_rate_zero_total(self) -> None:
        r = ImportResult(total=0)
        assert r.success_rate == 0.0

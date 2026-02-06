"""Tests for the Instagram export parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ig2raindrop_cli.instagram import parse_saved_posts

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def new_format_file(tmp_path: Path) -> Path:
    """Instagram export in the newer ``saved_saved_media`` format."""
    data = {
        "saved_saved_media": [
            {
                "title": "Cool post",
                "string_list_data": [
                    {
                        "href": "https://www.instagram.com/p/ABC123/",
                        "value": "",
                        "timestamp": 1700000000,
                    }
                ],
            },
            {
                "title": "Another post",
                "string_list_data": [
                    {
                        "href": "https://www.instagram.com/p/DEF456/",
                        "value": "some caption",
                        "timestamp": 1700001000,
                    }
                ],
            },
        ]
    }
    p = tmp_path / "saved_posts.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def legacy_format_file(tmp_path: Path) -> Path:
    """Instagram export as a flat list (older format)."""
    data = [
        {"href": "https://www.instagram.com/p/AAA111/", "title": "Flat 1", "timestamp": 1600000000},
        {"href": "https://www.instagram.com/p/BBB222/", "title": "Flat 2", "timestamp": 1600001000},
        {"url": "https://www.instagram.com/p/CCC333/", "title": "Flat 3", "timestamp": 1600002000},
    ]
    p = tmp_path / "saved_posts.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def duplicate_items_file(tmp_path: Path) -> Path:
    """Export with duplicate hrefs that should be deduplicated."""
    data = {
        "saved_saved_media": [
            {
                "title": "Dup 1",
                "string_list_data": [
                    {"href": "https://www.instagram.com/p/SAME/", "timestamp": 1700000000}
                ],
            },
            {
                "title": "Dup 2",
                "string_list_data": [
                    {"href": "https://www.instagram.com/p/SAME/", "timestamp": 1700001000}
                ],
            },
        ]
    }
    p = tmp_path / "saved_posts.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def empty_export_file(tmp_path: Path) -> Path:
    """Empty export with no saved items."""
    data: dict[str, list] = {"saved_saved_media": []}
    p = tmp_path / "saved_posts.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── Tests ────────────────────────────────────────────────────────────


class TestParseNewFormat:
    def test_parses_items(self, new_format_file: Path) -> None:
        export = parse_saved_posts(new_format_file)
        assert export.count == 2

    def test_extracts_href(self, new_format_file: Path) -> None:
        export = parse_saved_posts(new_format_file)
        assert export.items[0].href == "https://www.instagram.com/p/ABC123/"

    def test_extracts_title(self, new_format_file: Path) -> None:
        export = parse_saved_posts(new_format_file)
        assert export.items[0].title == "Cool post"

    def test_extracts_timestamp(self, new_format_file: Path) -> None:
        export = parse_saved_posts(new_format_file)
        assert export.items[0].timestamp == 1700000000


class TestParseLegacyFormat:
    def test_parses_items(self, legacy_format_file: Path) -> None:
        export = parse_saved_posts(legacy_format_file)
        assert export.count == 3

    def test_handles_url_key(self, legacy_format_file: Path) -> None:
        export = parse_saved_posts(legacy_format_file)
        hrefs = [i.href for i in export.items]
        assert "https://www.instagram.com/p/CCC333/" in hrefs


class TestDeduplication:
    def test_removes_duplicates(self, duplicate_items_file: Path) -> None:
        export = parse_saved_posts(duplicate_items_file)
        assert export.count == 1


class TestEmptyExport:
    def test_empty_returns_zero(self, empty_export_file: Path) -> None:
        export = parse_saved_posts(empty_export_file)
        assert export.count == 0


class TestInvalidInput:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_saved_posts(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{{not json}}", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            parse_saved_posts(p)

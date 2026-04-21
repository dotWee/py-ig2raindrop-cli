"""Tests for CLI tree rendering helpers and grouping logic."""

from __future__ import annotations

from unittest.mock import MagicMock

from rich.console import Console

from ig2raindrop_cli.cli import (
    _build_collections_tree,
    _get_parent_collection_id,
    _group_items_by_collection,
    _import_grouped_by_ig_collection,
)
from ig2raindrop_cli.config import Settings
from ig2raindrop_cli.models import ImportResult, InstagramSavedItem


def _render_tree_text(collections: list[dict]) -> str:
    """Render a collection tree to plain text for assertions."""
    console = Console(record=True, width=120)
    console.print(_build_collections_tree(collections))
    return console.export_text()


def test_get_parent_collection_id_from_nested_parent() -> None:
    """Extract parent IDs from nested parent payloads."""
    collection = {"_id": 2, "title": "child", "parent": {"$id": 1}}
    assert _get_parent_collection_id(collection) == 1


def test_get_parent_collection_id_from_flat_parent_id() -> None:
    """Extract parent IDs from flat parentId fields."""
    collection = {"_id": 3, "title": "child", "parentId": "2"}
    assert _get_parent_collection_id(collection) == 2


def test_build_collections_tree_renders_nested_structure() -> None:
    """Render child collections under their root in tree form."""
    collections = [
        {"_id": 1, "title": "Root", "count": 3},
        {"_id": 2, "title": "Child A", "count": 1, "parent": {"$id": 1}},
        {"_id": 3, "title": "Grandchild", "count": 1, "parent": {"$id": 2}},
        {"_id": 4, "title": "Child B", "count": 2, "parent": {"$id": 1}},
    ]

    tree_text = _render_tree_text(collections)
    assert "Root (id: 1, items: 3)" in tree_text
    assert "Child A (id: 2, items: 1)" in tree_text
    assert "Grandchild (id: 3, items: 1)" in tree_text
    assert "Child B (id: 4, items: 2)" in tree_text


# ── Grouping / mapping tests ─────────────────────────────────────────


def test_group_items_by_collection_splits_by_name() -> None:
    """Items are grouped by their ``collection_name``, including ``None``."""
    items = [
        InstagramSavedItem(href="https://a", collection_name="Tracks"),
        InstagramSavedItem(href="https://b", collection_name="Tracks"),
        InstagramSavedItem(href="https://c", collection_name="Memes"),
        InstagramSavedItem(href="https://d"),
    ]

    groups = _group_items_by_collection(items)

    assert set(groups) == {"Tracks", "Memes", None}
    assert len(groups["Tracks"]) == 2
    assert len(groups["Memes"]) == 1
    assert len(groups[None]) == 1


def test_import_grouped_routes_items_into_sub_collections() -> None:
    """Each IG collection gets mapped to its own Raindrop sub-collection."""
    items = [
        InstagramSavedItem(href="https://a", collection_name="Tracks"),
        InstagramSavedItem(href="https://b", collection_name="Memes"),
        InstagramSavedItem(href="https://c"),
    ]

    client = MagicMock()
    client.get_collections.return_value = [
        {"_id": 100, "title": "Instagram"},
        {"_id": 200, "title": "Tracks", "parent": {"$id": 100}},
    ]

    def find_or_create(title: str, *, parent_id: int, collections: list) -> int:  # noqa: ARG001
        if title.lower() == "tracks":
            return 200
        return 300  # freshly created for "Memes"

    client.find_or_create_sub_collection.side_effect = find_or_create
    client.import_items.return_value = ImportResult(total=1, created=1)

    result = _import_grouped_by_ig_collection(
        client,
        items,
        parent_id=100,
        settings=Settings.model_validate({}),
    )

    assert result.total == 3
    assert result.created == 3
    call_targets = [call.kwargs["collection_id"] for call in client.import_items.call_args_list]
    assert sorted(call_targets) == [100, 200, 300]


def test_import_grouped_skips_sub_collection_for_unassigned_items() -> None:
    """Items without an IG collection are sent to the parent collection."""
    items = [InstagramSavedItem(href="https://a")]
    client = MagicMock()
    client.get_collections.return_value = []
    client.import_items.return_value = ImportResult(total=1, created=1)

    _import_grouped_by_ig_collection(
        client,
        items,
        parent_id=77,
        settings=Settings.model_validate({}),
    )

    client.find_or_create_sub_collection.assert_not_called()
    assert client.import_items.call_args.kwargs["collection_id"] == 77

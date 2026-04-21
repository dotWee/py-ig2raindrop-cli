"""Tests for CLI tree rendering helpers."""

from __future__ import annotations

from rich.console import Console

from ig2raindrop_cli.cli import _build_collections_tree, _get_parent_collection_id


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

"""Parse Instagram data export files for saved posts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import InstagramExport, InstagramSavedItem


def parse_saved_posts(path: Path) -> InstagramExport:
    """Parse an Instagram saved-posts JSON export file.

    Supports multiple known export formats:
    - New format: ``saved_saved_media`` key with ``string_list_data``
    - Legacy format: flat list of objects with ``href``
    - Collections format: ``saved_saved_collections`` with nested items

    Args:
        path: Path to the JSON file from Instagram's data export.

    Returns:
        An ``InstagramExport`` containing all discovered saved items.

    Raises:
        FileNotFoundError: If the path does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[InstagramSavedItem] = []

    if isinstance(data, dict):
        # New format: { "saved_saved_media": [ ... ] }
        items.extend(_parse_saved_media(data.get("saved_saved_media", [])))

        # Collections format: { "saved_saved_collections": [ ... ] }
        for collection in data.get("saved_saved_collections", []):
            items.extend(_parse_saved_media(collection.get("string_list_data", [])))

        # Fallback: try top-level string_list_data
        items.extend(_parse_string_list_data(data.get("string_list_data", [])))

    elif isinstance(data, list):
        # Legacy: flat list of entries
        items.extend(_parse_flat_list(data))

    # Deduplicate by href
    seen: set[str] = set()
    unique: list[InstagramSavedItem] = []
    for item in items:
        if item.href not in seen:
            seen.add(item.href)
            unique.append(item)

    return InstagramExport(items=unique)


def _parse_saved_media(entries: list[dict[str, Any]]) -> list[InstagramSavedItem]:
    """Parse entries from the ``saved_saved_media`` array."""
    items: list[InstagramSavedItem] = []
    for entry in entries:
        title = entry.get("title", "")

        # Each entry may have string_list_data with the actual link
        for sld in entry.get("string_list_data", []):
            href = sld.get("href", "")
            if href:
                items.append(
                    InstagramSavedItem(
                        href=href,
                        title=title or sld.get("value", ""),
                        timestamp=sld.get("timestamp", 0),
                    )
                )

        # Some entries have media_list_data instead
        for mld in entry.get("media_list_data", []):
            uri = mld.get("uri", "")
            if uri and uri.startswith("http"):
                items.append(
                    InstagramSavedItem(
                        href=uri,
                        title=title or mld.get("title", ""),
                        timestamp=mld.get("creation_timestamp", 0),
                    )
                )

    return items


def _parse_string_list_data(entries: list[dict[str, Any]]) -> list[InstagramSavedItem]:
    """Parse a top-level ``string_list_data`` array."""
    items: list[InstagramSavedItem] = []
    for entry in entries:
        href = entry.get("href", "")
        if href:
            items.append(
                InstagramSavedItem(
                    href=href,
                    title=entry.get("value", ""),
                    timestamp=entry.get("timestamp", 0),
                )
            )
    return items


def _parse_flat_list(entries: list[dict[str, Any]]) -> list[InstagramSavedItem]:
    """Parse a legacy flat-list export format."""
    items: list[InstagramSavedItem] = []
    for entry in entries:
        href = entry.get("href", "") or entry.get("url", "") or entry.get("link", "")
        if href:
            items.append(
                InstagramSavedItem(
                    href=href,
                    title=entry.get("title", "") or entry.get("value", ""),
                    timestamp=entry.get("timestamp", 0),
                )
            )
    return items

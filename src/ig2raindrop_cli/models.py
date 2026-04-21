"""Data models for ig2raindrop-cli."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Instagram export models ──────────────────────────────────────────


class InstagramSavedItem(BaseModel):
    """A single saved item extracted from an Instagram data export."""

    href: str
    title: str = ""
    timestamp: int = 0
    collection_name: str | None = None
    """Name of the Instagram saved collection the item belongs to (if any)."""

    @property
    def saved_at(self) -> datetime:
        return (
            datetime.fromtimestamp(self.timestamp, tz=UTC)
            if self.timestamp
            else datetime.now(tz=UTC)
        )


class InstagramExport(BaseModel):
    """Parsed result of an Instagram saved-posts export file."""

    items: list[InstagramSavedItem] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)


# ── Raindrop.io models ──────────────────────────────────────────────


class RaindropType(StrEnum):
    LINK = "link"
    ARTICLE = "article"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"


class RaindropCreatePayload(BaseModel):
    """Payload to create a single raindrop (bookmark)."""

    link: str
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    collection: dict[str, int] | None = None  # {"$id": <collection_id>}
    created: str | None = None  # ISO-8601
    pleaseParse: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_instagram_item(
        cls,
        item: InstagramSavedItem,
        *,
        collection_id: int | None = None,
        tags: list[str] | None = None,
    ) -> RaindropCreatePayload:
        payload = cls(
            link=item.href,
            title=item.title or item.href,
            tags=tags or ["instagram", "saved"],
            created=item.saved_at.isoformat(),
            pleaseParse={"meta": "true"},
        )
        if collection_id is not None:
            payload.collection = {"$id": collection_id}
        return payload


class RaindropResponse(BaseModel):
    """Minimal response model for a created raindrop."""

    result: bool = False
    item: dict[str, Any] | None = None
    items: list[dict[str, Any]] | None = None
    errorMessage: str | None = None


# ── Import result tracking ──────────────────────────────────────────


class ImportResult(BaseModel):
    """Tracks the outcome of an import run."""

    total: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.created / self.total * 100) if self.total else 0.0

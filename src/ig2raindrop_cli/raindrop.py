"""Raindrop.io API client."""

from __future__ import annotations

import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from .models import (
    ImportResult,
    InstagramSavedItem,
    RaindropCreatePayload,
    RaindropResponse,
)

API_BASE = "https://api.raindrop.io/rest/v1"
BATCH_SIZE = 50  # Raindrop API batch limit

console = Console(stderr=True)


def _normalize_id(value: object) -> int | None:
    """Normalize an arbitrary Raindrop ID value to an integer."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _parent_id(collection: dict) -> int | None:
    """Extract the parent collection ID from a Raindrop collection payload."""
    parent = collection.get("parent")
    if isinstance(parent, dict):
        for key in ("$id", "_id", "id"):
            parent_id = _normalize_id(parent.get(key))
            if parent_id is not None:
                return parent_id
        return None
    if parent is not None:
        parent_id = _normalize_id(parent)
        if parent_id is not None:
            return parent_id
    for key in ("parentId", "parent_id"):
        parent_id = _normalize_id(collection.get(key))
        if parent_id is not None:
            return parent_id
    return None


class RaindropClient:
    """Thin wrapper around the Raindrop.io REST API."""

    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ── API methods ──────────────────────────────────────────────────

    def test_connection(self) -> bool:
        """Check that the API token is valid by fetching the user profile."""
        try:
            resp = self._client.get("/user")
            resp.raise_for_status()
            return resp.json().get("result", False)
        except httpx.HTTPError:
            return False

    def get_collections(self) -> list[dict]:
        """List all collections, including child collections when available."""
        root_resp = self._client.get("/collections")
        root_resp.raise_for_status()
        root_items = root_resp.json().get("items", [])

        child_items: list[dict] = []
        child_resp = self._client.get("/collections/childrens")
        if child_resp.status_code == 404:
            return root_items
        child_resp.raise_for_status()
        child_items = child_resp.json().get("items", [])

        merged: dict[int | str, dict] = {}
        for collection in [*root_items, *child_items]:
            collection_id = collection.get("_id")
            if collection_id is None:
                continue
            merged[collection_id] = collection
        return list(merged.values())

    def find_or_create_collection(self, title: str) -> int:
        """Find a collection by title or create it. Returns the collection ID."""
        collections = self.get_collections()
        for col in collections:
            if col.get("title", "").lower() == title.lower():
                return col["_id"]
        return self.create_collection(title)

    def create_collection(self, title: str, *, parent_id: int | None = None) -> int:
        """Create a new Raindrop collection, optionally as a sub-collection.

        Args:
            title: Title for the new collection.
            parent_id: Optional parent collection ID. When provided the new
                collection is created nested under that collection.

        Returns:
            The ID of the newly created collection.
        """
        payload: dict[str, object] = {"title": title}
        if parent_id is not None:
            payload["parent"] = {"$id": parent_id}

        resp = self._client.post("/collection", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result"):
            return int(data["item"]["_id"])
        raise RuntimeError(f"Failed to create collection '{title}': {data}")

    def find_or_create_sub_collection(
        self,
        title: str,
        *,
        parent_id: int,
        collections: list[dict] | None = None,
    ) -> int:
        """Find a sub-collection by title under ``parent_id`` or create it.

        Args:
            title: Title of the sub-collection.
            parent_id: ID of the parent Raindrop collection.
            collections: Optional pre-fetched list of all collections. When
                provided the lookup avoids an extra API call.

        Returns:
            The ID of the existing or newly created sub-collection.
        """
        if collections is None:
            collections = self.get_collections()

        title_lower = title.strip().lower()
        for col in collections:
            if str(col.get("title", "")).strip().lower() != title_lower:
                continue
            if _parent_id(col) == parent_id:
                return int(col["_id"])

        return self.create_collection(title, parent_id=parent_id)

    def create_raindrop(self, payload: RaindropCreatePayload) -> RaindropResponse:
        """Create a single raindrop (bookmark)."""
        resp = self._client.post("/raindrop", json=payload.model_dump(exclude_none=True))
        resp.raise_for_status()
        return RaindropResponse.model_validate(resp.json())

    def create_raindrops_batch(self, payloads: list[RaindropCreatePayload]) -> RaindropResponse:
        """Create multiple raindrops in a single batch request."""
        items = [p.model_dump(exclude_none=True) for p in payloads]
        resp = self._client.post("/raindrops", json={"items": items})
        resp.raise_for_status()
        return RaindropResponse.model_validate(resp.json())

    # ── High-level import ────────────────────────────────────────────

    def import_items(
        self,
        items: list[InstagramSavedItem],
        *,
        collection_id: int | None = None,
        tags: list[str] | None = None,
        batch: bool = True,
    ) -> ImportResult:
        """Import a list of Instagram saved items into Raindrop.io.

        Args:
            items: Parsed Instagram saved items.
            collection_id: Optional Raindrop collection ID.
            tags: Tags to apply to each bookmark.
            batch: Use batch API (faster) or one-by-one.

        Returns:
            An ``ImportResult`` with counts and any errors.
        """
        result = ImportResult(total=len(items))

        if not items:
            return result

        payloads = [
            RaindropCreatePayload.from_instagram_item(item, collection_id=collection_id, tags=tags)
            for item in items
        ]

        if batch:
            result = self._import_batch(payloads, result)
        else:
            result = self._import_single(payloads, result)

        return result

    def _import_batch(
        self, payloads: list[RaindropCreatePayload], result: ImportResult
    ) -> ImportResult:
        """Import payloads in batches."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Importing…", total=len(payloads))

            for i in range(0, len(payloads), BATCH_SIZE):
                chunk = payloads[i : i + BATCH_SIZE]
                try:
                    resp = self.create_raindrops_batch(chunk)
                    if resp.result:
                        created = len(resp.items) if resp.items else len(chunk)
                        result.created += created
                    else:
                        result.failed += len(chunk)
                        if resp.errorMessage:
                            result.errors.append(resp.errorMessage)
                except httpx.HTTPError as exc:
                    result.failed += len(chunk)
                    result.errors.append(f"Batch {i // BATCH_SIZE + 1}: {exc}")

                progress.advance(task, len(chunk))

        return result

    def _import_single(
        self, payloads: list[RaindropCreatePayload], result: ImportResult
    ) -> ImportResult:
        """Import payloads one by one (slower but more granular error handling)."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Importing…", total=len(payloads))

            for payload in payloads:
                try:
                    resp = self.create_raindrop(payload)
                    if resp.result:
                        result.created += 1
                    else:
                        result.failed += 1
                        if resp.errorMessage:
                            result.errors.append(f"{payload.link}: {resp.errorMessage}")
                except httpx.HTTPError as exc:
                    result.failed += 1
                    result.errors.append(f"{payload.link}: {exc}")

                progress.advance(task, 1)

        return result

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RaindropClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

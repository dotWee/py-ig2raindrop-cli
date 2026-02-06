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
        """List all root collections."""
        resp = self._client.get("/collections")
        resp.raise_for_status()
        return resp.json().get("items", [])

    def find_or_create_collection(self, title: str) -> int:
        """Find a collection by title or create it. Returns the collection ID."""
        collections = self.get_collections()
        for col in collections:
            if col.get("title", "").lower() == title.lower():
                return col["_id"]

        # Create new collection
        resp = self._client.post("/collection", json={"title": title})
        resp.raise_for_status()
        data = resp.json()
        if data.get("result"):
            return data["item"]["_id"]
        raise RuntimeError(f"Failed to create collection '{title}': {data}")

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

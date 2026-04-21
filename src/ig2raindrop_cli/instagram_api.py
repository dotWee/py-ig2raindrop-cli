"""Fetch Instagram saved posts via the unofficial private API (instagrapi)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from instagrapi import Client
from instagrapi.types import Media
from rich.console import Console

from .config import get_default_session_path
from .models import InstagramExport, InstagramSavedItem

console = Console(stderr=True)

DEFAULT_SESSION_PATH = get_default_session_path()
REQUEST_DELAY = 1.0  # seconds between paginated requests


class InstagramClient:
    """Wrapper around instagrapi for fetching saved posts."""

    def __init__(
        self,
        username: str,
        password: str | None = None,
        *,
        session_path: Path | None = None,
        totp_seed: str | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._session_path = session_path or DEFAULT_SESSION_PATH
        self._totp_seed = totp_seed
        self._client = Client()
        self._client.delay_range = [1, 3]  # built-in random delay between requests

    # ── Authentication ───────────────────────────────────────────────

    def login(self, *, verification_code: str | None = None) -> bool:
        """Authenticate with Instagram.

        Tries to restore a previous session first. Falls back to
        username/password login. Supports 2FA via ``verification_code``
        or TOTP seed.

        Returns:
            ``True`` if login succeeded.
        """
        # Try restoring existing session
        if self._session_path.exists():
            console.print("  Restoring saved session…")
            try:
                self._client.load_settings(self._session_path)
                self._client.login(self._username, self._password or "")
                self._client.get_timeline_feed()  # verify session is alive
                console.print("  [green]Session restored![/green]")
                self._save_session()
                return True
            except Exception:
                console.print("  [yellow]Saved session expired, logging in fresh…[/yellow]")

        if not self._password:
            raise ValueError(
                "Password is required for first-time login. "
                "Use --password or set IG_PASSWORD env var."
            )

        # Generate 2FA code from TOTP seed if available
        two_factor_code = verification_code
        if not two_factor_code and self._totp_seed:
            two_factor_code = self._client.totp_generate_code(self._totp_seed)

        try:
            self._client.login(
                self._username,
                self._password,
                verification_code=two_factor_code or "",
            )
        except Exception as exc:
            console.print(f"  [red]Login failed:[/red] {exc}")
            return False

        self._save_session()
        return True

    def _save_session(self) -> None:
        """Persist session to disk for reuse."""
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.dump_settings(self._session_path)

    # ── Fetching saved posts ─────────────────────────────────────────

    def fetch_saved_posts(self, *, max_count: int = 0) -> InstagramExport:
        """Fetch all saved posts (the "All Posts" saved collection).

        Args:
            max_count: Maximum number of posts to fetch. 0 = all.

        Returns:
            An ``InstagramExport`` containing the fetched items.
        """
        console.print("  Fetching saved posts…")

        amount = max_count if max_count > 0 else 0
        medias: list[Media] = self._client.collection_medias("saved", amount=amount)
        total = len(medias)
        console.print(f"  Processing [bold]{total}[/bold] fetched posts…")
        items: list[InstagramSavedItem] = []
        for index, media in enumerate(medias, start=1):
            items.append(self._media_to_item(media))
            self._print_progress(index, total, "saved posts")

        console.print(f"  Fetched [bold green]{len(items)}[/bold green] saved posts.")
        return InstagramExport(items=items)

    def fetch_saved_posts_with_collections(self, *, max_count: int = 0) -> InstagramExport:
        """Fetch saved posts and annotate each with its Instagram collection.

        Fetches the "All Posts" collection first, then iterates over every
        named Instagram saved collection and tags matching items with the
        collection name. Items that are not in any named collection keep
        ``collection_name`` set to ``None``. If a post belongs to multiple
        named collections, the last one iterated wins.

        Args:
            max_count: Maximum number of posts to fetch from "All Posts".
                0 = all. Named collections are always fetched in full so
                every item found in "All Posts" can be annotated.

        Returns:
            An ``InstagramExport`` with items enriched by ``collection_name``.
        """
        console.print("  Fetching saved posts…")

        amount = max_count if max_count > 0 else 0
        medias: list[Media] = self._client.collection_medias("saved", amount=amount)
        total_saved = len(medias)
        console.print(f"  Processing [bold]{total_saved}[/bold] fetched posts…")

        items_by_pk: dict[str, InstagramSavedItem] = {}
        for index, media in enumerate(medias, start=1):
            items_by_pk[str(media.pk)] = self._media_to_item(media)
            self._print_progress(index, total_saved, "saved posts")

        console.print(f"  Fetched [bold green]{len(items_by_pk)}[/bold green] saved posts.")

        try:
            collections = self._client.collections()
        except Exception as exc:
            console.print(f"  [yellow]Could not list collections: {exc}[/yellow]")
            return InstagramExport(items=list(items_by_pk.values()))

        named_collections = [col for col in collections if col.name.lower() != "all posts"]
        total_collections = len(named_collections)
        console.print(
            f"  Checking [bold]{total_collections}[/bold] Instagram collection"
            f"{'s' if total_collections != 1 else ''} for mapping…"
        )

        for collection_index, col in enumerate(named_collections, start=1):
            if col.name.lower() == "all posts":
                continue
            console.print(
                f"  Scanning [cyan]{col.name}[/cyan] ({collection_index}/{total_collections})…"
            )
            try:
                col_medias = self._client.collection_medias(col.id, amount=0)
            except Exception as exc:
                console.print(f"  [yellow]Skipping '{col.name}' (fetch failed: {exc})[/yellow]")
                continue

            collection_total = len(col_medias)
            for media_index, media in enumerate(col_medias, start=1):
                pk = str(media.pk)
                if pk in items_by_pk:
                    items_by_pk[pk].collection_name = col.name
                else:
                    item = self._media_to_item(media)
                    item.collection_name = col.name
                    items_by_pk[pk] = item
                self._print_progress(media_index, collection_total, f"items in '{col.name}'")

        return InstagramExport(items=list(items_by_pk.values()))

    def fetch_saved_collection(self, name: str, *, max_count: int = 0) -> InstagramExport:
        """Fetch saved posts from a named Instagram saved collection.

        Args:
            name: Name of the saved collection.
            max_count: Maximum number of posts to fetch. 0 = all.

        Returns:
            An ``InstagramExport`` containing the fetched items.
        """
        console.print(f"  Looking for collection [cyan]{name}[/cyan]…")

        collections = self._client.collections()
        target = None
        for col in collections:
            if col.name.lower() == name.lower():
                target = col
                break

        if target is None:
            available = [c.name for c in collections]
            raise ValueError(
                f"Collection '{name}' not found. Available: {', '.join(available) or '(none)'}"
            )

        console.print(f"  Fetching from [cyan]{target.name}[/cyan] (ID: {target.id})…")

        amount = max_count if max_count > 0 else 0
        medias = self._client.collection_medias(target.id, amount=amount)
        total = len(medias)
        console.print(f"  Processing [bold]{total}[/bold] fetched items…")

        items: list[InstagramSavedItem] = []
        for index, media in enumerate(medias, start=1):
            item = self._media_to_item(media)
            item.collection_name = target.name
            items.append(item)
            self._print_progress(index, total, f"items in '{target.name}'")

        console.print(f"  Fetched [bold green]{len(items)}[/bold green] items.")
        return InstagramExport(items=items)

    def list_collections(self) -> list[dict[str, Any]]:
        """List all saved collections.

        Returns:
            A list of dicts with ``id``, ``name``, and ``count`` keys.
        """
        collections = self._client.collections()
        return [
            {"id": str(col.id), "name": col.name, "count": col.media_count} for col in collections
        ]

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _print_progress(current: int, total: int, label: str) -> None:
        """Print throttled progress updates for long-running loops."""
        if total <= 0:
            return
        # Keep output useful but concise: always first/last, and then every 100
        # processed items (or every 25 for small batches).
        step = 25 if total <= 250 else 100
        if current == 1 or current == total or current % step == 0:
            percentage = (current / total) * 100
            console.print(
                f"    {label}: [bold]{current}/{total}[/bold] [dim]({percentage:.1f}%)[/dim]"
            )

    @staticmethod
    def _media_to_item(media: Media) -> InstagramSavedItem:
        """Convert an instagrapi ``Media`` object to our internal model."""
        # Build the Instagram post permalink
        href = f"https://www.instagram.com/p/{media.code}/"

        # Use caption text as title, truncated
        title = ""
        if media.caption_text:
            title = media.caption_text[:120]
            if len(media.caption_text) > 120:
                title += "…"

        # Convert taken_at datetime to unix timestamp
        taken_at = media.taken_at or datetime.now(tz=UTC)
        if taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=UTC)
        timestamp = int(taken_at.timestamp())

        return InstagramSavedItem(
            href=href,
            title=title,
            timestamp=timestamp,
        )

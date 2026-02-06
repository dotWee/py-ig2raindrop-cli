"""CLI interface for ig2raindrop-cli.

Provides the command-line interface using Typer with Rich output.
Follows the same sub-app structure as x2raindrop-cli.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import (
    Settings,
    create_default_config,
    get_default_config_path,
    load_settings,
)
from .instagram import parse_saved_posts
from .instagram_api import InstagramClient
from .models import ImportResult, InstagramExport
from .raindrop import RaindropClient

# ── App & sub-apps ───────────────────────────────────────────────────

app = typer.Typer(
    name="ig2raindrop",
    help="Sync Instagram saved posts to Raindrop.io",
    no_args_is_help=True,
)

ig_app = typer.Typer(help="Instagram related commands")
raindrop_app = typer.Typer(help="Raindrop.io related commands")
config_app = typer.Typer(help="Configuration management")

app.add_typer(ig_app, name="ig")
app.add_typer(raindrop_app, name="raindrop")
app.add_typer(config_app, name="config")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"ig2raindrop-cli version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Instagram saved posts to Raindrop.io sync tool."""


# ── sync command (top-level) ─────────────────────────────────────────


@app.command()
def sync(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    collection: Annotated[
        int | None,
        typer.Option(
            "--collection",
            help="Target Raindrop collection ID",
        ),
    ] = None,
    tags: Annotated[
        str | None,
        typer.Option(
            "--tags",
            "-t",
            help="Comma-separated tags to apply",
        ),
    ] = None,
    ig_collection: Annotated[
        str | None,
        typer.Option(
            "--ig-collection",
            help="Instagram saved collection name to sync",
        ),
    ] = None,
    max_count: Annotated[
        int | None,
        typer.Option(
            "--max",
            "-m",
            help="Maximum number of posts to fetch (0 = all)",
        ),
    ] = None,
    no_batch: Annotated[
        bool,
        typer.Option(
            "--no-batch",
            help="Import one-by-one instead of batches",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Don't make any changes, just show what would happen",
        ),
    ] = False,
) -> None:
    """Sync Instagram saved posts to Raindrop.io.

    Fetches your Instagram saved posts and creates corresponding
    Raindrop.io bookmarks in the configured collection.
    """
    try:
        settings = load_settings(config_path)

        # Override settings from CLI flags
        if collection is not None:
            settings.sync.collection_id = collection
        if tags is not None:
            settings.sync.tags = [t.strip() for t in tags.split(",") if t.strip()]
        if ig_collection is not None:
            settings.sync.ig_collection = ig_collection
        if max_count is not None:
            settings.sync.max_count = max_count
        if no_batch:
            settings.sync.no_batch = True
        if dry_run:
            settings.sync.dry_run = True

        # Validate Instagram credentials
        if not settings.instagram.username:
            console.print(
                "[red]Error:[/red] No Instagram username configured.\n"
                "Set IG_USERNAME in env or config file, or run [bold]ig2raindrop ig login[/bold]."
            )
            raise typer.Exit(1)

        # Validate Raindrop token
        if not settings.raindrop.token or settings.raindrop.token == "YOUR_RAINDROP_TOKEN":
            console.print(
                "[red]Error:[/red] No Raindrop.io token configured.\n"
                "Set RAINDROP_TOKEN in env or config file."
            )
            raise typer.Exit(1)

        if settings.sync.dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")

        # Show sync configuration
        table = Table(title="Sync Configuration", show_header=False)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Instagram User", settings.instagram.username)
        table.add_row("IG Collection", settings.sync.ig_collection or "(all saved)")
        table.add_row(
            "Max Posts", str(settings.sync.max_count) if settings.sync.max_count else "all"
        )
        table.add_row("Tags", ", ".join(settings.sync.tags) or "(none)")
        table.add_row(
            "Raindrop Collection",
            str(settings.sync.collection_id or settings.sync.collection_title or "(unsorted)"),
        )
        console.print(table)
        console.print()

        # Login to Instagram
        console.print("[bold]Logging in[/bold] to Instagram…")
        ig_client = InstagramClient(
            username=settings.instagram.username,
            password=settings.instagram.password,
            session_path=settings.instagram.session_path,
            totp_seed=settings.instagram.totp_seed,
        )

        if not ig_client.login():
            console.print("[red]Instagram login failed.[/red]")
            console.print("Run [bold]ig2raindrop ig login[/bold] to authenticate.")
            raise typer.Exit(1)

        console.print("  [green]Logged in![/green]\n")

        # Fetch saved posts
        if settings.sync.ig_collection:
            export = ig_client.fetch_saved_collection(
                settings.sync.ig_collection, max_count=settings.sync.max_count
            )
        else:
            export = ig_client.fetch_saved_posts(max_count=settings.sync.max_count)

        _import_to_raindrop(export, settings)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


# ── import-file command (top-level) ──────────────────────────────────


@app.command("import-file")
def import_file(
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the Instagram saved_posts.json export file.",
            exists=True,
            readable=True,
            resolve_path=True,
        ),
    ],
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    collection: Annotated[
        int | None,
        typer.Option(
            "--collection",
            help="Target Raindrop collection ID",
        ),
    ] = None,
    tags: Annotated[
        str | None,
        typer.Option(
            "--tags",
            "-t",
            help="Comma-separated tags to apply",
        ),
    ] = None,
    no_batch: Annotated[
        bool,
        typer.Option(
            "--no-batch",
            help="Import one-by-one instead of batches",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Don't make any changes, just show what would happen",
        ),
    ] = False,
) -> None:
    """Import saved posts from an Instagram JSON data export file."""
    try:
        settings = load_settings(config_path)

        if collection is not None:
            settings.sync.collection_id = collection
        if tags is not None:
            settings.sync.tags = [t.strip() for t in tags.split(",") if t.strip()]
        if no_batch:
            settings.sync.no_batch = True
        if dry_run:
            settings.sync.dry_run = True

        console.print(f"\n[bold]Parsing[/bold] {file.name}…")

        export = parse_saved_posts(file)

        _import_to_raindrop(export, settings)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


# ── ig subcommands ───────────────────────────────────────────────────


@ig_app.command("login")
def ig_login(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    verification_code: Annotated[
        str | None,
        typer.Option(
            "--2fa-code",
            help="One-time 2FA verification code",
        ),
    ] = None,
) -> None:
    """Authenticate with Instagram.

    Logs in and saves the session for future use. If you have a TOTP
    seed configured, 2FA codes are generated automatically.
    """
    try:
        settings = load_settings(config_path)

        if not settings.instagram.username:
            console.print(
                "[red]Error:[/red] No IG_USERNAME configured.\n"
                "Set it in config.toml or as an environment variable."
            )
            raise typer.Exit(1)
        if not settings.instagram.password:
            console.print(
                "[red]Error:[/red] No IG_PASSWORD configured.\n"
                "Set it in config.toml or as an environment variable."
            )
            raise typer.Exit(1)

        console.print("Starting Instagram login…")

        ig_client = InstagramClient(
            username=settings.instagram.username,
            password=settings.instagram.password,
            session_path=settings.instagram.session_path,
            totp_seed=settings.instagram.totp_seed,
        )

        if ig_client.login(verification_code=verification_code):
            console.print("[green]Successfully authenticated with Instagram![/green]")
            console.print(f"Session saved to: {settings.instagram.session_path}")
        else:
            console.print("[red]Instagram login failed.[/red]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@ig_app.command("status")
def ig_status(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Check Instagram authentication status."""
    try:
        settings = load_settings(config_path)

        if not settings.instagram.username:
            console.print("[yellow]No Instagram username configured.[/yellow]")
            raise typer.Exit(0)

        session_path = settings.instagram.session_path
        if session_path.exists():
            console.print("[green]Session file found[/green]")
            table = Table(show_header=False)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Username", settings.instagram.username)
            table.add_row("Session path", str(session_path))
            table.add_row("TOTP configured", "Yes" if settings.instagram.totp_seed else "No")
            console.print(table)
        else:
            console.print("[yellow]Not authenticated with Instagram[/yellow]")
            console.print("Run [bold]ig2raindrop ig login[/bold] to authenticate.")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@ig_app.command("logout")
def ig_logout(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Clear stored Instagram session."""
    try:
        settings = load_settings(config_path)
        session_path = settings.instagram.session_path

        if session_path.exists():
            session_path.unlink()
            console.print("[green]Instagram session cleared.[/green]")
        else:
            console.print("[dim]No session file to clear.[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@ig_app.command("collections")
def ig_collections(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """List your Instagram saved collections."""
    try:
        settings = load_settings(config_path)

        if not settings.instagram.username:
            console.print("[red]Error:[/red] No IG_USERNAME configured.")
            raise typer.Exit(1)

        ig_client = InstagramClient(
            username=settings.instagram.username,
            password=settings.instagram.password,
            session_path=settings.instagram.session_path,
            totp_seed=settings.instagram.totp_seed,
        )

        if not ig_client.login():
            console.print("[red]Instagram login failed.[/red]")
            console.print("Run [bold]ig2raindrop ig login[/bold] first.")
            raise typer.Exit(1)

        collections = ig_client.list_collections()

        if not collections:
            console.print("[yellow]No saved collections found.[/yellow]")
            raise typer.Exit(0)

        table = Table(title="Instagram Saved Collections")
        table.add_column("Name", style="cyan")
        table.add_column("Items", justify="right", style="bold")
        table.add_column("ID", style="dim")

        for col in collections:
            table.add_row(col["name"], str(col.get("count", "?")), col["id"])

        console.print(table)
        console.print(f"\nTotal: {len(collections)} collections")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


# ── raindrop subcommands ─────────────────────────────────────────────


@raindrop_app.command("collections")
def raindrop_collections(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """List available Raindrop.io collections."""
    try:
        settings = load_settings(config_path)

        if not settings.raindrop.token or settings.raindrop.token == "YOUR_RAINDROP_TOKEN":
            console.print("[red]Error:[/red] No RAINDROP_TOKEN configured.")
            raise typer.Exit(1)

        client = RaindropClient(settings.raindrop.token)
        raw_collections = client.get_collections()
        client.close()

        table = Table(title="Raindrop.io Collections")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title", style="green")
        table.add_column("Items", justify="right")

        for c in sorted(raw_collections, key=lambda x: x.get("title", "").lower()):
            table.add_row(
                str(c["_id"]),
                c.get("title", ""),
                str(c.get("count", "")),
            )

        console.print(table)
        console.print(f"\nTotal: {len(raw_collections)} collections")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


# ── config subcommands ───────────────────────────────────────────────


@config_app.command("init")
def config_init(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            "-p",
            help="Path for config file",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing config file",
        ),
    ] = False,
) -> None:
    """Create a default configuration file."""
    try:
        if path is None:
            path = get_default_config_path()

        if path.exists() and not force:
            console.print(f"[yellow]Config file already exists:[/yellow] {path}")
            console.print("Use --force to overwrite.")
            raise typer.Exit(1)

        created_path = create_default_config(path)
        console.print(f"[green]Created config file:[/green] {created_path}")
        console.print("\nEdit this file to add your API credentials.")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@config_app.command("show")
def config_show(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Show current configuration (with secrets masked)."""
    try:
        settings = load_settings(config_path)

        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        # Instagram settings
        table.add_row("IG Username", settings.instagram.username or "(not set)")
        table.add_row("IG Password", "***" if settings.instagram.password else "(not set)")
        table.add_row("IG TOTP Seed", "***" if settings.instagram.totp_seed else "(not set)")
        table.add_row("IG Session Path", str(settings.instagram.session_path))

        # Raindrop settings
        token = settings.raindrop.token
        table.add_row(
            "Raindrop Token",
            ("***" + token[-8:]) if token and token != "YOUR_RAINDROP_TOKEN" else "(not set)",
        )

        # Sync settings
        table.add_row(
            "Collection ID",
            str(settings.sync.collection_id) if settings.sync.collection_id else "(not set)",
        )
        table.add_row("Collection Title", settings.sync.collection_title or "(not set)")
        table.add_row("IG Collection", settings.sync.ig_collection or "(all saved)")
        table.add_row("Tags", ", ".join(settings.sync.tags) or "(none)")
        table.add_row(
            "Max Count", str(settings.sync.max_count) if settings.sync.max_count else "all"
        )
        table.add_row("No Batch", str(settings.sync.no_batch))
        table.add_row("Dry Run", str(settings.sync.dry_run))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@config_app.command("path")
def config_path_cmd() -> None:
    """Show the default config file path."""
    console.print(f"Default config path: {get_default_config_path()}")


# ── Shared import logic ──────────────────────────────────────────────


def _import_to_raindrop(export: InstagramExport, settings: Settings) -> None:
    """Common import logic shared by sync and import-file commands."""
    if export.count == 0:
        console.print("[yellow]No saved posts found.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"  Found [bold green]{export.count}[/bold green] saved posts.\n")

    if settings.sync.dry_run:
        _show_preview(export.items[:20], settings.sync.tags, export.count)
        raise typer.Exit(code=0)

    # Validate Raindrop token
    token = settings.raindrop.token
    if not token or token == "YOUR_RAINDROP_TOKEN":
        console.print("[red]Error:[/red] No RAINDROP_TOKEN configured.")
        raise typer.Exit(1)

    with RaindropClient(token) as client:
        console.print("[bold]Connecting[/bold] to Raindrop.io…")

        if not client.test_connection():
            console.print("[red]Failed to connect. Check your API token.[/red]")
            raise typer.Exit(code=1)

        console.print("  [green]Connected![/green]\n")

        # Resolve collection
        collection_id: int | None = settings.sync.collection_id
        if not collection_id and settings.sync.collection_title:
            console.print(
                f"[bold]Resolving[/bold] collection [cyan]{settings.sync.collection_title}[/cyan]…"
            )
            collection_id = client.find_or_create_collection(settings.sync.collection_title)
            console.print(f"  Using collection ID [bold]{collection_id}[/bold]\n")

        result = client.import_items(
            export.items,
            collection_id=collection_id,
            tags=settings.sync.tags,
            batch=not settings.sync.no_batch,
        )

    _show_results(result)

    if result.failed > 0:
        raise typer.Exit(code=1)


# ── Display helpers ──────────────────────────────────────────────────


def _show_preview(items: list, tag_list: list[str], total: int) -> None:
    """Show a preview table for dry-run mode."""
    table = Table(title="Preview (first 20 items)", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("URL", style="cyan", no_wrap=True, max_width=70)
    table.add_column("Title", max_width=30)

    for i, item in enumerate(items, 1):
        table.add_row(str(i), item.href, item.title or "—")

    console.print(table)
    if total > 20:
        console.print(f"  … and {total - 20} more items\n")
    console.print(f"  Tags: [bold]{', '.join(tag_list)}[/bold]")
    console.print("\n  [yellow]Dry run — no changes were made.[/yellow]\n")


def _show_results(result: ImportResult) -> None:
    """Show a summary panel after import."""
    lines = [
        f"  Total:   [bold]{result.total}[/bold]",
        f"  Created: [bold green]{result.created}[/bold green]",
        f"  Skipped: [bold yellow]{result.skipped}[/bold yellow]",
        f"  Failed:  [bold red]{result.failed}[/bold red]",
        f"  Success: [bold]{result.success_rate:.1f}%[/bold]",
    ]

    panel = Panel(
        "\n".join(lines),
        title="[bold]Import Results[/bold]",
        border_style="green" if result.failed == 0 else "red",
    )
    console.print(panel)

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors[:10]:
            console.print(f"  • {err}")
        if len(result.errors) > 10:
            console.print(f"  … and {len(result.errors) - 10} more errors")

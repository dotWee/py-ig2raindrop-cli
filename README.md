# ig2raindrop-cli

Sync Instagram saved posts to [Raindrop.io](https://raindrop.io) bookmarks — either from a JSON data export or directly via the Instagram API.

Follows the same CLI and configuration patterns as [x2raindrop-cli](https://github.com/dotWee/py-x2raindrop-cli).

## Installation

```bash
# Clone and install with uv
git clone <repo-url>
cd ig2raindrop-cli
uv sync --all-groups
```

## Quick Start

```bash
# 1. Create a config file
ig2raindrop config init

# 2. Edit config.toml with your credentials
#    - Set your Instagram username/password
#    - Set your Raindrop.io API token

# 3. Login to Instagram
ig2raindrop ig login

# 4. Sync saved posts to Raindrop.io
ig2raindrop sync
```

## Configuration

Settings are loaded from (in order of priority):

1. **CLI flags** — highest priority
2. **Environment variables** — prefixed with `IG_`, `RAINDROP_`, or `SYNC_`
3. **Config file** — `config.toml` (or path via `--config` / `-c`)
4. **Defaults** — built-in fallbacks

### Config File

Create a default config with `ig2raindrop config init`:

```toml
log_level = "INFO"

[instagram]
username = ""
password = ""
totp_seed = ""

[raindrop]
token = "YOUR_RAINDROP_TOKEN"

[sync]
collection_id = 0
collection_title = ""
ig_collection = ""
tags = ["instagram", "saved"]
max_count = 0
no_batch = false
dry_run = false
```

### Environment Variables

| Variable | Description |
| --- | --- |
| `IG_USERNAME` | Instagram username |
| `IG_PASSWORD` | Instagram password |
| `IG_TOTP_SEED` | TOTP seed for automatic 2FA (base32) |
| `RAINDROP_TOKEN` | Raindrop.io API test token |
| `SYNC_COLLECTION_ID` | Target Raindrop collection ID |
| `SYNC_TAGS` | Comma-separated tags |
| `SYNC_MAX_COUNT` | Maximum posts to fetch |

## Commands

### `sync` — Fetch from Instagram API and import to Raindrop.io

```bash
# Sync all saved posts using config file
ig2raindrop sync

# Sync a specific Instagram collection
ig2raindrop sync --ig-collection "Travel"

# Limit to 50 posts
ig2raindrop sync --max 50

# Dry run (preview only)
ig2raindrop sync --dry-run

# Use a custom config file
ig2raindrop sync -c /path/to/config.toml
```

### `import-file` — Import from a JSON data export

```bash
# Import from an Instagram data export file
ig2raindrop import-file saved_posts.json

# Into a specific Raindrop collection
ig2raindrop import-file saved_posts.json --collection 12345

# Custom tags
ig2raindrop import-file saved_posts.json --tags "instagram,bookmarks"

# Dry run
ig2raindrop import-file saved_posts.json --dry-run
```

### `ig` — Instagram subcommands

```bash
# Authenticate with Instagram
ig2raindrop ig login

# With a one-time 2FA code
ig2raindrop ig login --2fa-code 123456

# Check authentication status
ig2raindrop ig status

# Clear stored session
ig2raindrop ig logout

# List saved collections
ig2raindrop ig collections
```

### `raindrop` — Raindrop.io subcommands

```bash
# List all Raindrop.io collections
ig2raindrop raindrop collections
```

### `config` — Configuration management

```bash
# Create a default config.toml
ig2raindrop config init

# Show current configuration (secrets masked)
ig2raindrop config show

# Show the default config file path
ig2raindrop config path
```

### Global Options

| Option | Short | Description |
| --- | --- | --- |
| `--version` | `-v` | Show version and exit |
| `--config` | `-c` | Path to config file (on most commands) |

## Prerequisites

1. **Raindrop.io API token** — Create a test token at [Raindrop.io App Settings](https://app.raindrop.io/settings/integrations).

2. **One of the following sources:**
   - **Instagram data export** — Request your data from Instagram (Settings → Your Activity → Download Your Information). Select JSON format. The file you need is `saved_posts.json`.
   - **Instagram account credentials** — For `sync` and `ig` commands that use the Instagram API.

## Development

```bash
# Install dev dependencies
uv sync --all-groups

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --tb=short -q
```

## Release

The release workflow runs when a semantic version tag is pushed (for example `v1.0.0`).
It will:

- create a GitHub release with generated notes
- build source and wheel distributions
- publish packages to PyPI
- publish packages to GitHub Packages (Python registry)
- upload built artifacts to the GitHub release
- build and publish multi-arch Docker images to GHCR

### Maintainer checklist

```bash
# 1) Ensure all checks pass locally
uv sync --locked --all-groups
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest

# 2) Commit release changes (including version bump)
git add .
git commit -m "release: prepare v1.0.0"

# 3) Create and push tag
git tag v1.0.0
git push origin main --tags
```

## License

Copyright (c) 2026 Lukas 'dotWee' Wolfsteiner <lukas@wolfsteiner.media>

Licensed under the Do What The Fuck You Want To Public License. See the [LICENSE](LICENSE) file for details.

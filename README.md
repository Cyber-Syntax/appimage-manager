# appman

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux-FCC624?style=flat-square&logo=linux&logoColor=black)](https://www.kernel.org/)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](https://github.com/Cyber-Syntax/appimage-manager)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square)](LICENSE)

**appman** is a Linux-first command-line AppImage manager. It discovers
AppImages from GitHub releases, selects the most suitable Linux asset, downloads
it concurrently, and verifies it with GitHub's embedded SHA256 digest or a
published checksum file.

> [!WARNING]
> appman is currently an early alpha. The implemented workflow is focused on
> GitHub-based discovery, download, and verification. Desktop integration,
> persistent install state, updates, catalog installation, and removal are
> planned but are not available yet.

[Features](#features) • [Prerequisites](#prerequisites) •
[Installation](#installation) • [Usage](#usage) • [Development](#development)

## Features

- Install one or more AppImages from GitHub repository URLs.
- Resolve the latest GitHub release through the REST API.
- Prefer Linux AppImage assets and x86_64/AMD64 builds.
- Exclude Windows, macOS, ARM, source, and other incompatible assets.
- Prefer stable assets when both stable and prerelease-like names exist.
- Detect matching checksum assets, including release-wide manifests.
- Verify GitHub API SHA256 digests and checksum files.
- Report structured errors and warnings for network, asset, and verification
 outcomes.
- Download AppImages as streamed chunks using temporary `.part` files and
 atomic replacement.
- Process multiple targets concurrently with bounded API and download
 concurrency.
- Deduplicate repeated GitHub repositories in one command.
- Cache fetched release metadata locally.

## Prerequisites

- Linux
- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/)
- Internet access to the GitHub REST API and release asset URLs

## Installation

Clone the repository and install its locked dependencies with `uv`:

```bash
git clone https://github.com/Cyber-Syntax/appimage-manager.git
cd appimage-manager
uv sync
```

Run appman through the project environment:

```bash
uv run appman --help
```

## Usage

Install one AppImage from a GitHub repository:

```bash
uv run appman install https://github.com/pbek/QOwnNotes
```

Install multiple repositories in one transaction:

```bash
uv run appman install \
 https://github.com/pbek/QOwnNotes \
 https://github.com/super-productivity/super-productivity
```

Show help or the installed package version:

```bash
uv run appman --help
uv run appman --version
```

The current CLI accepts GitHub repository URLs. Catalog names, direct download
URLs, GitLab URLs, update commands, and other package-management commands are
planned for later releases.

### Verification behavior

For each selected AppImage, appman attempts both available verification paths:

1. GitHub's embedded SHA256 digest for the release asset.
2. A matching checksum asset, when published by the release.

Verification results distinguish passed, failed, missing, and corrupt checksum
data. A checksum mismatch is reported as a security-relevant failure; an
unparseable checksum file is reported separately as a warning.

## File locations

appman follows the XDG-oriented layout below:

| Purpose | Location |
| --- | --- |
| Configuration | `~/.config/appman/` |
| AppImages | `~/.local/share/appman/appimages/` |
| Application data | `~/.local/share/appman/` |
| Catalog data | `~/.local/share/appman/catalog/` |
| Backups | `~/.local/share/appman/backup/` |
| Release cache | `~/.cache/appman/` |
| Logs | `~/.local/state/appman/` |

The command initializes the required directories before dispatching the CLI.
Console logs are written to stderr, while detailed logs are written to the
rotating log file.

## Development

Install development dependencies:

```bash
uv sync --all-groups
```

Run the test suite with coverage:

```bash
uv run pytest
```

Run linting and type checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The main implementation is under [`src/appman`](src/appman). The module
boundaries are intentionally small:

- [`api.py`](src/appman/api.py) handles GitHub release data and asset selection.
- [`download.py`](src/appman/download.py) streams assets and coordinates
 verification.
- [`verify.py`](src/appman/verify.py) parses and checks digests and checksum
 files.
- [`install.py`](src/appman/install.py) orchestrates multi-target installs.
- [`models.py`](src/appman/models.py) contains canonical dataclasses and typed
 error/warning models.
- [`cli.py`](src/appman/cli.py) parses arguments and dispatches commands.

See [`docs/PRD.md`](docs/PRD.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
and [`docs/TODO.md`](docs/TODO.md) for product requirements, design decisions,
and the implementation roadmap.

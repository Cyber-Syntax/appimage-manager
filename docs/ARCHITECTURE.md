# appimage-manager Architecture

## 1. Technical Baseline

- Python 3.12+, Argparse, aiohttp (async networking), dataclasses, `uv` for packaging/install, Linux-only.

## 2. Module Layout

```
appman/
  cli.py        # argument parsing, dispatch
  config.py     # global + per-app config load/save/migrate
  constants.py  # constants
  download.py   # download and verify appimage
  install.py    # install orchestration
  logger.py     # logging init
  update.py     # update orchestration
  api.py        # GitHub REST client
  file_ops.py   # make executable...
  models.py     # all the dataclasses, enums...
  verify.py     # verify appimage internal logic

```

## 3. Storage Layout (XDG-aligned)

```
Config:    ~/.config/appman/
State:     ~/.local/share/appman/
Cache:     ~/.cache/appman/
Backups:   ~/.local/share/appman/backups/
Catalog:   ~/.local/share/appman/catalog/
Logs:      ~/.local/state/appman/
AppImages: ~/.local/share/appman/appimages/
Fallback:  ~/.local/share/appman/apps/
```

## 4. Catalog Strategy

- Catalog lives outside the package, in a separate folder instead of bundled in appman package, one JSON file per app (`appimage-manager/catalog/obsidian.json`, etc.).
- Synced into `~/.local/share/appman/catalog/` and refreshed via cache rules / `--check`.

## 5. API Strategy

- GitHub REST API (not GraphQL) for release metadata and assets — 60 req/hr unauthenticated.
- Actual AppImage downloads go through direct asset URLs, not the REST API, so downloads never consume rate limit.
- Token support (GTH) raises the ceiling but is explicitly non-MVP since real-world usage stays well under 60 req/hr per install/update batch.

## 6. Data Models

### 6.1 AppConfig

```python
@dataclass(slots=True)
class AppConfig:
    name: str
    repo: str
    installed_version: str
    appimage_path: Path
    desktop_file_path: Optional[Path] = None
    icon_path: Optional[Path] = None
    skip_verify: bool = False
    created_from_catalog: bool = True
    catalog_id: Optional[str] = None
```

### 6.2 CatalogEntry

```python
@dataclass(slots=True)
class CatalogEntry:
    name: str
    repo: str
    default_asset_pattern: Optional[str] = None
    allow_prerelease: bool = False
    allow_skip_verify: bool = False
    architecture: str = "x86_64"
```

Catalog entries override generic GitHub-derived behavior (e.g. FreeTube prerelease allowance).

### 6.3 GitHubRelease / ReleaseAsset

```python
@dataclass(slots=True)
class GitHubRelease:
    tag_name: str
    release_name: str
    prerelease: bool
    published_at: str
    assets: list["ReleaseAsset"]

@dataclass(slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int
    content_type: str
```

Open item: support `github_digest` (the API-embedded SHA256) as a first-class verification source, not just checksum files.

### 6.4 SelectedAssets

```python
@dataclass(slots=True)
class SelectedAssets:
    appimage: ReleaseAsset
    checksum_file: Optional[ReleaseAsset] = None
```

Rationale: resolve once, pass a small typed object everywhere instead of threading the full asset list through every function.

### 6.5 ChecksumResult

```python
class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    MISSING = "missing"
    SKIPPED = "skipped"

@dataclass(slots=True)
class ChecksumResult:
    status: VerificationStatus
    method: Optional[str] = None
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None
    source_file: Optional[str] = None
```

## 7. State File Schema (per app, JSON)

### URL installs

```json
{
  "catalog_ref": null,
  "config_version": "2.0.0",
  "overrides": {
    "appimage": {
      "naming": {
        "architectures": ["amd64", "x86_64"],
        "target_name": "keepassxc",
        "template": ""
      }
    },
    "icon": {
      "filename": "keepassxc.png",
      "method": "extraction"
    },
    "metadata": {
      "description": "",
      "display_name": "keepassxc",
      "name": "keepassxc"
    },
    "source": {
      "owner": "keepassxreboot",
      "prerelease": false,
      "repo": "keepassxc",
      "type": "github"
    },
    "verification": {
      "method": "digest"
    }
  },
  "source": "url",
  "state": {
    "icon": {
      "installed": true,
      "method": "extraction",
      "path": "/home/developer/Applications/icons/keepassxc.png"
    },
    "installed_date": "2026-05-11T12:32:41.646279+03:00",
    "installed_path": "/home/developer/Applications/keepassxc.AppImage",
    "verification": {
      "methods": [
        {
          "algorithm": "SHA256",
          "computed": "564fe8b751b9ef7aa057e4d3d0b2878db24eaa0f6b1c855c82e699ab0913ae49",
          "expected": "sha256:564fe8b751b9ef7aa057e4d3d0b2878db24eaa0f6b1c855c82e699ab0913ae49",
          "source": "github_api",
          "status": "passed",
          "type": "digest"
        },
        {
          "algorithm": "SHA256",
          "computed": "564fe8b751b9ef7aa057e4d3d0b2878db24eaa0f6b1c855c82e699ab0913ae49",
          "expected": "564fe8b751b9ef7aa057e4d3d0b2878db24eaa0f6b1c855c82e699ab0913ae49",
          "source": "https://github.com/keepassxreboot/keepassxc/releases/download/2.7.12/KeePassXC-2.7.12-x86_64.AppImage.DIGEST",
          "status": "passed",
          "type": "checksum_file"
        }
      ],
      "passed": true
    },
    "version": "2.7.12"
  }
}
```

### Catalog installs

```json
{
  "catalog_ref": "zen-browser",
  "config_version": "2.0.0",
  "source": "catalog",
  "state": {
    "icon": {
      "installed": true,
      "method": "extraction",
      "path": "/home/developer/Applications/icons/zen-browser.png"
    },
    "installed_date": "2026-06-27T15:18:39.457424+03:00",
    "installed_path": "/home/developer/Applications/zen-browser.AppImage",
    "verification": {
      "methods": [
        {
          "algorithm": "SHA256",
          "computed": "ea1763434255eff81d79f91f08a415b526a1d66663d1fa6cded40e0c87da4c05",
          "expected": "sha256:ea1763434255eff81d79f91f08a415b526a1d66663d1fa6cded40e0c87da4c05",
          "source": "github_api",
          "status": "passed",
          "type": "digest"
        }
      ],
      "passed": true
    },
    "version": "1.21.4b"
  }
}
```

## 8. Release Asset Selection Algorithm

```
latest stable release
  → Linux-only assets
  → AppImage extension only
  → architecture match (x86_64 preferred)
  → retain associated checksum asset if present
  → prereleases excluded unless catalog entry sets allow_prerelease
```

## 9. Verification Workflow

```
has checksum/digest?
  yes → verify
          pass → VERIFIED
          fail → prompt: install-without-verify or abort [y/n]
                   y → install continues, status=FAILED (recorded)
                   n → abort, nothing installed
  no  → catalog/user config allows skip?
          yes → status=SKIPPED, warn, remember decision in per-app JSON
          no  → status=MISSING, warn (may be upstream or appman limitation)
```

### logging/errors

- main output stdout, errors stderr
- allow pipe your data into other tools without mixing in progress messages
- \*EAFP = "Easier to Ask for Forgiveness than Permission"—a core Python philosophy
- Don't use number returns on python, use typed exception which more pythonic.

### Install Workflow

- Install from catalog name
- Install from GitHub/GitLab repository URL
- Install directly from download URL -> some apps provide direct url from their own website like libreoffice etc.
- Multi-target install support
- Verification support
- Desktop entry creation
- Icon extraction from appimage

### Update Workflow

- Check-only mode
- Targeted update mode
- Update-all mode
- Atomic update flow using temporary download directory

### Config and State Model

- Global settings config
- Per-app state config

### JSON Output (Essential)

no progress bar, no text, only json output for machine readable

#### update output

appman update --json

```json
{
  "success": true,
  "exit_code": 1,
  "operation": "update",
  "warnings": [
    {
      "package": "weektodo",
      "code": "no_checksum_skipped",
      "stage": "verify",
      "message": "no checksum provided by upstream : skipping verification"
    }
  ]
}
```

```json
{
  "success": true,
  "exit_code": 1,
  "operation": "update",
  "warnings": [
    {
      "package": "legcord",
      "code": "no_checksum_unsupported",
      "stage": "verify",
      "message": "checksum asset not found : some developers not provide any, please report an issue for the package maintainers if you verified this isn't appman fault"
    }
  ]
}
```

```json
{
  "success": true,
  "exit_code": 0,
  "operation": "update",
  "updated": [
    {
      "name": "qownnotes",
      "version": "26.2.4"
    }
  ]
}
```

#### install output

appman install --json

```json
{
  "success": false,
  "exit_code": 1,
  "operation": "install",
  "installed": [
    {
      "name": "qownnotes",
      "version": "26.2.4"
    }
  ],
  "failed": [
    {
      "name": "ytmdesktop",
      "kind": "asset",
      "code": "appimage_asset_not_found",
      "stage": "query",
      "retryable": false,
      "message": "appimage asset not found : appimage builds may still be processing, try again later. Some developers may not provide appimage builds, so this might be external to appman's control."
    }
  ]
}
```

## 12. Concurrency Model

- Downloads run concurrently (bounded by configurable `concurrency`, default conservative enough to stay under GitHub's recommended 20 concurrent connections).
- Verification, extraction, desktop-entry creation, and install steps run synchronously — they're cheap enough that concurrency isn't worth the complexity.
- A single `LockManager`-backed lock file ensures only one state-changing command (install/update/remove/restore) runs at a time:

```python
async with LockManager(lock_path):
    await self._execute_command(args)
```

## 13. Output Contract

- stdout: primary human/machine output only.
- stderr: logs/errors — keeps `appman ... | other-tool` pipelines clean.
- `--json` disables progress bar and color, and emits one of the documented JSON shapes (`install`, `update`, `check`) with `success`, `exit_code`, `operation`, plus `installed`/`updated`/`failed`/`warnings` arrays as relevant.

## 14. Design Principles

- Functional-first: pure functions by default; migrate a piece to OOP only when statefulness (e.g. `ReleaseCacheManager`, `GitHubAuthManager`) makes FP awkward.
- EAFP over manual existence-checking where idiomatic.
- Typed exceptions/structured errors over sentinel return codes — but per §10, expected failures are structured data, not raised exceptions.
- Catalog rules always take precedence over generic GitHub-inferred defaults.

### 15. Special warning/error for cli (Essential)

If we support app in our catalog, we could now their dev doesn't provide a checksum, so we skip verification and warn the user we skipped verification but if we don't support the app - if the user installed via url - than we need to warn the user we didn't able to find it and skipped verification but this might be my-unicorn fault or the app developer didn't provide a checksum.

Hard rule: **never raise domain errors across module boundaries; always return a structured `PackageError`/`PackageWarning`.** Exceptions are reserved for truly exceptional/internal failures, not expected business outcomes. `ERROR_MESSAGES`/`WARNING_MESSAGES` dicts centralize user-facing text for future i18n.

```python
from enum import Enum
from dataclasses import dataclass

class Stage(Enum):
    QUERY = "query"
    DOWNLOAD = "download"
    VERIFY = "verify"
    INSTALL = "install"

# stage=Stage.DOWNLOAD

class ErrorKind(Enum):
    NETWORK = "network"
    ASSET = "asset"
    VERIFICATION = "verification"
    PERMISSION = "permission"
    INTERNAL = "internal"

class ErrorCode(Enum):
    APPIMAGE_ASSET_NOT_FOUND = "appimage_asset_not_found"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DNS_FAILURE = "network_dns_failure"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN_ERROR = "unknown_error"

ERROR_MESSAGES = {
    ErrorCode.APPIMAGE_ASSET_NOT_FOUND:
        "appimage asset not found : appimage builds may still be processing, try again later. Some developers may not provide appimage builds, so this might be external to my-unicorn's control.",

    ErrorCode.NETWORK_TIMEOUT:
        "network timeout while downloading asset",

    ErrorCode.NETWORK_DNS_FAILURE:
        "could not resolve upstream host",

    ErrorCode.PERMISSION_DENIED:
        "permission denied",

    ErrorCode.CHECKSUM_MISMATCH:
        "checksum verification failed",

    ErrorCode.UNKNOWN:
        "an unknown error occurred",
}

class WarningCode(Enum):
    NO_CHECKSUM_SKIPPED = "no_checksum_skipped"
    NO_CHECKSUM_UNSUPPORTED = "no_checksum_unsupported"

WARNING_MESSAGES = {
    WarningCode.NO_CHECKSUM_SKIPPED:
        "no checksum provided by upstream : skipping verification",

    WarningCode.NO_CHECKSUM_UNSUPPORTED:
        "checksum asset not found : some developers not provide any, please report an issue for the package maintainers if you verified this isn't my-unicorn fault",
}

@dataclass
class PackageWarning:
    package: str
    code: WarningCode
    stage: str

@dataclass
class PackageError:
    package: str
    kind: ErrorKind
    code: ErrorCode
    stage: str
    retryable: bool = False


# Usage
error = PackageError(
    package="ytmdesktop",
    kind=ErrorKind.ASSET,
    code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
    stage="query",
    retryable=False,
)
# print stdout
print(
    f"error: {ERROR_MESSAGES[error.code]}"
)
print(
    f"error: failed retrieving '{error.package}' : "
    f"{ERROR_MESSAGES[error.code]}"
)
# logger stderr
logger.error(
    "package failed",
    extra={
        "package": error.package,
        "kind": error.kind.value,
        "code": error.code.value,
        "stage": error.stage,
    }
)
```

architecture flow:

```
ErrorKind
    broad category

ErrorCode
    exact issue

PackageError
    actual error object

ERROR_MESSAGES
    user-facing text

Stage
    transaction phase
```

important detail, never raise, return structured errors:

```python
# no raise
raise AssetNotFoundError()

# return package error
return PackageError()
```

# 3. Internal Architecture

```python
class Event(Enum):
    DOWNLOAD_STARTED = auto()
    DOWNLOAD_FINISHED = auto()
    APPIMAGE_VERIFIED = auto()
    APPIMAGE_VERIFICATION_SKIPPED = auto()
    APPIMAGE_INSTALLED = auto()
    APPIMAGE_FAILED = auto()

class Phase(Enum):
    QUERY = auto()
    DOWNLOAD = auto()
    VERIFY = auto()
    INSTALL = auto()
    SUMMARY = auto()
```

## 16. User stories

### 10.1 Install a catalog app

- **ID**: GH-001
- **Description**: As a Linux user, I want to install an app by catalog name so that I can get started quickly.
- **Acceptance criteria**:
  - Given a valid catalog app name, when install runs, then the tool downloads and installs exactly one AppImage.
  - The command output includes version and install path.
  - Exit code is 0 on success.

### 10.2 Install from GitHub URL

- **ID**: GH-002
- **Description**: As a Linux user, I want to install from a GitHub repository URL so that I can install apps not in catalog.
- **Acceptance criteria**:
  - Given a valid GitHub repo URL, install resolves owner/repo and fetches latest eligible release.
  - If no AppImage asset exists, command exits non-zero with clear error reason.
  - App state is persisted after successful install.

### 10.3 Multi-target install

- **ID**: GH-003
- **Description**: As a power user, I want to install multiple apps in one command so that I can bootstrap faster.
- **Acceptance criteria**:
  - Given mixed valid and invalid targets, command processes all valid targets and reports invalid ones.
  - Summary includes success, failure, and already-installed counts.
  - Partial success returns non-zero exit code with detailed per-target status.

### 10.4 Check updates without applying

- **ID**: GH-004
- **Description**: As an automation user, I want check-only mode so that I can monitor update availability.
- **Acceptance criteria**:
  - Check-only mode never modifies installed AppImages.
  - Output lists available updates and up-to-date apps separately.
  - Supports cache refresh override.

### 10.5 Update selected or all apps

- **ID**: GH-005
- **Description**: As a user, I want to update one, many, or all apps so that my apps stay current.
- **Acceptance criteria**:
  - Update with no targets processes all installed apps.
  - Update with targets processes only valid matches.
  - Summary includes updated, failed, and up-to-date groups.

### 10.6 Verification transparency

- **ID**: GH-006
- **Description**: As a security-conscious user, I want verification status clarity so that I can trust installed binaries.
- **Acceptance criteria**:
  - For digest/checksum verification, output and state include method and pass/fail status.
  - Missing checksums produce warning status, not silent success.
  - Verification failures block install/update by default.

### 10.7 Remove app and artifacts

- **ID**: GH-007
- **Description**: As a user, I want to remove an app cleanly so that no stale artifacts remain.
- **Acceptance criteria**:
  - Remove deletes AppImage and related desktop/icon/cache files when present.
  - Output explicitly lists removed and missing paths.

### 10.9 Backup and restore

- **ID**: GH-009
- **Description**: As a user, I want backup and restore commands so that I can recover from bad updates.
- **Acceptance criteria**:
  - Backup command stores versioned AppImage and metadata entry.
  - Restore-last and restore-version both validate target availability before replacing files.
  - Failed restore leaves current installed AppImage untouched.

### 10.11 Configuration migration safety

- **ID**: GH-011
- **Description**: As an existing user, I want reliable migration so that I can keep using current app state.
- **Acceptance criteria**:
  - Migration creates backups before modifying config files.
  - Migrated files pass schema validation.
  - Failed migration reports per-app reason and recovery path.

### 10.12 Non-interactive automation support

- **ID**: GH-012
- **Description**: As an automation user, I want stable output/exit semantics so that scripts can make decisions.
- **Acceptance criteria**:
  - Exit codes are documented and consistent across commands.
  - Machine-readable summary mode (JSON) is supported for install/update/check flows.
  - Verbose logging can be enabled.

### 10.13 Maintainer-friendly architecture

- **ID**: GH-013
- **Description**: As a maintainer, I want straightforward module boundaries so that I can change behavior safely.
- **Acceptance criteria**:
  - Each command maps to one orchestration module and a small set of direct collaborators.
  - New contributors can trace install or update flow end-to-end in under 10 minutes.
  - Use functional programming, write pure function for everything until you have problem with it than you can migrate OOP.
  - Core modules include tests for happy path and error path.

### 10.14 Performance and reliability guardrails

- **ID**: GH-014
- **Description**: As a maintainer, I want measurable guardrails so that rewrite quality remains enforceable.
- **Acceptance criteria**:
  - Learn and write Regression benchmarks track update-check latency and install runtime.
  - Release checklist includes smoke tests for install, update, remove, token, cache, and migrate commands.
  - Make sure all your test pass above %80
  - Detailed tests;
    - Unit, integration, e2e tests

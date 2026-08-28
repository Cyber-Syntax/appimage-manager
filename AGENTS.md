# AGENTS.md

Guidance for AI coding agents (and humans) working on **appimage-manager** (`appman`).

## 1. Project Overview

`appman` is a Linux-only CLI for installing, updating, verifying, backing up,
restoring, and removing AppImages — pacman-style, scriptable, checksum-verified.
Distributed via `uv`. No GUI, no web interface, no plugin system.

Read `PRD.md` / `ARCHITECTURE.md` in full before making structural changes.
This file summarizes the load-bearing rules an agent must not violate.

## 2. Tech Baseline

- Python 3.12+
- `argparse` for CLI parsing
- `aiohttp` for async networking
- `dataclasses` (with `slots=True`) for all data models
- Packaging/install via `uv`
- Linux-only

## 3. Module Layout — Respect Boundaries

```
appman/
  api.py        # GitHub REST client
  cli.py        # argument parsing, dispatch only
  config.py     # global + per-app config load/save/migrate
  constants.py
  download.py   # downloading assets (e.g appimage)
  file_ops.py   # download, extract, desktop entry, icon
  install.py    # install orchestration
  logger.py     # logging configurations
  main.py       # main orchestration
  models.py     # Canonical data models
  verify.py     # Verifying appimage
```

Rule of thumb (GH-013): each CLI command maps to **one orchestration module**
plus a small set of direct collaborators. A new contributor should be able to
trace `install` or `update` end-to-end in under 10 minutes. If a change makes
that harder, reconsider the design before merging.

Do not let `cli.py` contain business logic — it dispatches only.
Do not let `api.py` know about desktop entries/icons — that's `file_ops.py`.

## 4. Storage Layout (XDG — do not deviate)

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

Catalog JSON files (one per app, e.g. `catalog/obsidian.json`) live **outside** the `appimage-manager/src/appman` package in the `appimage-manager` repo (`appimage-manager/catalog/{obsidian,qownnotes,...}.json`), and are synced/refreshed into `~/.local/share/appman/catalog/`. Never bundle catalog data inside the installed package.

## 5. Design Principles (non-negotiable)

- **Functional-first.** Write pure functions by default. Only migrate a piece
  to OOP when statefulness genuinely demands it (e.g. `ReleaseCacheManager`,
  `GitHubAuthManager`). Don't introduce classes preemptively.
- **EAFP over LBYL.** Prefer try/except-driven flow over manual
  existence-checks, where idiomatic — but see error-handling rule below,
  which overrides this for cross-module boundaries.
- **Catalog rules always override generic GitHub-inferred defaults**
  (e.g. `allow_prerelease`, `allow_skip_verify` on `CatalogEntry`).
- **No sentinel return codes.** Errors are typed, not `-1`/`None`-as-error.
- Google style docstrings.

## 6. Error & Warning Handling — Critical Rule

**Never raise domain errors across module boundaries.** Business-outcome
failures (asset not found, checksum mismatch, permission denied, etc.) are
**returned**, not raised, as `PackageError`/`PackageWarning`.

```python
# WRONG
raise AssetNotFoundError()

# RIGHT
return PackageError(
    package="ytmdesktop",
    kind=ErrorKind.ASSET,
    code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
    stage="query",
    retryable=False,
)
```

Exceptions are reserved for truly exceptional/internal failures (e.g. a bug,
an unrecoverable I/O corruption) — not expected business outcomes like "no
checksum provided" or "asset missing."

Structure:

- `ErrorKind` — broad category (`network`, `asset`, `verification`, `permission`, `internal`)
- `ErrorCode` — exact issue (`appimage_asset_not_found`, `checksum_mismatch`, ...)
- `PackageError` — the actual error object (package, kind, code, stage, retryable)
- `PackageWarning` — same idea for non-fatal issues (`no_checksum_skipped`, `no_checksum_unsupported`)
- `ERROR_MESSAGES` / `WARNING_MESSAGES` — centralized user-facing text dicts (future i18n hook). Never inline user-facing error strings elsewhere.
- `Stage` — transaction phase (`query`, `download`, `verify`, `install/update`)

When adding a new failure mode: add an `ErrorCode`/`WarningCode` enum member
and a message dict entry — don't invent ad hoc strings inline.

### 6.1 Asset resolution codes

- `APPIMAGE_ASSET_NOT_FOUND` — used for **both** "dev never ships AppImage
  builds" and "build is still running" (some CI pipelines take up to ~1hr
  after a tag is published). Always set `retryable=True` on this code and
  keep the message hinting "may still be processing, try again later" —
  don't split this into two codes; the CLI can't reliably tell the
  difference from the API response alone, so let the retry hint cover both.

### 6.2 Verification-specific codes (new — see §8)

Add these alongside the existing ones:

```python
class ErrorCode(Enum):
    ...
    CHECKSUM_MISMATCH = "checksum_mismatch"        # real hash mismatch — security-relevant, always blocks by default

class WarningCode(Enum):
    ...
    NO_CHECKSUM_SKIPPED = "no_checksum_skipped"           # catalog-known: dev doesn't provide any verification
    NO_CHECKSUM_UNSUPPORTED = "no_checksum_unsupported"   # raw URL install, unknown why nothing's available
    CHECKSUM_FILE_CORRUPT = "checksum_file_corrupt"       # file present but unparseable/malformed — upstream build tooling issue (e.g. Electron packaging), NOT appman's fault, NOT a security failure
```

`CHECKSUM_MISMATCH` (real, parseable, wrong hash) and `CHECKSUM_FILE_CORRUPT`
(can't even parse it) must **not** share a code. A mismatch is a security
signal and should always prompt abort/continue. Corruption is a data-quality
problem — a warning, not a verification failure — and must not block
installs on its own if another verification method passes.

## 7. Output Contract

- **stdout**: primary human/machine output only.
- **stderr**: logs and errors — keeps `appman ... | other-tool` pipelines clean.
- `--json` disables the progress bar and color, and emits exactly one of the
  documented shapes (`install`, `update`, `check`) with `success`, `exit_code`,
  `operation`, plus `installed`/`updated`/`failed`/`warnings` arrays as relevant.
- Never mix progress-bar/log noise into stdout when `--json` is active.

## 8. Verification Policy — Do Not Weaken

Rules that must always hold:

- Verification failure blocks install/update **by default** (override needs explicit `y` or `--noconfirm`).
- Missing/skipped verification is **never silent** — it must warn and be recorded in per-app state (`skip_verify` in `AppConfig`, `verification.methods` in state JSON).
- Distinguish clearly in messaging between "catalog allows skip" (developer doesn't provide checksums, known) vs. "raw URL install with no checksum" (unknown — could be upstream's omission or appman's limitation). Don't collapse these into one message.
- `--noverify` skips verification entirely; `--noconfirm` auto-accepts prompts and must also remember `skip_verify` decisions per-app so the same prompt doesn't repeat.

### 8.1 Core rule: appman always checks, catalog flags never bypass checking

`allow_skip_verify: true` on a `CatalogEntry` is a **UX hint, not a bypass**.
It means "we already know this app's dev doesn't ship any checksum/digest,
so don't nag the user about it every run." It does **not** mean appman
skips the actual check. On every install/update, appman still:

1. Queries the GitHub API for an embedded digest.
2. Looks for a checksum asset (`.sha256`, `.sha512`, `.DIGEST`, etc.) on the release.

Both are attempted regardless of catalog config, `skip_verify` state, or
prior decisions — because a dev can start providing checksums at any time,
and appman must notice and start verifying again automatically.

### 8.2 Partial vs. full verification

- **Digest only** (GitHub API) available and passes → `VERIFIED`, method
  recorded as digest-only (partial).
- **Checksum file only** available, parses, and passes → `VERIFIED`, method
  recorded as checksum-file-only (partial).
- **Both** available and both pass → `VERIFIED`, full verification.
- **Checksum file present but corrupted/unparseable** (common with
  Electron-style build pipelines) → record `CHECKSUM_FILE_CORRUPT` as a
  **warning**, not a failure. If digest also passed, overall status stays
  `VERIFIED` (digest-only, partial) with the corruption warning attached.
  If digest isn't available either, fall through to §8.4 (no valid method
  found).
- **Any available method produces a real, parseable mismatch** → `FAILED`,
  go to §8.3. A passing digest does not override a failing checksum file
  (or vice versa) if the failure is a genuine mismatch rather than corruption
  — don't silently let one passing method mask a real one failing.

### 8.3 Verification FAILED (real mismatch found)

```

prompt: "Verification failed for <app>. Install anyway? [y/n]"
y → install continues, verification status=FAILED (recorded in state, never hidden)
n → abort: delete the downloaded AppImage only.
Nothing else exists yet at this point (see §8.5 ordering) — no
desktop file, no icon, no state entry to clean up.

```

### 8.4 No valid verification method found (missing or only corrupt)

This covers: no digest, no checksum asset, or checksum asset present but
unparseable and no digest to fall back on.

```

prompt: "No usable checksum/digest found for <app>. Install without
verification? [y/n]"

Context shown to user differs by install source: - catalog entry with allow_skip_verify=true →
"This app is known to not provide checksums (recorded in catalog)." - raw URL install (not in catalog) →
"Could not find a checksum — this may be the developer's omission
or an appman limitation."

y → status=SKIPPED, warn (code: NO_CHECKSUM_SKIPPED or
NO_CHECKSUM_UNSUPPORTED depending on source), remember decision as
skip_verify=true in the per-app state JSON, THEN proceed to install
(chmod +x, move to ~/.local/share/appman/appimages/, create desktop entry, extract icon).
n → abort: delete the downloaded AppImage only. Nothing else was created.

```

### 8.5 Ordering — why abort only ever deletes the AppImage

appman never creates the desktop file, icon, or state entry **before**
verification is resolved (pass, explicit skip, or accepted failure). The
sequence is always:

```

download AppImage
→ attempt verification (§8.2)
→ resolve outcome: VERIFIED | user accepted FAILED | user accepted SKIPPED
→ only then: chmod +x → move into ~/.local/share/appman/appimages/ → create .desktop → extract icon → write state JSON
```

So an abort at any verification prompt is always a clean, single-file
delete — never a partial install requiring desktop/icon/state cleanup.

### 8.6 Remembering decisions for fast, quiet updates

`skip_verify` (on `AppConfig`) records the user's past choice so `update`
doesn't re-prompt every run. But per §8.1, this is purely an
"don't-ask-again" flag, not a "don't-check-again" flag:

- On every update, appman still re-runs the digest/checksum lookup (§8.1–8.2).
- If verification is still unavailable/corrupt → honor the remembered
  `skip_verify=true` silently (no prompt), just emit the warning as before.
- If a digest or valid checksum has newly appeared upstream → appman
  verifies it for real. On pass, upgrade the recorded status to `VERIFIED`
  and consider clearing `skip_verify` (or at least noting in state that
  verification became available). On a genuine mismatch, this is now a
  security event — always prompt (§8.3), even though `skip_verify` was
  previously set. **Never let a stale skip_verify=true suppress a real
  mismatch prompt.**

### 8.7 Common workflow: URL install → later promoted to catalog

The typical maintainer flow is: install an app via raw URL first, then once
confirmed the dev provides no checksums, add it to the catalog with
`allow_skip_verify: true` (and `default_asset_pattern`, `architecture`, etc.)
so future users of that catalog entry get the friendlier §8.4 messaging
("known to not provide checksums") instead of the "may be upstream or
appman's limitation" URL-install messaging — without changing what appman
actually checks.

## 9. Data Models — Keep in Sync

Canonical dataclasses (all `@dataclass(slots=True)`):
`AppConfig`, `CatalogEntry`, `GitHubRelease`, `ReleaseAsset`, `SelectedAssets`,
`ChecksumResult` (+ `VerificationStatus` enum).

If you add a field to any of these, update:

1. The dataclass itself
2. The JSON state schema examples (`config_version` bump if breaking)
3. Migration logic in `config.py` (must back up before modifying, validate schema after — GH-011)

`SelectedAssets` exists specifically so code resolves the asset list **once**
and passes a small typed object around instead of threading the full asset
array through every function. Don't regress this by re-passing raw asset lists.

## 10. Concurrency Model

- Downloads: concurrent, bounded by a configurable `concurrency` (default conservative, under GitHub's recommended 20 concurrent connections).
- Verification, extraction, desktop-entry creation, install: **synchronous** — do not parallelize these, they're intentionally cheap and simple.
- Any state-changing command (`install`/`update`/`remove`/`restore`) must run inside the single `LockManager`-backed lock:

```python
async with LockManager(lock_path):
    await self._execute_command(args)
```

Never allow two state-changing commands to run concurrently against the same state directory.

## 11. GitHub API Usage

- REST API only (not GraphQL), for release metadata/assets. Unauthenticated limit: 60 req/hr.
- Actual AppImage **downloads** go through direct asset URLs, not the REST API — they must never consume rate limit.
- Prefer `github_digest` (API-embedded SHA256) as first-class verification source alongside checksum files — don't treat checksum files as the only verification method.

## 12. Release Asset Selection Algorithm

```
latest stable release
  → Linux-only assets
  → .AppImage extension only
  → architecture match (x86_64 preferred)
  → retain associated checksum asset if present
  → prereleases excluded unless catalog entry sets allow_prerelease
```

Implement as one composable pipeline, not scattered conditionals — this is the
kind of logic that should be a pure function taking a release + `CatalogEntry`
and returning `SelectedAssets` or a `PackageError`.

## 13. CLI Surface — Don't Silently Change Contracts

| Command                        | Purpose                                        |
| ------------------------------ | ---------------------------------------------- |
| `install`                      | catalog name, GitHub/GitLab URL, or direct URL |
| `update [names\|--check]`      | one/many/all/check-only                        |
| `remove`                       | AppImage + desktop file + icon + backups       |
| `upgrade`                      | self-upgrade via `uv`                          |
| `list --installed/--available` |                                                |
| `search`                       | catalog search, optional category              |
| `info`                         | metadata, verification status, install path    |
| `auth --status`                | token + rate-limit status                      |

Global flags: `--verbose`, `--version/-v`, `--noprogressbar`, `--no-color`,
`--json`, `--noverify`, `--noconfirm`, `--check`.

Changing exit codes, flag names, or JSON shapes is a **breaking change** for
automation users (GH-012) — flag it explicitly, don't do it incidentally
while fixing something else.

## 14. Testing Requirements

- ≥80% coverage on core modules — treat this as a hard floor, not a target.
- Every core module needs unit + integration + e2e coverage for both happy
  path and error path (GH-013/GH-014).
- Regression benchmarks for update-check latency and install runtime should
  not silently regress.
- Release checklist smoke tests: install, update, remove, token, cache, migrate.

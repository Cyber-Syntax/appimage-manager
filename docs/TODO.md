# appman Roadmap

## v0.1.0-alpha: Foundations

- [x] Create Python package structure and uv packaging
- [x] Add `appman` console entry point
- [x] Create basic CLI parser and command dispatch
- [x] Define canonical dataclasses and enums
- [x] Define typed errors and warnings
- [x] Define centralized error and warning messages
- [x] Create basic XDG config, data, cache, catalog, and log directories
- [x] Configure file and stderr logging
- [x] Add state directory and backup directory constants
- [ ] Add `LockManager` for state-changing commands
- [ ] Add initial architecture and storage-layout tests
- [ ] Fix current Ruff/mypy issues and placeholder-module errors

## v0.2.0-alpha: GitHub API and Asset Selection

- [x] Parse GitHub repository URLs
- [x] Fetch latest GitHub release
- [x] Convert API payloads into typed models
- [x] Handle HTTP, timeout, DNS, and malformed-response errors
- [x] Cache release metadata
- [x] Classify release assets
- [x] Select Linux AppImage assets
- [x] Prefer x86_64/amd64 assets
- [x] Exclude incompatible platform assets
- [x] Exclude unstable assets where possible
- [x] Detect associated checksum files
- [x] Preserve GitHub embedded asset digests
- [ ] Support catalog-specific selection rules

- [ ] Add real GitHub API integration tests

## v0.3.0-alpha: Download Pipeline

- [x] Download AppImages through direct asset URLs
- [x] Stream downloads in chunks
- [x] Use temporary `.part` files
- [x] Atomically move completed downloads into place
- [x] Download AppImage and checksum assets concurrently
- [x] Bound API concurrency
- [x] Bound download concurrency
- [x] Continue processing other targets after one target fails
- [x] Deduplicate duplicate GitHub targets
- [ ] Add visible progress bars
- [ ] Add download progress, speed, and size reporting
- [ ] Move downloads into a temporary/cache directory
- [ ] Clean up downloaded files after failed verification
- [ ] Add download integration tests

## v0.4.0-alpha: Complete GitHub Installation and Verification

- [x] Resolve GitHub URL to owner and repository
- [x] Resolve the latest eligible release
- [x] Select one AppImage asset
- [x] Verify GitHub embedded SHA256 digest
- [x] Verify checksum files
- [x] Detect checksum mismatches
- [x] Detect corrupt or unreadable checksum files
- [x] Represent VERIFIED, FAILED, MISSING, and SKIPPED states
- [x] Return structured verification warnings
- [ ] Make verification status affect the install result
- [ ] Block installation after verification failure by default
- [ ] Add confirmation prompt after verification failure
- [ ] Add missing-checksum confirmation flow
- [ ] Implement `--noverify`
- [ ] Remember `skip_verify` decisions
- [ ] Support SHA512 checksum files
- [ ] Print verification method and status in the summary
- [ ] Ensure aborted verification deletes only the downloaded AppImage
- [ ] Add verification policy tests
- [ ] Add the actual install step after verification succeeds
- [ ] Set AppImage executable permissions
- [ ] Rename or normalize installed AppImage filenames
- [ ] Move verified AppImages into the final AppImages directory

## v0.5.0-alpha: Desktop Integration and State

- [ ] Implement desktop-entry generation
- [ ] Extract icons from AppImages
- [ ] Install icons into the configured icon directory
- [ ] Persist per-app state JSON
- [ ] Persist installed version and install path
- [ ] Persist desktop and icon paths
- [ ] Persist verification method and status
- [ ] Distinguish URL installs from catalog installs
- [ ] Add state loading and saving helpers
- [ ] Add state schema validation
- [ ] Add end-to-end single-app installation test
- [ ] Confirm installed applications appear in GNOME/KDE menus

## v0.6.0-alpha: Catalog

- [ ] Finalize external catalog JSON format
- [ ] Keep catalog data outside the installed Python package
- [ ] Sync catalog files into the local catalog directory
- [ ] Load and validate catalog entries
- [ ] Install by catalog name
- [ ] Apply catalog asset-pattern overrides
- [ ] Apply catalog architecture overrides
- [ ] Apply catalog prerelease rules
- [ ] Apply catalog checksum-warning rules
- [ ] Implement `list --available`
- [ ] Implement `search`
- [ ] Implement `info`
- [ ] Add catalog tests

## v0.7.0-alpha: Update

- [ ] Add update orchestration module
- [ ] Implement update by app name
- [ ] Implement update-all
- [ ] Implement `update --check`
- [ ] Never mutate files in check-only mode
- [ ] Compare installed and upstream versions
- [ ] Re-run verification on every update
- [ ] Support remembered skip-verification decisions correctly
- [ ] Implement atomic update replacement
- [ ] Preserve the existing installation when an update fails
- [ ] Add update summaries
- [ ] Add update integration and end-to-end tests

## v0.8.0-alpha: Remove and CLI Contract

- [ ] Implement `remove`
- [ ] Remove AppImage files
- [ ] Remove desktop entries
- [ ] Remove icons
- [ ] Remove related backups and cache files
- [ ] Report removed and already-missing paths
- [ ] Add install confirmation prompts
- [ ] Add remove confirmation prompts
- [ ] Implement `--noconfirm`
- [ ] Implement `--noprogressbar`
- [ ] Implement `--no-color`
- [ ] Add shell completion
- [ ] Add stable exit-code tests

## v0.9.0-alpha: JSON and Automation

- [ ] Implement `--json`
- [ ] Keep logs and progress output out of JSON mode
- [ ] Implement install JSON output
- [ ] Implement update JSON output
- [ ] Implement check JSON output
- [ ] Include warnings and structured errors in JSON
- [ ] Document JSON schemas
- [ ] Add cron and systemd usage documentation
- [ ] Test non-interactive execution

## v0.10.0-alpha: Reliability

- [ ] Implement missing-file validation
- [ ] Detect missing AppImages, desktop files, icons, and state
- [ ] Add reinstall or repair suggestions
- [ ] Implement configuration migration
- [ ] Back up configuration before migration
- [ ] Validate migrated configuration
- [ ] Add per-app migration failure reporting
- [ ] Add state repair tests

## v0.11.0-alpha: Backup and Restore

- [ ] Implement versioned backups
- [ ] Store backup metadata and hashes
- [ ] Implement restore-last
- [ ] Implement restore by version
- [ ] Validate restore targets before replacement
- [ ] Preserve the active installation after failed restore
- [ ] Implement backup retention settings
- [ ] Add backup and restore tests

## v0.12.0-alpha: Self-Upgrade and Configuration

- [ ] Implement `appman upgrade`
- [ ] Detect current and latest appman versions
- [ ] Hand off upgrades to `uv`
- [ ] Add global TOML settings
- [ ] Configure download concurrency
- [ ] Configure backup retention
- [ ] Document configuration options

## v0.13.0-alpha: Test and Release Hardening

- [ ] Add unit tests for every core module
- [ ] Add API integration tests
- [ ] Add install, update, remove, and migration end-to-end tests
- [ ] Add network failure tests
- [ ] Add permission failure tests
- [ ] Add checksum mismatch regression tests
- [ ] Reach at least 80% coverage
- [ ] Run Ruff in CI
- [ ] Run mypy in CI
- [ ] Run dependency security auditing
- [ ] Add update latency benchmarks
- [ ] Add installation runtime benchmarks

## v1.0.0: Stable MVP

- [ ] Complete GitHub installation
- [ ] Complete catalog installation
- [ ] Complete verification workflow
- [ ] Complete desktop integration
- [ ] Complete state persistence
- [ ] Complete update workflow
- [ ] Complete remove workflow
- [ ] Complete JSON output
- [ ] Complete backup and restore
- [ ] Complete migration and repair behavior
- [ ] Complete documentation
- [ ] Run the complete release smoke-test checklist
- [ ] Tag and publish `v1.0.0`







## v1.1.0+: Post-MVP Features


- [ ] GitHub token authentication

- [ ] GitLab repository support
- [ ] Direct website/download URL improvements

- [ ] Bulk install from `.txt` or `.md` files
- [ ] Fuzzy catalog search and shell completion
- [ ] Category-based catalog search
- [ ] More advanced cache management
- [ ] Additional backup and restore policies
- [ ] Optional desktop notifications
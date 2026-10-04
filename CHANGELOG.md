# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha] - 2026-10-04

### Added

- Initial `appman` Python package and `uv` packaging configuration.
- CLI entry point with version, help, and `install` commands.
- GitHub repository URL parsing and latest-release retrieval.
- Typed models for releases, assets, selections, verification results, errors, warnings, and configuration.
- GitHub AppImage asset selection with:
  - Linux platform filtering.
  - x86_64/AMD64 preference.
  - Incompatible platform exclusion.
  - Unstable asset filtering.
  - Associated checksum-file detection.
- GitHub API embedded SHA256 digest support.
- Checksum-file parsing and SHA256 verification.
- Detection of checksum mismatches and corrupt checksum files.
- Structured error and warning codes with centralized messages.
- Concurrent multi-target installation processing.
- Duplicate GitHub target detection and warnings.
- Bounded API and download concurrency.
- Streaming asset downloads with temporary `.part` files.
- Atomic download completion using file replacement.
- Persisting GitHub release metadata as a JSON snapshot.  
- Default configuration, data, cache, backup, catalog, AppImage, and log directories under standard XDG paths.  
- File and stderr logging with rotating log files.

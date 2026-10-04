# appimage-manager PRD

## 1. Product Summary

appimage-manager (`appman`) is a Linux-first CLI for installing, updating, verifying, backing up, restoring, and removing AppImages, distributed via `uv`.

## 2. Problem Statement

Existing AppImage tools fall into two camps: GUI tools requiring manual interaction with no automation path, or CLI tools that skip checksum/digest verification entirely. Neither gives users a scriptable, verifiable, pacman-style workflow.

## 3. Target Users

- CLI-first Linux users
- Automation users (systemd/cron driven installs and updates)
- Developers who want predictable, scriptable package management
- Security-conscious users who want install-time integrity verification

## 4. User Stories (Core)

1. As a user, I want to install/update an AppImage from GitHub (and later GitLab or a direct URL) with a single command.
2. As a user, I want installed apps to appear in my GNOME/KDE app menu with the correct icon.
3. As a user, I want SHA256/SHA512 verification when available, with the option to skip and have that decision remembered.

## 5. Goals (MVP)

- Search and list catalog AppImages
- Install/update from GitHub releases, tracked via per-app state JSON
- Verify every available GitHub digest and checksum file; a mismatch from either is a verification failure but detailed warning, partial success, and skip options are available. (see verification policy below)
- Desktop entry + icon extraction
- Concurrent downloads, synchronous verify/install steps
- Progress bar (speed, size, percentage)
- Shell completion for CLI args
- Confirmation prompts (pacman-style) before install/delete
- Cron/systemd-friendly automation mode
- Validation/self-heal detection for missing desktop/icon/state files
- `--json` machine-readable output
- `Catalog/{appflowy,qownnotes}.json` is in appimage-manager repo but outside of appman package. So, we request appimage-manager repo to receive that catalog and save it locally. Sometimes, we refresh catalog for new supported apps.
- Typed error/warning codes (translatable, consistent messaging)
- Pre-release support on a per-catalog-entry basis (e.g. FreeTube)

## 6. Non-Goals

- GUI or web interface
- Non-Linux platform support
- Plugin systems or extension APIs

## 7. Good-to-Have (Post-MVP)

- GitLab and direct-website install support
- Fuzzy/partial-name shell completion `qow<tab>` would make it `qownotes`
- GitHub token support (auth status, rate-limit visibility, token usage logs)
- JSON Schema validation for state/config files
- Backup/restore with integrity-checked snapshots
- Self-upgrade command (`appman upgrade`, hands off to `uv`)
- Global TOML settings (`max_backup`, `max_concurrent_download`, etc.)
- Bulk install from a `.txt`/`.md` list (pacman-style export/import)

## 8. CLI Surface

| Command                          | Purpose                                                   |
| -------------------------------- | --------------------------------------------------------- |
| `install`                        | Install by catalog name, GitHub/GitLab URL, or direct URL |
| `update [names\|--check]`        | Update one, many, all, or check-only                      |
| `remove`                         | Remove AppImage + desktop file + icon + backups           |
| `upgrade`                        | Self-upgrade the CLI                                      |
| `list --installed / --available` | Show installed or catalog apps                            |
| `search`                         | Search catalog, optionally by category                    |
| `info`                           | Show metadata, verification status, install path          |
| `auth --status`                  | Show token + rate-limit status                            |

Global flags: `--verbose`, `--version/-v`, `--noprogressbar`, `--no-color`, `--json`, `--noverify`, `--noconfirm`, `--check`.

- `--verbose` : show everything verbose like chmod +x, moving appimage, appimage extraction, verification... all the internal processing logs shown on console.
- `--version` or `-v` : show version
- `--noprogressbar` : Do not show a progress bar when downloading files.
- `--no-color` : without any text colors
- `--json` : machine readeable json output, no text, no progress bar.
- `--noverify`: Doesn't verify appimage.
- `--noconfirm` : auto accept every confirmation - e.g auto accept update, install, delete failed -:
  - we need proper handling for delete failed, we must have a key to remember the decision for verification_skipped appimage to not ask confirmation again.
- `--check`: request a api to check versions only
- `remove`: remove appimage and it's own dependencies - icon, .desktop, backups -
- `update` : update the appimage via it's app_name - `appman update qownnotes appflowy`:
  - `appman update`: update all installed apps in the system
  - `appman update --check`: request api to check for versions only for installed packages (supported only for GitHub/GitLab because custom websites hard to handle(also I didn't find how to do it, so I have no idea what problems I am going to encounter...))
- `upgrade` : upgrade the cli - `appman upgrade`
- `install` : install the appimage via catalog name or GitHub/GitLab or direct download url.
- `info` : info for appimage like installed path, verification status, name, owner, size... `appman info qownnotes`

## 9. Verification Policy

### Summary for verification

- There is two verification methods for appimage from github provider. According to current appman versions, we only support github for now. So, those methods are named as checksum_file and digest.
  - checksum_file: This is the checksum file provided by the upstream developer. This is a file that contains the checksum of the appimage. (Examples: SHA256SUMS.txt, latest-linux.yml, qownnotes.AppImage.sha256, etc.)
  - digest: This is the checksum provided by the github provider. This is a checksum that is generated by github when the appimage is uploaded to the release. (Example: `"digest": "sha256:67ef7470c4183d9ebb0f1cd0d955edd18e03903ac4d766a9bf59ae01d4bf6e62",`)

### Verification behavior

- For each selected AppImage, appman attempts both available verification paths:
  1. digest: GitHub's embedded SHA256 digest for the release asset.
  2. checksum_file: A matching checksum asset, when published by the release.
- Verification results distinguish passed, failed, missing, and corrupt checksum data. A checksum mismatch is reported as a security-relevant failure; an unparseable checksum file is reported separately as a warning.
- Basically, if one method verifies the appimage, then the appimage is considered verified. If both methods fail, then the appimage is considered failed but user can choose to skip the verification if both verification fails (e.g STATUS=FAILED).
- If the upstream developer didn't provide any checksum file but appman supports the app and the catalog json file has allow_skip_verify set to true, then user can choose to skip the verification (e.g STATUS=SKIPPED).
- If the upstream developer didn't provide any checksum file and appman doesn't support the app, then appman will warn (e.g STATUS=MISSING). This warning happens if one of the method verified the app, otherwise STATUS=FAILED section will be shown to the user.
- If the upstream developer didn't provide any checksum file but appman supports the app and the catalog json file has allow_skip_verify set to true, then user can choose to skip the verification (e.g STATUS=SKIPPED). This happens if the upstream developer didn't provide any checksum file or even digest is available but appman supports the app and the catalog json file has allow_skip_verify set to true. This basically means appimage installed without verification.

## 10. Success Criteria

- MVP commands (install/update/remove/verify/list/search/info) work end-to-end against real GitHub repos.
- ≥80% test coverage with unit, integration, and e2e tests on core modules.
- Exit codes and `--json` output are stable and documented for scripting.
- Learning testing well and understand how code work with each other.

## 11. Acceptance Criteria (selected, full list maps to ARCH milestones)

- **Install by catalog name**: downloads exactly one AppImage, output includes version + path, exit 0 on success.
- **Install from GitHub URL**: resolves owner/repo, fetches latest eligible release, exits non-zero with a clear reason if no AppImage asset exists.
- **Multi-target install**: processes valid targets even if others fail; summary reports success/failure/already-installed counts; partial failure returns non-zero exit code.
- **Update check-only**: never mutates installed files; separates "available update" from "up to date".
- **Verification transparency**: state and CLI output always show method + pass/fail/skip, never silent success.
- **Remove**: deletes AppImage, desktop file, icon, and cache; explicitly lists removed vs. already-missing paths.
- **Backup/restore**: backup stores versioned AppImage + metadata; restore validates target exists before replacing; failed restore leaves the current install untouched.
- **Migration**: backs up config before modifying, validates against schema after, reports per-app failure + recovery path.

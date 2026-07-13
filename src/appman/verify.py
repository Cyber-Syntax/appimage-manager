"""Verification of downloaded AppImages."""

import hashlib
import re
from pathlib import Path

from .constants import CHUNK_SIZE
from .models import (
    Asset,
    ChecksumResult,
    PackageWarning,
    Stage,
    VerificationStatus,
    WarningCode,
)


def _parse_checksum_file(content: str, target_name: str) -> str | None:
    """Extract the hash for 'target_name' from checksum_file contents.

    Handles `sha256sum`-style lines (`<hash>  <filename>`) and bare-hash
    `.DIGEST` files with no filename. Returns None if unparseable — caller
    records CHECKSUM_FILE_CORRUPT (AGENTS.md §6.2), not a hard failure.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None

    if len(lines) == 1 and re.fullmatch(r"[0-9a-fA-F]{64}", lines[0]):
        return lines[0]

    for line in lines:
        match = _CHECKSUM_LINE_RE.match(line)
        if not match:
            continue
        hash_value, filename = match.groups()
        filename = filename.strip().lstrip("./")
        if filename == target_name or filename.endswith(target_name):
            return hash_value

    return None


def verify_downloaded_appimage(
    appimage_path: Path,
    appimage_asset: Asset,
    checksum_path: Path | None,
) -> tuple[ChecksumResult, list[PackageWarning]]:
    """Resolve verification status.

    Both the embedded digest (if the API gave one) and the checksum file
    (if downloaded) are checked independently — a real mismatch on either
    always wins over a pass on the other; corruption on the file is a
    warning, not a failure, and doesn't mask a passing digest.
    """
    package = appimage_asset.name
    warnings: list[PackageWarning] = []
    computed_hash: str | None = None
    digest_status: VerificationStatus | None = None
    checksum_status: VerificationStatus | None = None
    expected_from_file: str | None = None

    if appimage_asset.digest:
        computed_hash = _sha256_file(appimage_path)
        digest_status = (
            VerificationStatus.VERIFIED
            if computed_hash.lower() == appimage_asset.digest.lower()
            else VerificationStatus.FAILED
        )

    # FIXME: undefined read_checksum_text error
    if checksum_path is not None:
        text = _read_checksum_text(checksum_path)
        if text is None:
            warnings.append(
                PackageWarning(
                    package=package,
                    code=WarningCode.CHECKSUM_FILE_CORRUPT,
                    stage=Stage.VERIFY.value,
                )
            )
        else:
            expected_from_file = _parse_checksum_file(
                text, appimage_asset.name
            )
            if expected_from_file is None:
                warnings.append(
                    PackageWarning(
                        package=package,
                        code=WarningCode.CHECKSUM_FILE_CORRUPT,
                        stage=Stage.VERIFY.value,
                    )
                )
            else:
                if computed_hash is None:
                    computed_hash = _sha256_file(appimage_path)
                checksum_status = (
                    VerificationStatus.VERIFIED
                    if computed_hash.lower() == expected_from_file.lower()
                    else VerificationStatus.FAILED
                )

    # mismatch on either method blocks, regardless of the other
    if VerificationStatus.FAILED in (digest_status, checksum_status):
        failed_via_digest = digest_status == VerificationStatus.FAILED
        return (
            ChecksumResult(
                status=VerificationStatus.FAILED,
                method="digest" if failed_via_digest else "checksum_file",
                expected_hash=appimage_asset.digest
                if failed_via_digest
                else expected_from_file,
                actual_hash=computed_hash,
                source_file=str(checksum_path) if checksum_path else None,
            ),
            warnings,
        )

    if VerificationStatus.VERIFIED in (digest_status, checksum_status):
        both = (
            digest_status == VerificationStatus.VERIFIED
            and checksum_status == VerificationStatus.VERIFIED
        )
        method = (
            "digest+checksum_file"
            if both
            else (
                "digest"
                if digest_status == VerificationStatus.VERIFIED
                else "checksum_file"
            )
        )
        return (
            ChecksumResult(
                status=VerificationStatus.VERIFIED,
                method=method,
                expected_hash=appimage_asset.digest or expected_from_file,
                actual_hash=computed_hash,
                source_file=str(checksum_path) if checksum_path else None,
            ),
            warnings,
        )

    # no usable method
    return ChecksumResult(status=VerificationStatus.MISSING), warnings


# verify via github digest if exist
# verify via checksum_file if exist
def _sha256_file(path: Path) -> str:
    """Stream-hash a file. Sync and cheap by design, verify never runs concurrent."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

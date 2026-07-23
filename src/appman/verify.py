"""Verification of downloaded AppImages."""

import hashlib
import logging
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

logger = logging.getLogger(__name__)

# Matches standard `sha256sum`/`shasum`-style output lines:
#   <64-hex-char-hash>  <filename>
#   <64-hex-char-hash> *<filename>      (asterisk = binary mode marker)
# Filename may contain spaces, so it's greedy to end-of-line rather than
# split on whitespace.
_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")


def _parse_checksum_file(content: str, target_name: str) -> str | None:
    """Extract the hash for 'target_name' from checksum_file contents.

    Handles `sha256sum`-style lines (`<hash>  <filename>`) and bare-hash
    `.DIGEST` files with no filename. Returns None if unparseable — caller
    records CHECKSUM_FILE_CORRUPT, not a hard failure.

    Args:
        content: The text of the checksum file.
        target_name: The name of the AppImage file to match against.

    Returns:
        The hash string if found, or None if not found or unparseable.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if len(lines) == 1 and re.fullmatch(r"[0-9a-fA-F]{64}", lines[0]):
        logger.debug("Checksum file is a bare hash: %s", lines[0])
        return lines[0]

    for line in lines:
        match = _CHECKSUM_LINE_RE.match(line)
        if not match:
            logger.warning("Checksum file line is unparseable: %s", line)
            continue

        logger.debug("Checksum file line parsed: %s", line)
        hash_value, filename = match.groups()
        filename = filename.strip().lstrip("./")
        if filename == target_name or filename.endswith(target_name):
            logger.debug(
                "Checksum file line matches target: %s -> %s",
                filename,
                hash_value,
            )
            return hash_value

    return None


def _read_checksum_text(path: Path) -> str | None:
    """Read a checksum file's contents as text.

    Returns None on any read/decode fail, so the caller can record
    CHECKSUM_FILE_CORRUPT as warning rather than raising.

    Args:
        path: The path to the checksum file.

    Returns:
        The file's text content, or None if couldn't be read or decoded.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read checksum file %s: %s", path, exc)
        return None

    if not text.strip():
        logger.warning("Checksum file is empty: %s", path)
        return None

    return text


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

    Arguments:
        appimage_path: The path to the downloaded AppImage.
        appimage_asset: The Asset object for the AppImage.
        checksum_path: The path to the downloaded checksum file, or None if
            not present.

    Returns:
        A tuple of (ChecksumResult, list of PackageWarning).
    """
    package = appimage_asset.name
    warnings: list[PackageWarning] = []
    computed_hash: str | None = None
    digest_status: VerificationStatus | None = None
    checksum_status: VerificationStatus | None = None
    expected_from_file: str | None = None

    logger.debug(
        "Verifying downloaded AppImage: %s, checksum file: %s",
        appimage_path,
        checksum_path,
    )
    if appimage_asset.digest:
        logger.debug("Checking embedded digest: %s", appimage_asset.digest)
        computed_hash = _sha256_file(appimage_path)
        digest_status = (
            VerificationStatus.VERIFIED
            if computed_hash.lower() == appimage_asset.digest.lower()
            else VerificationStatus.FAILED
        )

    if checksum_path is not None:
        logger.debug("Checksum file exists, reading: %s", checksum_path)
        text = _read_checksum_text(checksum_path)
        if text is None:
            logger.warning(
                "Checksum file is unreadable or empty: %s", checksum_path
            )
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
                logger.warning(
                    "Failed to parse checksum file: %s", checksum_path
                )
                warnings.append(
                    PackageWarning(
                        package=package,
                        code=WarningCode.CHECKSUM_FILE_CORRUPT,
                        stage=Stage.VERIFY.value,
                    )
                )
            else:
                logger.debug(
                    "Checksum file parsed successfully: %s -> %s",
                    checksum_path,
                    expected_from_file,
                )
                if computed_hash is None:
                    logger.debug(
                        "Computing SHA256 for AppImage since not done yet: %s",
                        appimage_path,
                    )
                    computed_hash = _sha256_file(appimage_path)
                checksum_status = (
                    VerificationStatus.VERIFIED
                    if computed_hash.lower() == expected_from_file.lower()
                    else VerificationStatus.FAILED
                )

    logger.debug(
        "Verification results: digest=%s, checksum_file=%s",
        digest_status,
        checksum_status,
    )
    # mismatch on either method blocks, regardless of the other
    if VerificationStatus.FAILED in (digest_status, checksum_status):
        failed_via_digest = digest_status == VerificationStatus.FAILED
        result = ChecksumResult(
            status=VerificationStatus.FAILED,
            method="digest" if failed_via_digest else "checksum_file",
            expected_hash=appimage_asset.digest
            if failed_via_digest
            else expected_from_file,
            actual_hash=computed_hash,
            source_file=str(checksum_path) if checksum_path else None,
        )
        return result, warnings

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
        result = ChecksumResult(
            status=VerificationStatus.VERIFIED,
            method=method,
            expected_hash=appimage_asset.digest or expected_from_file,
            actual_hash=computed_hash,
            source_file=str(checksum_path) if checksum_path else None,
        )
        logger.debug("Verification passed: %s", result)
        return result, warnings

    # no usable method
    result = ChecksumResult(
        status=VerificationStatus.MISSING,
        method=None,
        expected_hash=None,
        actual_hash=None,
        source_file=str(checksum_path) if checksum_path else None,
    )
    logger.debug("Verification missing: %s", result)
    return result, warnings


def _sha256_file(path: Path) -> str:
    """Compute the SHA256 hash of a file.

    Args:
        path: The path to the file to hash.

    Returns:
        The SHA256 hash of the file as a hex string.
    """
    hasher = hashlib.sha256()

    logger.debug("Computing SHA256 for file: %s", path)

    # Read the file in chunks to avoid loading the entire file into memory
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

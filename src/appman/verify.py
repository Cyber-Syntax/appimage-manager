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

# TODO: add yml support
# TODO: add PARTIAL_VERIFIED support (e.g. digest verified but checksum file failed or other way around)

# Matches standard `sha256sum/sha512sum`/`shasum`-style output lines:
#   <64-hex-char-hash>  <filename>
#   <128-hex-char-hash>  <filename>
#   <64-hex-char-hash> *<filename>      (asterisk = binary mode marker)
# Filename may contain spaces, so it's greedy to end-of-line rather than
# split on whitespace.
_CHECKSUM_LINE_RE = re.compile(
    r"^([0-9a-fA-F]{64}|[0-9a-fA-F]{128})\s+\*?(.+)$"
)
# Matches a bare hash with no filename, which is valid for .DIGEST files.
_HASH_RE = re.compile(r"^[0-9a-fA-F]+$")


def _parse_checksum_file(content: str, target_name: str) -> str | None:
    """Extract a sha256 or sha512 hash for target_name.

    Handles `sha256sum/sha512sum`-style lines (`<hash>  <filename>`) and
    bare-hash `.DIGEST` files with no filename.

    Args:
        content: The text of the checksum file.
        target_name: The name of the AppImage file to match against.

    Returns:
        The hash string if found, or None if not found or unparseable.
        Caller records CHECKSUM_FILE_CORRUPT as a warning if None is returned.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if len(lines) == 1 and _HASH_RE.fullmatch(lines[0]):
        if len(lines[0]) == 64:
            logger.debug(
                "Checksum file is a bare SHA256 hash for target: %s",
                lines[0],
            )
            return lines[0]
        if len(lines[0]) == 128:
            logger.debug(
                "Checksum file is a bare SHA512 hash for target: %s",
                lines[0],
            )
            return lines[0]
        return None

    for line in lines:
        match = _CHECKSUM_LINE_RE.match(line)
        if not match:
            logger.warning("Checksum file line is unparseable: %s", line)
            continue

        logger.debug("Checksum file line parsed: %s", line)

        hash_value, filename = match.groups()
        filename = filename.strip()

        if len(hash_value) == 64:
            logger.debug(
                "Checksum file line is a SHA256 hash for target: %s -> %s",
                filename,
                hash_value,
            )
        elif len(hash_value) == 128:
            logger.debug(
                "Checksum file line is a SHA512 hash for target: %s -> %s",
                filename,
                hash_value,
            )
        else:
            logger.warning(
                "Checksum file line has unexpected hash length: %s", line
            )
            continue

        # Checksum files may contain paths such as ./releases/app.AppImage.
        # Match the exact basename, not a suffix.
        if Path(filename.strip()).name == target_name:
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
    MAX_CHECKSUM_FILE_SIZE = 1024 * 1024  # 1 MiB

    try:
        with path.open("rb") as fh:
            content = fh.read(MAX_CHECKSUM_FILE_SIZE + 1)
            if len(content) > MAX_CHECKSUM_FILE_SIZE:
                logger.warning("Checksum file is too large (>1 MiB): %s", path)
                return None
            text = content.decode("utf-8")
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

    Args:
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
                checksum_hash: str | None

                if len(expected_from_file) == 64:
                    logger.debug("Computing SHA256 for checksum verification")
                    checksum_hash = _sha256_file(appimage_path)
                elif len(expected_from_file) == 128:
                    logger.debug("Computing SHA512 for checksum verification")
                    checksum_hash = _sha512_file(appimage_path)
                else:
                    logger.warning(
                        "Checksum file has unexpected hash length: %d",
                        len(expected_from_file),
                    )
                    checksum_hash = None

                if checksum_hash is not None:
                    checksum_status = (
                        VerificationStatus.VERIFIED
                        if checksum_hash.lower() == expected_from_file.lower()
                        else VerificationStatus.FAILED
                    )

                    # Keep the checksum hash for checksum-only results.
                    if computed_hash is None:
                        computed_hash = checksum_hash

    logger.debug(
        "Verification results: digest=%s, checksum_file=%s",
        digest_status,
        checksum_status,
    )
    # mismatch on either method blocks, regardless of the other
    # source_file: only set if checksum file was used, not for digest
    if VerificationStatus.FAILED in (digest_status, checksum_status):
        failed_via_digest = digest_status == VerificationStatus.FAILED
        result = ChecksumResult(
            status=VerificationStatus.FAILED,
            method="digest" if failed_via_digest else "checksum_file",
            expected_hash=appimage_asset.digest
            if failed_via_digest
            else expected_from_file,
            actual_hash=computed_hash,
            source_file=str(checksum_path)
            if not failed_via_digest and checksum_path
            else None,
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
            source_file=str(checksum_path)
            if method in ("checksum_file", "digest+checksum_file")
            and checksum_path
            else None,
        )
        logger.debug("Verification passed: %s", result)
        return result, warnings

    # no usable method
    result = ChecksumResult(
        status=VerificationStatus.MISSING,
        method=None,
        expected_hash=None,
        actual_hash=None,
        source_file=None,
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
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha512_file(path: Path) -> str:
    """Compute the SHA512 hash of a file.

    Args:
        path: The path to the file to hash.

    Returns:
        The SHA512 hash of the file as a hex string.
    """
    hasher = hashlib.sha512()

    logger.debug("Computing SHA512 for file: %s", path)

    # Read the file in chunks to avoid loading the entire file into memory
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

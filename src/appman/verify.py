"""Verification of downloaded AppImages."""

import base64
import binascii
import hashlib
import logging
import re
from pathlib import Path

import yaml

from .models import (
    Asset,
    ChecksumResult,
    PackageWarning,
    Stage,
    VerificationStatus,
    WarningCode,
)

logger = logging.getLogger(__name__)

# Maps the length of a hex digest to the hashlib algorithm that produced it.
_HASH_ALGORITHM_BY_LENGTH = {64: "sha256", 128: "sha512"}


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
# Matches a bare hash with no filename, for `.sha256`/`.sha512` checksum files.
_HASH_RE = re.compile(r"^[0-9a-fA-F]+$")


def _decode_base64_sha512(value: object) -> str | None:
    """Decode an Electron-builder base64 SHA512 value to hexadecimal.

    Args:
        value: The base64-encoded SHA512 string.

    Returns:
        The decoded SHA512 hash as lowercase hexadecimal, or None if the
        value is not a valid base64-encoded SHA512 hash.
    """
    # check that the value is a string before attempting to decode it
    if not isinstance(value, str):
        return None

    try:
        # decode the base64 string and validate cause an error
        # if invalid characters or malformed padding are present
        decoded = base64.b64decode(value, validate=True)
    # malformed base64 is treated as invalid checksum data,
    # not as an application crash.
    except (binascii.Error, ValueError):
        logger.warning("YAML checksum file contains invalid base64")
        return None

    # decoded value must contain exactly 64 bytes (512 bits) for a SHA512 hash
    if len(decoded) != hashlib.sha512().digest_size:
        logger.warning("YAML checksum file contains a non-SHA512 hash")
        return None

    # return the decoded hash as a lowercase hexadecimal string
    # 64 bytest become a 128-character hex string
    return decoded.hex()


def _parse_latest_linux_yml(content: str, target_name: str) -> str | None:
    """Extract an Electron-builder SHA512 hash for target_name.

    Electron-builder stores SHA512 digests as base64 in either a matching
    ``files`` entry or the top-level ``path``/``sha512`` fields.

    Example latest-linux.yml content:
        version: 19.1.0
        files:
        - url: superProductivity-x86_64.AppImage
            sha512: LotnOiMGE6EMIpMuC5Xu1KQF1lAAshdDhEVd6N4PAP5vDozRjNYcmFVReUYZj1t1MPZpWwTWzEfQdF3HSpcbhQ==
            size: 145212036
            blockMapSize: 152216
        - url: superProductivity-amd64.deb
            sha512: tPx5Ynyty9Wtrq2mu9d47TK+WniDDbwCKSzEv8fXqsNrztDG2yBho3rkOuqRy7dykdPbawAyqGHt4PNyAcqhbA==
            size: 114282468
        - url: superProductivity-x86_64.rpm
            sha512: vYkvyNcsajyhbbv/4Z4KCNyeQqNblOpRkCAcdjxNsCWEhC5CYgC9FjW9Xt2UtUmyryGjpWjfoSZYZsPfQUdHfA==
            size: 100122185
        path: superProductivity-x86_64.AppImage
        sha512: LotnOiMGE6EMIpMuC5Xu1KQF1lAAshdDhEVd6N4PAP5vDozRjNYcmFVReUYZj1t1MPZpWwTWzEfQdF3HSpcbhQ==

    Args:
        content: The complete YAML file as text.
        target_name: The name of the AppImage to match.

    Returns:
        The decoded SHA512 hash as lowercase hexadecimal, or None if the
        manifest is malformed or does not identify target_name.
    """
    try:
        # parse the YAML content into a Python dictionary
        # safe_load: only loads a subset of YAML that is safe for untrusted input
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML checksum file: %s", exc)
        return None

    # validate that the root of the YAML document is a mapping (dictionary)
    if not isinstance(document, dict):
        logger.warning("YAML checksum file root is not a mapping")
        return None

    # search the files list for an entry matching the target_name
    files = document.get("files")
    if isinstance(files, list):
        for entry in files:
            # malformed entries are skipped, but the rest of the
            # list is still checked
            if not isinstance(entry, dict):
                continue

            # check if the entry has a "url" field that matches the target_name
            url = entry.get("url")
            if isinstance(url, str) and Path(url).name == target_name:
                # decode the base64 SHA512 value and return it as a hex string
                return _decode_base64_sha512(entry.get("sha512"))

    # fall back to searching the top-level path/sha512 fields for a match
    # if there is no matching entry in the files list
    path = document.get("path")
    if isinstance(path, str) and Path(path).name == target_name:
        return _decode_base64_sha512(document.get("sha512"))

    logger.warning(
        "YAML checksum file has no entry for target: %s", target_name
    )

    # if no matching entry was found in either the files list or the top-level
    # fields, return None
    return None


def _parse_checksum_file(
    content: str,
    target_name: str,
    checksum_filename: str | None = None,
) -> str | None:
    """Extract a sha256 or sha512 hash for target_name.

    Handles `sha256sum/sha512sum/.DIGEST`-style lines (`<hash>  <filename>`),
    bare-hash `.sha256/.sha512` files with no filename and Electron-builder
    YAML manifests with base64-encoded SHA512 hashes.

    Args:
        content: The text of the checksum file.
        target_name: The name of the AppImage file to match against.
        checksum_filename: The downloaded checksum filename, used to select
            YAML parsing for Electron-builder manifests.

    Returns:
        The hash string if found, or None if not found or unparseable.
        Caller records CHECKSUM_FILE_CORRUPT as a warning if None is returned.
    """
    if checksum_filename and checksum_filename.lower().endswith(
        (".yml", ".yaml")
    ):
        return _parse_latest_linux_yml(content, target_name)

    # Split the content into lines, stripping whitespace, ignoring empty lines.
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    # If the checksum file is a single bare hash with no filename, return it.
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

    # If the checksum file contains multiple lines,
    # parse each line for a hash and filename.
    for line in lines:
        match = _CHECKSUM_LINE_RE.match(line)
        if not match:
            logger.warning("Checksum file line is unparseable: %s", line)
            continue

        logger.debug("Checksum file line parsed: %s", line)

        # Extract the hash and filename from the matched groups.
        hash_value, filename = match.groups()
        filename = filename.strip()

        # Determine the hash type based on its length and log accordingly.
        if len(hash_value) == 64:
            logger.debug(
                "Checksum file line is a SHA256 hash for target: %s -> %s",
                filename,
                hash_value,
            )
        if len(hash_value) == 128:
            logger.debug(
                "Checksum file line is a SHA512 hash for target: %s -> %s",
                filename,
                hash_value,
            )

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


def _compute_file_hash(path: Path, algorithm: str) -> str:
    """Compute the hash of a local file.

    This is the *actual* hash of the downloaded AppImage, to be compared
    against an *expected* hash taken from the GitHub API digest or a
    checksum file. It does not read either of those sources.

    Args:
        path: The file to hash (the downloaded AppImage).
        algorithm: A hashlib algorithm name, e.g. "sha256" or "sha512".

    Returns:
        The hash as a lowercase hex string.
    """
    logger.debug("Computing %s for file: %s", algorithm, path)

    # open the file in binary mode and compute its hash using
    # the specified algorithm
    with path.open("rb") as fh:
        # use hashlib.file_digest to compute the hash of the file
        # this is more efficient than reading the file in chunks manually
        # it returns a hash object, so we call hexdigest() to get the hex string
        # it also automatically handles large files without loading them
        # entirely into memory by reading them in chunks
        return hashlib.file_digest(fh, algorithm).hexdigest()


def _check_hash(
    method: str,
    appimage_path: Path,
    expected_hash: str,
    source_file: str | None = None,
) -> ChecksumResult | None:
    """Hash the AppImage and compare it against an expected hash.

    The algorithm is inferred from the length of expected_hash.

    Args:
        method: Label for where expected_hash came from
            ("digest" or "checksum_file").
        appimage_path: The path to the downloaded AppImage.
        expected_hash: The hash claimed by upstream (SHA256 or SHA512 hex).
        source_file: The checksum file the hash was read from, if any.

    Returns:
        A ChecksumResult with status VERIFIED or FAILED, or None if
        expected_hash has an unsupported length.
    """
    # Determine the hashing algorithm based on the length of the expected hash.
    algorithm = _HASH_ALGORITHM_BY_LENGTH.get(len(expected_hash))

    if algorithm is None:
        logger.warning(
            "Unexpected hash length %d from %s", len(expected_hash), method
        )
        return None

    # Compute the actual hash of the AppImage file using the determined algorithm
    actual_hash = _compute_file_hash(appimage_path, algorithm)
    status = (
        VerificationStatus.VERIFIED
        if actual_hash.lower() == expected_hash.lower()
        else VerificationStatus.FAILED
    )

    return ChecksumResult(
        status=status,
        method=method,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
        source_file=source_file,
    )


def _check_digest(
    appimage_path: Path, digest: str | None
) -> ChecksumResult | None:
    """Verify the AppImage against the GitHub API embedded digest.

    Args:
        appimage_path: The path to the downloaded AppImage.
        digest: The hex digest from the GitHub API, or None if not provided.

    Returns:
        A ChecksumResult (VERIFIED or FAILED), or None if there is no
        usable digest.
    """
    if not digest:
        return None

    logger.debug("Checking embedded digest: %s", digest)
    return _check_hash("digest", appimage_path, digest)


def _check_checksum_file(
    appimage_path: Path, checksum_path: Path | None, package: str
) -> tuple[ChecksumResult | None, list[PackageWarning]]:
    """Verify the AppImage against a downloaded checksum file.

    A missing checksum file is a normal outcome and yields no result and
    no warning. A file that is present but unparseable or unusable yields
    no result and a CHECKSUM_FILE_CORRUPT warning (a data-quality problem,
    not a verification failure; see AGENTS.md §6.2).

    Args:
        appimage_path: The path to the downloaded AppImage.
        checksum_path: The path to the downloaded checksum file, or None.
        package: The package label used in warnings.

    Returns:
        A tuple of (ChecksumResult or None, list of PackageWarning).
    """
    # If the checksum file is not present, return None and no warnings.
    # We don't return any MISSING status here because that's handled
    # by the _summarize function, which aggregates results from both the digest
    # and checksum file checks.
    if checksum_path is None:
        return None, []

    logger.debug("Parsing checksum file: %s", checksum_path)

    try:
        content = checksum_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "Checksum file is unreadable: %s, error: %s", checksum_path, exc
        )
        return None, [
            PackageWarning(
                package=package,
                stage=Stage.VERIFY.value,
                code=WarningCode.CHECKSUM_FILE_CORRUPT,
            )
        ]

    expected_hash = _parse_checksum_file(
        content, appimage_path.name, checksum_path.name
    )

    # If the checksum file is present and got parsed, than compare the hash
    # with using _check_hash.
    # If length not 64 or 128, _check_hash would return None.
    result = (
        _check_hash(
            "checksum_file",
            appimage_path,
            expected_hash,
            source_file=str(checksum_path),
        )
        if expected_hash
        else None
    )

    # If the result is None, it means the checksum file was corrupt
    # or unreadable or the hash length was unexpected
    if result is None:
        logger.warning(
            "Checksum file is corrupt or unreadable: %s", checksum_path
        )
        return None, [
            PackageWarning(
                package=package,
                stage=Stage.VERIFY.value,
                code=WarningCode.CHECKSUM_FILE_CORRUPT,
            )
        ]

    # If the result is not None, it means the checksum file was parsed and
    # the hash was checked, so return the result and no warnings.
    return result, []


def _summarize(results: list[ChecksumResult]) -> ChecksumResult:
    """Combine per-method results into the final verification result.

    A real mismatch always wins (AGENTS.md §8.2): the first failed result
    is returned as-is, so its method, expected and actual hash stay
    coherent. Otherwise, all passing methods are merged, with hashes taken
    from the first (digest is listed before checksum file).

    Args:
        results: Per-method results (VERIFIED or FAILED), in priority order.

    Returns:
        The aggregate ChecksumResult: FAILED, VERIFIED, or MISSING when no
        method produced a result.
    """
    # give me the first item that matches failed status, or None
    # if there is no such item, then failed will be None
    failed = next(
        (r for r in results if r.status is VerificationStatus.FAILED), None
    )

    # If there is a failed result, return it immediately. This ensures that
    # the first failed result is prioritized over any passing results.
    if failed is not None:
        return failed

    # If there are no failed results, check if there are any passing results.
    # If there are no passing results, return a MISSING status.
    if not results:
        return ChecksumResult(status=VerificationStatus.MISSING)

    # If there are passing results, collect their methods for logging/debugging
    # and for the final ChecksumResult.
    # methods kept as list of strings, e.g. ["digest", "checksum_file"]
    methods = [r.method for r in results if r.method]

    # If there are passing results, merge them into a single ChecksumResult.
    # The method field is a concatenation of all passing methods, and the
    # expected and actual hashes are taken from the first passing result.
    return ChecksumResult(
        status=VerificationStatus.VERIFIED,
        # method: e.g "digest+checksum_file" if both methods passed
        method="+".join(methods),
        expected_hash=results[0].expected_hash,
        actual_hash=results[0].actual_hash,
        # source_file: the first source file that was used to verify the AppImage
        # If no source file is available, use None.
        source_file=next(
            (r.source_file for r in results if r.source_file), None
        ),
    )


def verify_downloaded_appimage(
    appimage_path: Path,
    appimage_asset: Asset,
    checksum_path: Path | None,
) -> tuple[ChecksumResult, list[PackageWarning]]:
    """Resolve verification status.

    Both the embedded digest (if the API gave one) and the checksum file
    (if downloaded) are checked independently. A real mismatch on either
    always wins over a pass on the other; corruption of the checksum file
    is a warning, not a failure, and doesn't mask a passing digest.

    Args:
        appimage_path: The path to the downloaded AppImage.
        appimage_asset: The Asset object for the AppImage.
        checksum_path: The path to the downloaded checksum file, or None if
            not present.

    Returns:
        A tuple of (ChecksumResult, list of PackageWarning).
    """
    logger.debug(
        "Verifying downloaded AppImage: %s, checksum file: %s",
        appimage_path,
        checksum_path,
    )
    # 1. Check the embedded digest from the GitHub API (if present).
    digest_result = _check_digest(appimage_path, appimage_asset.digest)

    # 2. Check the downloaded checksum file (if present).
    checksum_file_result, warnings = _check_checksum_file(
        appimage_path, checksum_path, appimage_asset.name
    )

    # Get all non-None results from the digest and checksum file checks.
    # The order is always digest first, then checksum file
    results = [
        r for r in (digest_result, checksum_file_result) if r is not None
    ]

    # Summarize the results into a single ChecksumResult, which will be
    # VERIFIED if all methods passed, FAILED if any method failed,
    # or MISSING if no methods produced a result.
    result = _summarize(results)
    logger.debug("Verification result: %s", result)

    return result, warnings

""" "Filesystem operations for AppImageManager."""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from .constants import APPIMAGES_DIR
from .models import ErrorCode, ErrorKind, PackageError, Stage

if TYPE_CHECKING:
    from pathlib import Path


logger = logging.getLogger(__name__)


# TODO: add renaming function after appstate/catalog supported
# with that, we need to rename appimages that name has version in it.
# TODO: after naming, chmod +x before moving
# after than move to appimages dir
# TODO: add support for .desktop creation after
# TODO: add support for icon creation after


def make_executable(src_path: Path, package: str) -> PackageError | None:
    """Make the AppImage executable.

    Args:
        src_path: The source path of the AppImage.
        package: The name of the package (used for logging).

    Returns:
        None if successful, or a PackageError if the operation fails.
    """
    try:
        src_path.chmod(src_path.stat().st_mode | 0o111)
        logger.debug("Made AppImage executable: %s", src_path)
    except PermissionError as e:
        logger.error(
            "Permission denied while making AppImage executable: %s", e
        )
        return PackageError(
            package=package,
            code=ErrorCode.PERMISSION_DENIED,
            kind=ErrorKind.FILESYSTEM,
            stage=Stage.INSTALL.value,
        )
    except OSError as e:
        logger.error("OS error while making AppImage executable: %s", e)
        return PackageError(
            package=package,
            code=ErrorCode.FILESYSTEM_CHMOD_ERROR,
            kind=ErrorKind.FILESYSTEM,
            stage=Stage.INSTALL.value,
        )

    return None


def move_verified_appimage(
    src_path: Path, owner: str, package: str
) -> Path | PackageError:
    """Move a verified AppImage to the APPIMAGES_DIR.

    Args:
        src_path: The source path of the verified AppImage.
        owner: The owner of the AppImage.
        package: The name of the package (used for logging).

    Returns:
        The destination path of the moved AppImage, or a PackageError if
        the move operation fails.
    """
    dest = APPIMAGES_DIR / owner / f"{package}.AppImage"

    executable_error = make_executable(src_path, package)
    if executable_error is not None:
        return executable_error

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest))
        logger.debug("Moved AppImage to: %s", dest)
    except PermissionError as e:
        logger.error("Permission denied while moving AppImage: %s", e)
        return PackageError(
            package=package,
            code=ErrorCode.PERMISSION_DENIED,
            kind=ErrorKind.FILESYSTEM,
            stage=Stage.INSTALL.value,
        )
    except OSError as e:
        logger.error("OS error while moving AppImage: %s", e)
        return PackageError(
            package=package,
            code=ErrorCode.FILESYSTEM_MOVE_ERROR,
            kind=ErrorKind.FILESYSTEM,
            stage=Stage.INSTALL.value,
        )

    return dest

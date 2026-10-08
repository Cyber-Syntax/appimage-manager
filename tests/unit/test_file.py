from pathlib import Path
from unittest.mock import patch

from appman.file import make_executable, move_verified_appimage
from appman.models import ErrorCode, ErrorKind, PackageError, Stage


def test_move_verified_appimages_moves_file_to_persistent_dir(
    tmp_path: Path,
) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    dest_path = tmp_path / "appimages"

    with patch("appman.file.APPIMAGES_DIR", dest_path):
        result = move_verified_appimage(src, "pbek", "QOwnNotes")

    dest = dest_path / "pbek" / "QOwnNotes.AppImage"

    assert result == dest
    assert dest.read_bytes() == b"fake content"
    assert not src.exists()  # Ensure the source file has been moved
    # Check if the file is executable (owner, group, others)
    assert dest.stat().st_mode & 0o111 == 0o111


def test_move_verified_appimages_returns_permission_error(
    tmp_path: Path,
) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    with (
        patch("appman.file.APPIMAGES_DIR", tmp_path / "appimages"),
        patch("appman.file.shutil.move", side_effect=PermissionError),
    ):
        result = move_verified_appimage(src, "pbek", "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.PERMISSION_DENIED
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value


def test_move_verified_appimage_returns_move_error(tmp_path: Path) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    with (
        patch("appman.file.APPIMAGES_DIR", tmp_path / "appimages"),
        patch("appman.file.shutil.move", side_effect=OSError),
    ):
        result = move_verified_appimage(src, "pbek", "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.FILESYSTEM_MOVE_ERROR
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value


def test_move_verified_appimage_returns_executable_error(
    tmp_path: Path,
) -> None:
    src = tmp_path / "cache" / "QOwnNotes.AppImage"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"fake content")

    with patch(
        "appman.file.make_executable",
        return_value=PackageError(
            package="QOwnNotes",
            code=ErrorCode.FILESYSTEM_CHMOD_ERROR,
            kind=ErrorKind.FILESYSTEM,
            stage=Stage.INSTALL.value,
        ),
    ):
        result = move_verified_appimage(src, "pbek", "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.FILESYSTEM_CHMOD_ERROR
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value


def test_make_executable_returns_permission_error(tmp_path: Path) -> None:
    appimage_path = tmp_path / "QOwnNotes.AppImage"
    appimage_path.write_bytes(b"fake content")

    with patch("pathlib.Path.chmod", side_effect=PermissionError):
        result = make_executable(appimage_path, "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.PERMISSION_DENIED
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value


def test_make_executable_returns_os_error(tmp_path: Path) -> None:
    appimage_path = tmp_path / "QOwnNotes.AppImage"
    appimage_path.write_bytes(b"fake content")

    with patch("pathlib.Path.chmod", side_effect=OSError):
        result = make_executable(appimage_path, "QOwnNotes")

    assert isinstance(result, PackageError)
    assert result.package == "QOwnNotes"
    assert result.code == ErrorCode.FILESYSTEM_CHMOD_ERROR
    assert result.kind == ErrorKind.FILESYSTEM
    assert result.stage == Stage.INSTALL.value

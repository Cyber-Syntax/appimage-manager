"""Unit test for config module.

How pytest handles:
    Setup phase: When a test requests the patched_constants fixture, pytest calls the fixture function. The code runs up to the yield statement. During this phase, the with block is entered, and the patching is applied. At the yield, the fixture pauses and returns the object mock_dirs to the test.

    Test execution: The test receives the mock_dirs dictionary (the same dictionary that was created by the mock_dirs fixture). The test can use these mocks if needed. All code inside the test that references appman.config.CONFIG_DIR will see the mock, not the real path.

    Teardown phase: After the test finishes (successfully or with an error), pytest resumes the fixture function immediately after the yield. The with block exits, causing patch.multiple to restore all the original constants. The fixture then ends.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from appman.config import init_config

# ruff: noqa: ERA001


@pytest.fixture
def mock_dirs() -> dict[str, MagicMock]:
    """Provide fake Path mocks standing in for the seven XDG dir."""
    names = [
        "config",
        "log",
        "data",
        "appimages",
        "catalog",
        "cache",
        "backup",
    ]

    # return one dict in seven key-value pairs
    # Example:
    # {
    #     "config":    <MagicMock spec='Path' id=140123456789>,
    #     "log":       <MagicMock spec='Path' id=140123456790>,
    #     "data":      <MagicMock spec='Path' id=140123456791>,
    #     "appimages": <MagicMock spec='Path' id=140123456792>,
    #     "catalog":   <MagicMock spec='Path' id=140123456793>,
    #     "cache":     <MagicMock spec='Path' id=140123456794>
    #     "backup":    <MagicMock spec='Path' id=140123456795>
    # }
    return {name: MagicMock(spec=Path) for name in names}


@pytest.fixture
def patched_constants(mock_dirs: dict[str, MagicMock]):
    """Patch the module-level real XDG dir constants used by init_config."""
    with patch.multiple(
        "appman.config",
        CONFIG_DIR=mock_dirs["config"],
        LOG_DIR=mock_dirs["log"],
        DATA_DIR=mock_dirs["data"],
        APPIMAGES_DIR=mock_dirs["appimages"],
        CATALOG_DIR=mock_dirs["catalog"],
        CACHE_DIR=mock_dirs["cache"],
        BACKUP_DIR=mock_dirs["backup"],
    ):
        # return all the seven key-value pairs
        # pause here, keep patched with block open
        yield mock_dirs

    # after test, execution resume here, then exits the with block


def test_init_config_creates_each_missing_directory(patched_constants):
    """All seven dirs are missing -> mkdir is called once per dir."""

    # Set up the mock Path objects to simulate that all directories are missing
    for mock_dir in patched_constants.values():
        mock_dir.exists.return_value = False

    # Call the function under test
    init_config()

    # Assert that mkdir was called once for each directory with the correct arg
    for mock_dir in patched_constants.values():
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_init_config_logs_info_directory_is_created(patched_constants, caplog):
    """A missing dir logs an INFO 'Created directory' message."""
    for mock_dir in patched_constants.values():
        mock_dir.exists.return_value = False

    with caplog.at_level(logging.INFO, logger="appman.config"):
        init_config()

    assert any("Created directory" in r.message for r in caplog.records)


def test_init_config_does_not_log_created_when_directory_already_exist(
    patched_constants, caplog
):
    """An already-existing dir does not log 'created directory'."""
    for mock_dir in patched_constants.values():
        mock_dir.exists.return_value = True

    with caplog.at_level(logging.INFO, logger="appman.config"):
        init_config()

    assert not any("Created directory" in r.message for r in caplog.records)


def test_init_config_still_calls_mkdir_when_directory_already_exists(
    patched_constants,
):
    """mkdir(exist_ok=True) is still called even for pre-exist dirs"""
    for mock_dir in patched_constants.values():
        mock_dir.exists.return_value = True

    init_config()

    for mock_dir in patched_constants.values():
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_init_config_raises_oserror_when_mkdir_fails(patched_constants):
    """Mkdir failure (e.g permission denied) raises OSError."""
    target = patched_constants["config"]
    target.exists.return_value = False
    target.mkdir.side_effect = OSError("permission denied")

    with pytest.raises(OSError, match="permission denied"):
        init_config()


def test_init_config_logs_exception_before_reraising(
    patched_constants, caplog
):
    """A failed mkdir is logged at ERROR level before the OSError raises."""
    target = patched_constants["cache"]
    target.exists.return_value = False
    target.mkdir.side_effect = OSError("disk full")

    with caplog.at_level(logging.ERROR, logger="appman.config"):
        with pytest.raises(OSError):
            init_config()

    assert any(
        "Failed to create directory" in r.message for r in caplog.records
    )

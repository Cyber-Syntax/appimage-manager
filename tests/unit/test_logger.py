from __future__ import annotations

import logging
from collections.abc import Generator
from logging import Logger, StreamHandler
from logging.handlers import RotatingFileHandler
from typing import Any
from unittest.mock import patch

import pytest

from appman.logger import init_console_log, init_file_log


@pytest.fixture
def configured_logger(log_file, clean_appman_logger: Logger) -> Logger:
    """Fixture to provide a logger configured with console and file handlers.

    Args:
        log_file: Temporary log file path.
        clean_appman_logger: Cleaned 'appman' logger fixture.

    Returns:
        Configured 'appman' logger.
    """
    init_console_log()
    init_file_log()
    return clean_appman_logger


@pytest.fixture(autouse=True)
def clean_appman_logger() -> Generator[Logger, None, None]:
    """Reset the 'appman' logger's handlers before and after each test.

    This ensures that each test starts with a clean logger state, preventing
    any interference between tests.

    The logger is a module-level singleton, so tests must not leak
    handlers into one another (independence requirement).
    """
    # Save the original handlers and level
    logger = logging.getLogger("appman")
    original_handlers = list(logger.handlers)
    original_level = logger.level

    # Remove all existing handlers from the logger
    for handler in original_handlers:
        logger.removeHandler(handler)

    # yield: pause here, let the test run with a clean logger
    yield logger

    # Teardown phase: After the test finishes (successfully or with an error),
    # pytest resumes the fixture function immediately after the yield.
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    # Restore the original handlers
    for handler in original_handlers:
        logger.addHandler(handler)

    # Restore the original logging level
    logger.setLevel(original_level)


@pytest.fixture
def log_file(tmp_path):
    """Patch LOG_FILE to a temp path so no real log file is touched.

    Args:
        tmp_path: temporary path
    """
    path = tmp_path / "main.log"

    # Patch LOG_FILE to a temporary path so no real log file is touched.
    with patch("appman.logger.LOG_FILE", path):
        # The with block ensures that the patch is active only within this context.
        yield path


def _file_handler(logger: logging.Logger) -> RotatingFileHandler:
    """Get RotatingFileHandler.

    generator expression (inside parenthesis): go through each handler
    `h`, only keep the ones that are a RotatingFileHandler.
    next(): give me the first one of those

    Args:
        logger: logging.Logger

    Returns:
        RotatingFileHandler
    """
    return next(
        h for h in logger.handlers if isinstance(h, RotatingFileHandler)
    )


def _console_handler(logger: logging.Logger) -> StreamHandler[Any]:
    """Get console handler.

    generator expression (inside parenthesis): go through each handler
    `h`, only keep the ones that are a StreamHandler but not a RotatingFileHandler.
    next(): give me the first one of those

    Args:
        logger: logging.Logger

    Returns:
        logging.StreamHandler
    """
    return next(
        h
        for h in logger.handlers
        if isinstance(h, StreamHandler)
        and not isinstance(h, RotatingFileHandler)
    )


def test_init_log_attaches_exactly_two_handlers(configured_logger):
    """Exactly one file handler and one console handler are attached.

    Args:
        configured_logger: Logger with console and file handlers.
    """
    init_console_log()
    init_file_log()

    assert len(configured_logger.handlers) == 2


def test_init_log_file_handler_is_rotating(configured_logger):
    """The file handler is a RotatingFileHandler, not a plain FileHandler."""
    init_console_log()
    init_file_log()

    assert isinstance(_file_handler(configured_logger), RotatingFileHandler)


def test_init_log_file_handler_uses_configured_rotation_limits(
    configured_logger,
):
    """Rotating is capped at 1MB with 5 backups, per the module's documented contract."""
    init_console_log()
    init_file_log()

    fh = _file_handler(configured_logger)
    assert fh.maxBytes == 1_000_000
    assert fh.backupCount == 5


def test_init_log_file_handler_captures_debug_level(configured_logger):
    """The file handler is set to DEBUG so it captures everything."""
    init_console_log()
    init_file_log()

    assert _file_handler(configured_logger).level == logging.DEBUG


def test_init_log_console_handler_only_shows_info_and_above(configured_logger):
    """The console handler is set to INFO so DEBUG noise stays out of the terminal."""
    init_console_log()
    init_file_log()

    assert _console_handler(configured_logger).level == logging.INFO


def test_init_log_creates_log_file_at_configured_path(
    log_file, configured_logger
):
    """init_log() eageryl opens the log file at the patched LOG_FILE path."""
    init_console_log()
    init_file_log()

    assert log_file.exists()


def test_init_console_log_is_idempotent(
    clean_appman_logger: Logger,
) -> None:
    init_console_log()
    init_console_log()

    console_handlers = [
        handler
        for handler in clean_appman_logger.handlers
        if isinstance(handler, StreamHandler)
        and not isinstance(handler, RotatingFileHandler)
    ]

    assert len(console_handlers) == 1


def test_init_file_log_is_idempotent(
    log_file,
    clean_appman_logger: Logger,
) -> None:
    init_file_log()
    first_handler = _file_handler(clean_appman_logger)

    init_file_log()

    file_handlers = [
        handler
        for handler in clean_appman_logger.handlers
        if isinstance(handler, RotatingFileHandler)
    ]

    assert len(file_handlers) == 1
    assert file_handlers[0] is not first_handler
    assert first_handler.stream is None

"""Unit tets for appman.main -- top-level CLI entrypoint orchestration.

main.py's only job is to wire together config/log setup, argument parsing,
and dispatch to whichever subcommand's 'func' argsparse resolved. All
collaborators (init_config, init_log...) are mocked here -- this module's
own control flow (call order, and the func-vs-no-func branch) is what's
under test, not cli.py/config.py/logger.py themselves.
"""

from __future__ import annotations

import argparse
import logging
from unittest.mock import MagicMock, call, patch

import pytest

from appman.main import main


@pytest.fixture
def fake_parser() -> MagicMock:
    """stand-in for the argsparse.ArgumentParser returned by create_parser().

    A bare MagicMock is enough: main.py only ever passes this straight into
    parse_args(), and on the no-func path, calls .print_help() on it. It
    never inspects the parser's internals.
    """
    return MagicMock(name="argsparse.ArgumentParser")


def test_main_dispatches_to_args_func_when_present(
    fake_parser: MagicMock,
) -> None:
    """When parsed args carry a `func` (a subcommand was chosen), main()
    must call it with args itself as the argument — this is how cli.py's
    install_cmd (and future update_cmd, remove_cmd, ...) actually get
    invoked.
    """
    mock_func = MagicMock(name="install_cmd")
    # argparse.Namespace, not MagicMock: hasattr() on a MagicMock is always
    # True (it auto-creates attributes on access), so a MagicMock can't be
    # used to simulate "func is missing". Namespace only has what's
    # explicitly set on it, so hasattr() behaves like the real object.
    fake_args = argparse.Namespace(command="install", func=mock_func)

    with (
        patch("appman.main.init_config") as mock_init_config,
        patch("appman.main.init_log") as mock_init_log,
        patch("appman.main.create_parser", return_value=fake_parser),
        patch(
            "appman.main.parse_args", return_value=fake_args
        ) as mock_parse_args,
        patch("appman.main.sys.exit") as mock_exit,
    ):
        main()

    # assert_called_once_with() used here because that call it without arg
    # currently, we call it without it which that's why it is used instead
    # of assert_called_once() which that isn't check without arg.
    mock_init_config.assert_called_once_with()
    mock_init_log.assert_called_once_with()
    mock_parse_args.assert_called_once_with(fake_parser)
    mock_func.assert_called_once_with(fake_args)
    mock_exit.assert_not_called()


def test_main_runs_setup_before_parsing_before_dispatch(
    fake_parser: MagicMock,
) -> None:
    """Locks in the required sequence: config/log setup must happen before
    parsing, and parsing must happen before dispatch. A regression that
    reordered these (e.g. parsing args before CONFIG_DIR exists) could
    silently break a command that reads config during arg validation.
    """
    manager = MagicMock()
    mock_func = MagicMock(name="install_cmd")
    fake_args = argparse.Namespace(func=mock_func)
    manager.create_parser.return_value = fake_parser
    manager.parse_args.return_value = fake_args

    with (
        patch("appman.main.init_config", manager.init_config),
        patch("appman.main.init_log", manager.init_log),
        patch("appman.main.create_parser", manager.create_parser),
        patch("appman.main.parse_args", manager.parse_args),
    ):
        main()

    # testing that all those func called in order from top to bottom
    assert manager.mock_calls[:4] == [
        call.init_config(),
        call.init_log(),
        call.create_parser(),
        call.parse_args(fake_parser),
    ]


# no-func path: no subcommand chosen


def test_main_exits_1_and_prints_help_when_no_func(
    fake_parser: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Running bare `appman` (no subcommand) must print the help text and
    exit(1) — never fall through silently, and never crash trying to call
    `.func` on args that don't have one.
    """
    fake_args = argparse.Namespace(command=None)  # no "func" attributes set

    with (
        patch("appman.main.init_config") as mock_init_config,
        patch("appman.main.init_log") as mock_init_log,
        patch("appman.main.create_parser", return_value=fake_parser),
        patch("appman.main.parse_args", return_value=fake_args),
        caplog.at_level(logging.ERROR, logger="appman.main"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1
    fake_parser.print_help.assert_called_once_with()
    assert "no command provided" in caplog.text.lower()

    # both must run even when no subcommand was given
    mock_init_config.assert_called_once()
    mock_init_log.assert_called_once()


def test_main_does_not_swallow_init_config_failure() -> None:
    """config.py's init_config() deliberately re-raises on directory-creation
    failure (see config.py's `raise` after logger.error). main() must not
    catch and hide that — a broken XDG setup should surface as a real
    crash, not silently continue into parsing with missing directories.
    """
    with (
        patch(
            "appman.main.init_config", side_effect=OSError("permission denied")
        ),
        patch("appman.main.init_log") as mock_init_log,
    ):
        with pytest.raises(OSError, match="permission denied"):
            main()

    mock_init_log.assert_not_called()  # never reached -- proves short-circuit


def test_main_does_not_swallow_dispatched_command_failure(
    fake_parser: MagicMock,
) -> None:
    """install() (reached via args.func) raises SystemExit(1) on partial
    failure per its own contract. main() must let that propagate untouched
    rather than catching it and returning normally — the CLI's exit code
    contract depends on this bubbling all the way up to the shell.
    """
    mock_func = MagicMock(side_effect=SystemExit(1))
    fake_args = argparse.Namespace(func=mock_func)

    with (
        patch("appman.main.init_config"),
        patch("appman.main.init_log"),
        patch("appman.main.create_parser", return_value=fake_parser),
        patch("appman.main.parse_args", return_value=fake_args),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

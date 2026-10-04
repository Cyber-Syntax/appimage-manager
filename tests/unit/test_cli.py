from argparse import Namespace
from unittest.mock import Mock

import pytest

from appman import cli
from appman.cli import create_parser


def test_install_empty_urls_is_noop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI rejects install without URLs with argparse exit code 2."""
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["install"])  # no URLs

    assert exc_info.value.code == 2
    assert (
        "the following arguments are required: URLs" in capsys.readouterr().err
    )


def test_install_cmd_passes_urls_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI passes the URLs to the install function."""
    install_mock = Mock()
    monkeypatch.setattr(cli, "install", install_mock)

    args = Namespace(urls=["https://github.com/pbek/QOwnNotes"])
    cli.install_cmd(args)

    install_mock.assert_called_once_with(args.urls)


def test_parse_args_returns_parser_arguments() -> None:
    """The CLI parse_args function returns the correct parser arguments."""
    expected = Namespace(
        command="install", urls=["https://github.com/pbek/QOwnNotes"]
    )
    parser = Mock()
    parser.parse_args.return_value = expected

    result = cli.parse_args(parser)

    assert result is expected
    parser.parse_args.assert_called_once_with()

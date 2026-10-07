import importlib
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import appman


def test_version_uses_installed_package_metadata() -> None:
    try:
        with patch("importlib.metadata.version", return_value="1.2.3"):
            module = importlib.reload(appman)

        assert module.__version__ == "1.2.3"
    # prevent module states from leaking into other tests
    # this restore both appman.__version__ and the imported appman.version
    # binding using real package metadata
    finally:
        importlib.reload(appman)


def test_version_falls_back_when_package_is_not_installed() -> None:
    with patch(
        "importlib.metadata.version",
        side_effect=PackageNotFoundError,
    ):
        module = importlib.reload(appman)

    assert module.__version__ == "0+unknown"

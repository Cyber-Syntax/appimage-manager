import importlib
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import appman


def test_version_uses_installed_package_metadata() -> None:
    with patch("importlib.metadata.version", return_value="1.2.3"):
        module = importlib.reload(appman)

    assert module.__version__ == "1.2.3"


def test_version_falls_back_when_package_is_not_installed() -> None:
    with patch(
        "importlib.metadata.version",
        side_effect=PackageNotFoundError,
    ):
        module = importlib.reload(appman)

    assert module.__version__ == "0+unknown"

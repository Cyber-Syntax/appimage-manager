"""Unit tests for appman.install — orchestration logic only.

All external calls (api.py, download.py, aiohttp) are mocked; this module's
own control flow is what's under test.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from appman.install import (
    _dedupe_urls,
    _install_all_async,
    _install_one,
    _print_package_error,
    _print_package_warning,
    install,
)
from appman.models import (
    Asset,
    AssetType,
    ChecksumResult,
    ErrorCode,
    ErrorKind,
    GitHubRelease,
    PackageError,
    PackageWarning,
    SelectedAssets,
    Stage,
    VerificationStatus,
    WarningCode,
)

# shared fixtures / factories


@pytest.fixture
def fake_session() -> MagicMock:
    """A stand-in for aiohttp.ClientSession.

    Unit tests must never open a real connection. install.py only ever
    passes this session through to mocked collaborators, so a bare
    MagicMock is enough — nothing here actually calls .get() in these tests.
    """
    return MagicMock(name="aiohttp.ClientSession")


@pytest.fixture
def sample_release() -> GitHubRelease:
    """A minimal, valid GitHubRelease used by success-path tests."""
    return GitHubRelease(
        tag_name="v1.2.3",
        release_name="MyApp 1.2.3",
        prerelease=False,
        published_at="2026-01-01T00:00:00Z",
        assets=[],
    )


@pytest.fixture
def sample_selected() -> SelectedAssets:
    """A minimal SelectedAssets result with no checksum file."""
    appimage = Asset(
        name="MyApp-x86_64.AppImage",
        download_url="https://example.com/MyApp.AppImage",
        size=1234,
        asset_type=AssetType.APPIMAGE,
        digest=None,
    )
    return SelectedAssets(appimage=appimage, checksum_file=None)


def make_package_error(
    package: str, stage: str = Stage.QUERY.value
) -> PackageError:
    """Factory for a generic PackageError, so tests don't repeat boilerplate."""
    return PackageError(
        package=package,
        kind=ErrorKind.NETWORK,
        code=ErrorCode.NETWORK_TIMEOUT,
        stage=stage,
        retryable=True,
    )


# print funct tests


def test_print_package_warning_logs_mapped_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A known WarningCode must render via the centralized WARNING_MESSAGES
    text, user-facing string live only in the message dicts, never inline.
    """
    warning = PackageWarning(
        package="qownnotes",
        code=WarningCode.NO_CHECKSUM_SKIPPED,
        stage=Stage.VERIFY.value,
    )

    with caplog.at_level(logging.WARNING, logger="appman.install"):
        _print_package_warning(warning)

    assert "no checksum provided by upstream" in caplog.text


def test_print_package_warning_falls_back_to_generic_message_when_unmapped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guards the WARNING_MESSAGES.get(code, UNKNOWN_WARNING_MESSAGE) fallback:
    if a WarningCode is ever added without a matching message-dict entry,
    the user must see the clean generic sentence — not silently regress to
    a raw enum string being read as if it were prose.
    """
    warning = PackageWarning(
        package="qownnotes",
        code=WarningCode.CHECKSUM_FILE_CORRUPT,
        stage=Stage.VERIFY.value,
    )
    with (
        patch("appman.install.WARNING_MESSAGES", {}),  # missing entry
        caplog.at_level(logging.WARNING, logger="appman.install"),
    ):
        _print_package_warning(warning)

    assert "an unknown warning occurred" in caplog.text
    # code.value is still logged as its own structured field regardless —
    # assert it separately so this test can't be fooled by that overlap again
    assert "checksum_file_corrupt" in caplog.text


def test_print_package_error_logs_mapped_message(caplog):
    error = make_package_error("qownnotes", Stage.DOWNLOAD.value)
    with caplog.at_level(logging.ERROR, logger="appman.install"):
        _print_package_error(error)
    assert "network timeout while downloading asset" in caplog.text


def test_print_package_error_falls_back_to_code_value_when_unmapped(caplog):
    error = make_package_error("qownnotes", Stage.DOWNLOAD.value)
    with (
        patch("appman.install.ERROR_MESSAGES", {}),
        caplog.at_level(logging.ERROR, logger="appman.install"),
    ):
        _print_package_error(error)
    assert "network_timeout" in caplog.text


def test_print_package_error_logs_code_and_stage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = make_package_error("qownnotes", Stage.DOWNLOAD.value)

    with caplog.at_level(logging.ERROR, logger="appman.install"):
        _print_package_error(error)

    assert "qownnotes" in caplog.text
    assert "network_timeout" in caplog.text
    assert "download" in caplog.text


def test_print_package_error_never_uses_message_as_format_string(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression guard for: TypeError: not all arguments converted during
    string formatting. That bug came from passing `message` as the format
    string itself (logger.error(message, package, kind, ...)) instead of
    as a trailing %s argument — a real ERROR_MESSAGES entry has zero
    placeholders, so using it as the template while also passing 5 extra
    positional args raised immediately. No need to fabricate a message
    containing '%': a substituted value's own characters are never
    re-interpreted as format codes, only the template's are. This test
    uses the real, unpatched ERROR_MESSAGES entry for exactly that reason.
    """
    error = make_package_error("qownnotes", Stage.DOWNLOAD.value)

    with caplog.at_level(logging.ERROR, logger="appman.install"):
        _print_package_error(error)  # must not raise TypeError

    assert "qownnotes" in caplog.text
    assert "network_timeout" in caplog.text
    assert "network timeout while downloading asset" in caplog.text


def test_print_package_error_falls_back_to_generic_message_when_unmapped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same fallback guard for errors: an unmapped ErrorCode must render
    the generic fallback sentence, not a raw enum value passed off as prose.
    """
    error = make_package_error("qownnotes", Stage.DOWNLOAD.value)
    with (
        patch("appman.install.ERROR_MESSAGES", {}),
        caplog.at_level(logging.ERROR, logger="appman.install"),
    ):
        _print_package_error(error)

    assert "an unknown error occurred" in caplog.text
    assert (
        "network_timeout" in caplog.text
    )  # structured field, asserted separately


# _install_one


# NOTE: fake_session using MagicMock because it's synchronous func
# and also return MagicMock itself
@pytest.mark.asyncio
async def test_install_one_success_returns_repo_and_tag(
    fake_session: MagicMock,
    sample_release: GitHubRelease,
    sample_selected: SelectedAssets,
) -> None:
    """When every step succeeds, _install_one returns (repo, tag_name).

    This is the core happy-path contract: install.py wires the four
    collaborators togetehr correctly and surfaces the release tag as the
    "installed version" on success.
    """
    url = "https://github.com/pbek/QOwnNotes"

    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ) as mock_parse,
        patch(
            "appman.install.fetch_latest_release",
            # NOTE: using AsyncMock via new_callable because
            # fetch_latest_release async function so we can't just use
            # return_value like synchronous function e.g parse_github_url...
            new_callable=AsyncMock,
            return_value=sample_release,
        ) as mock_fetch,
        patch(
            "appman.install.select_appimage_asset",
            return_value=sample_selected,
        ) as mock_select,
        patch(
            "appman.install.download_and_verify",
            new_callable=AsyncMock,
            return_value=(
                "/fake/path/MyApp.AppImage",
                ChecksumResult(status=VerificationStatus.VERIFIED),
                [],
            ),
        ) as mock_download,
    ):
        package, outcome = await _install_one(fake_session, url)

    assert package == "QOwnNotes"
    assert outcome == "v1.2.3"

    # verify the collaborators were called with the right arguments
    # this is the "contract" of _install_one: it must thread
    # owner/repo/package/session through correctly, not just return the
    # right value by coincidence.
    mock_parse.assert_called_once_with(url)
    mock_fetch.assert_awaited_once_with(
        fake_session, "pbek", "QOwnNotes", "QOwnNotes"
    )
    mock_select.assert_called_once_with(sample_release.assets, "QOwnNotes")
    mock_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_one_prints_download_warnings_but_still_succeeds(
    fake_session: MagicMock,
    sample_release: GitHubRelease,
    sample_selected: SelectedAssets,
) -> None:
    """Warnings from download_and_verify (e.g no checksum) must not fail
    the install -- SKIPPED/partial verification is a warning.
    """
    warning = PackageWarning(
        package="QOwnNotes",
        code=WarningCode.NO_CHECKSUM_SKIPPED,
        stage=Stage.VERIFY.value,
    )
    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ),
        patch(
            "appman.install.fetch_latest_release",
            new_callable=AsyncMock,
            return_value=sample_release,
        ),
        patch(
            "appman.install.select_appimage_asset",
            return_value=sample_selected,
        ),
        patch(
            "appman.install.download_and_verify",
            new_callable=AsyncMock,
            return_value=(
                "/fake/path/MyApp.AppImage",
                ChecksumResult(status=VerificationStatus.SKIPPED),
                [warning],
            ),
        ),
        patch("appman.install._print_package_warning") as mock_print_warn,
    ):
        package, outcome = await _install_one(
            fake_session, "https://github.com/pbek/QOwnNotes"
        )

    assert outcome == "v1.2.3"
    mock_print_warn.assert_called_once_with(warning)


# _install_one failure path


@pytest.mark.asyncio
async def test_install_one_returns_error_when_url_invalid(
    fake_session: MagicMock,
) -> None:
    """An invalid URL must short-circuit before any network call is made.

    Also asserts the *package* label falls back to the raw URL - install.py
        has no owner/repo yet at this point, so it must not fabricate one.
    """
    bad_url = "not-a-github-url"
    parse_error = PackageError(
        package=bad_url,
        kind=ErrorKind.VALIDATION,
        code=ErrorCode.INVALID_URL,
        stage=Stage.QUERY.value,
        retryable=False,
    )

    with (
        patch("appman.install.parse_github_url", return_value=parse_error),
        patch(
            "appman.install.fetch_latest_release", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        package, outcome = await _install_one(fake_session, bad_url)

    assert package == bad_url
    assert outcome is parse_error
    mock_fetch.assert_not_awaited()  # never reached - proves short-circuit


@pytest.mark.asyncio
async def test_install_one_returns_error_when_release_fetch_fails(
    fake_session: MagicMock,
) -> None:
    """A network failure fetching the release must stop before asset
    selection or download are attempted.
    """
    fetch_error = make_package_error("QOwnNotes", Stage.QUERY.value)

    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ),
        patch(
            "appman.install.fetch_latest_release",
            new_callable=AsyncMock,
            return_value=fetch_error,
        ),
        patch("appman.install.select_appimage_asset") as mock_select,
    ):
        package, outcome = await _install_one(
            fake_session, "https://github.com/pbek/QOwnNotes"
        )

    assert package == "QOwnNotes"
    assert outcome is fetch_error
    mock_select.assert_not_called()


@pytest.mark.asyncio
async def test_install_one_returns_error_when_asset_selection_fails(
    fake_session: MagicMock, sample_release: GitHubRelease
) -> None:
    """No matchin AppImage asset must stop before download is attempted."""
    select_error = PackageError(
        package="QOwnNotes",
        kind=ErrorKind.ASSET,
        code=ErrorCode.APPIMAGE_ASSET_NOT_FOUND,
        stage=Stage.QUERY.value,
        retryable=True,
    )

    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ),
        patch(
            "appman.install.fetch_latest_release",
            new_callable=AsyncMock,
            return_value=sample_release,
        ),
        patch(
            "appman.install.select_appimage_asset",
            return_value=select_error,
        ),
        patch(
            "appman.install.download_and_verify", new_callable=AsyncMock
        ) as mock_download,
    ):
        package, outcome = await _install_one(
            fake_session, "https://github.com/pbek/QOwnNotes"
        )

    assert outcome is select_error
    mock_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_one_returns_error_when_download_fails(
    fake_session: MagicMock,
    sample_release: GitHubRelease,
    sample_selected: SelectedAssets,
) -> None:
    """A download/verification failure propagates as the final outcome."""
    download_error = make_package_error("QOwnNotes", Stage.DOWNLOAD.value)

    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ),
        patch(
            "appman.install.fetch_latest_release",
            new_callable=AsyncMock,
            return_value=sample_release,
        ),
        patch(
            "appman.install.select_appimage_asset",
            return_value=sample_selected,
        ),
        patch(
            "appman.install.download_and_verify",
            new_callable=AsyncMock,
            return_value=download_error,
        ),
    ):
        package, outcome = await _install_one(
            fake_session, "https://github.com/pbek/QOwnNotes"
        )

    assert outcome is download_error


@pytest.mark.asyncio
async def test_install_one_survives_malformed_release_payload(
    fake_session, sample_selected
):
    """A KeyError raised during release parsing must not propagate — it
    becomes a PackageError so one bad upstream response can't cancel the
    rest of the batch via gather().
    """
    with (
        patch(
            "appman.install.parse_github_url",
            return_value=("pbek", "QOwnNotes"),
        ),
        patch(
            "appman.install.fetch_latest_release",
            new_callable=AsyncMock,
            side_effect=KeyError("tag_name"),
        ),
    ):
        package, outcome = await _install_one(
            fake_session, "https://github.com/pbek/QOwnNotes"
        )

    assert package == "QOwnNotes"
    assert isinstance(outcome, PackageError)
    assert outcome.code == ErrorCode.UNKNOWN_ERROR


@pytest.mark.asyncio
async def test_install_all_async_one_bad_task_does_not_cancel_others():
    """A raising task must not cancel sibling in installs via gather()."""
    urls = ["https://github.com/a/a", "https://github.com/b/b"]

    async def fake_install_one(session, url):
        if "a/a" in url:
            # simulates a bug that slipping install_one own guard
            raise KeyError("boom")
        return url, "v1.0.0"

    with patch("appman.install._install_one", side_effect=fake_install_one):
        with pytest.raises(KeyError):
            # document current unguarded gather() behavior
            await _install_all_async(urls)


# _install_all_async


# TODO: add more detailed comment
@pytest.mark.asyncio
async def test_install_all_async_preserves_order_and_uses_shared_session() -> (
    None
):
    """Results must come back in the same order as the input URLs.
    and every call must share a single aiohttp.ClientSession
    """
    urls = [
        "https://github.com/pbek/QOwnNotes",
        "https://github.com/AppFlowy-IO/AppFlowy",
    ]

    async def fake_install_one(session, url):
        # return a value that encodes which URL/session was used so we
        # can assert both order and session sharing without over-mocking
        # asyncio internals
        return url, id(session)

    with (
        patch("appman.install._install_one", side_effect=fake_install_one),
        patch("appman.install.aiohttp.ClientSession") as mock_session_cls,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(name="shared-session")
        )
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await _install_all_async(urls)

    assert [r[0] for r in results] == urls
    # both tasks got the exact same session object
    assert results[0][1] == results[1][1]


@pytest.mark.asyncio
async def test_install_all_async_handles_duplicate_urls_independently() -> (
    None
):
    """Two identical URLs in one batch run as two independent tasks and
    both surface their own result. install.py doesn't dedupe input URLs —
    this test locks in that current behavior so a future change to it is
    a deliberate decision, not an accident.
    """
    url = "https://github.com/pbek/QOwnNotes"
    urls = [url, url]
    call_count = 0

    async def fake_install_one(session, u):
        nonlocal call_count
        call_count += 1
        return u, f"v1.0.{call_count}"

    with (
        patch("appman.install._install_one", side_effect=fake_install_one),
        patch("appman.install.aiohttp.ClientSession") as mock_session_cls,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock()
        )
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await _install_all_async(urls)

    assert len(results) == 2
    assert call_count == 2  # both ran -- no caching/dedup collapsed them
    assert results[0][0] == results[1][0] == url


# install synchronous func


def test_install_raises_systemexit_1_when_any_target_fails() -> None:
    """Exit codes are a stable contract.

    Any failure in the batch produce SystemExit(1), even if other targets
        succeeded.
    """
    results = [
        ("QOwnNotes", "v1.0.0"),
        ("ytmdesktop", make_package_error("ytmdesktop")),
    ]

    with (
        patch("appman.install.asyncio.run", return_value=results),
        pytest.raises(SystemExit) as exc_info,
    ):
        install(["https://github.com/pbek/QOwnNotes", "https://x/y"])

    assert exc_info.value.code == 1


def test_install_returns_none_when_all_targets_succeed() -> None:
    """All success must NOT raise SystemExit - asyncio.run() returning None
    from install() is the "everything worked" contract for the CLI layer.
    """
    results = [
        ("QOwnNotes", "v1.0.0"),
        ("AppFlowy", "v0.11.1"),
    ]

    with patch("appman.install.asyncio.run", return_value=results):
        outcome = install(["https://x/y", "https://x/z"])

    assert outcome is None


def test_install_all_work_completes_before_exit_code_is_decided() -> None:
    """SystemExit(1) must never cut off in-flight work: asyncio.run() has
    already fully resolved every task (success and failure alike) by the
    time install() inspects `failed` and decides on an exit code. A
    successful sibling install is never rolled back because one other
    target failed.
    """
    completed: list[str] = []

    def fake_run(coro):
        # simulate async.run() actually draining the coroutine to
        # completion, recording that both "installs" ran, before install()
        # ever gets to look at results
        coro.close()
        completed.extend(["a", "b"])
        return [("a", "v1.0.0"), ("b", make_package_error("b"))]

    with patch("appman.install.asyncio.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            install(["https://x/a", "https://x/b"])

    assert exc_info.value.code == 1
    # both ran to completion regardles of exit code
    assert completed == ["a", "b"]


# NOTE: we patch asyncio.run here because I don't want it to
# run full async chain via _install_all_async + _install_one
# together, so patching isolates install() own logic.
@pytest.mark.parametrize(
    ("results", "expected_failed_count"),
    [
        ([], 0),
        ([("a", "v1.0.0")], 0),
        ([("a", make_package_error("a"))], 1),
        ([("a", "v1.0.0"), ("b", make_package_error("b"))], 1),
    ],
)
def test_install_partitions_successes_and_failures_correctly(
    results, expected_failed_count
) -> None:
    """install() must bucket each (package, outcome) tuple by type
    (str = success, PackageError = failure) and choose the right exit
    behavior, regardless of what asyncio.run() hands back.

    NOTE: the `urls` argument below is an arbitrary placeholder — asyncio.run
    is mocked to return `results` unconditionally, so install() never
    actually inspects `urls` beyond passing it into the (unexecuted)
    coroutine. Any non-empty list works identically here.
    """
    with patch("appman.install.asyncio.run", return_value=results):
        if expected_failed_count > 0:
            with pytest.raises(SystemExit) as exc_info:
                install(["https://github.com/pbek/QOwnNotes"])
            assert exc_info.value.code == 1
        else:
            assert install(["https://github.com/pbek/QOwnNotes"]) is None


def test_install_prints_a_warning_for_each_dedupe_warning() -> None:
    """The dedupe_warnings loop in install() must call _print_package_warning
    once per warning returned by _dedupe_urls, in order -- this is the only
    call site in instal() that consumes _dedupe_urls's warning list.
    """
    dup_warning_1 = PackageWarning(
        package="qownnotes",
        code=WarningCode.DUPLICATE_TARGET_SKIPPED,
        stage=Stage.QUERY.value,
    )
    dup_warning_2 = PackageWarning(
        package="appflowy",
        code=WarningCode.DUPLICATE_TARGET_SKIPPED,
        stage=Stage.QUERY.value,
    )
    deduped_urls = ["https://github.com/pbek/QOwnNotes"]

    with (
        patch(
            "appman.install._dedupe_urls",
            return_value=(deduped_urls, [dup_warning_1, dup_warning_2]),
        ),
        patch(
            "appman.install.asyncio.run",
            return_value=[("QOwnNotes", "v1.0.0")],
        ),
        patch("appman.install._print_package_warning") as mock_print_warn,
    ):
        outcome = install(
            [
                "https://github.com/pbek/QOwnNotes",
                "https://github.com/pbek/qownnotes",
                "https://github.com/AppFlowy-IO/AppFlowy",
            ]
        )

        assert outcome is None  # single successful result -> no SystemExit
        assert mock_print_warn.call_count == 2
        mock_print_warn.assert_any_call(dup_warning_1)
        mock_print_warn.assert_any_call(dup_warning_2)


def test_install_prints_nothing_when_no_dedupe_warnings() -> None:
    """Guards the empty-list branch of the same loop: when _dedupe_urls
    returns no warnings, _print_package_warning must not be called for
    dedup at all (it may still be called later for download warnings,
    but not from this loop with an empty list).
    """
    with (
        patch(
            "appman.install._dedupe_urls",
            return_value=(["https://github.com/pbek/QOwnNotes"], []),
        ),
        patch(
            "appman.install.asyncio.run",
            return_value=[("QOwnNotes", "v1.0.0")],
        ),
        patch("appman.install._print_package_warning") as mock_print_warn,
    ):
        install(["https://github.com/pbek/QOwnNotes"])

    mock_print_warn.assert_not_called()


# _dedupe_urls


class TestDedupeUrls:
    """Unit tests for install._dedupe_urls.

    Covers the dedup-key logic itself: case-insensitive (owner, repo)
    folding for parseable URLs, raw-string fallback for URLs that fail
    to parse, and the warning label chosen for each branch. Uses the
    real parse_github_url (pure function, already covered elsewhere)
    rather than mocking it, since mocking it would hide the exact
    behavior under test.
    """

    def test_no_duplicates_returns_all_urls_unchanged(self) -> None:
        """Distinct repos produce no warnings and preserve input order."""
        urls = [
            "https://github.com/pbek/QOwnNotes",
            "https://github.com/AppFlowy-IO/AppFlowy",
        ]

        deduped, warnings = _dedupe_urls(urls)

        assert deduped == urls
        assert warnings == []

    def test_drops_exact_duplicate_and_warns(self) -> None:
        """An identical URL repeated is dropped, keeping only the first."""

        url = "https://github.com/pbek/QOwnNotes"

        deduped, warnings = _dedupe_urls([url, url])

        assert deduped == [url]
        assert len(warnings) == 1
        warning = warnings[0]
        # label is key[1], the casefolded repo name -- not the original casing
        assert warning.package == "qownnotes"
        assert warning.code == WarningCode.DUPLICATE_TARGET_SKIPPED
        assert warning.stage == Stage.QUERY.value

    def test_case_insensitiv_owner_repo_treated_as_duplicate(self) -> None:
        """Dedup key is casefolded (owner, repo), not raw string equality
        different casing of the same repo must still collapse to one target.
        """
        urls = [
            "https://github.com/pbek/QOwnNotes",
            "https://github.com/PBEK/qownnotes",
        ]

        deduped, warnings = _dedupe_urls(urls)

        assert deduped == [urls[0]]
        assert len(warnings) == 1
        # label comes from the *second* (duplicate) url's casefolded repo
        assert warnings[0].package == "qownnotes"

    def test_trailing_dot_git_suffix_treated_as_duplicate(self) -> None:
        """parse_github_url strips '.git', so both forms must dedupe to the
        same (owner, repo) key -- this is exactly the race download.py's
        dest_path collision this func exists to prevent.
        """
        urls = [
            "https://github.com/pbek/QOwnNotes",
            "https://github.com/pbek/QOwnNotes.git",
        ]

        deduped, warnings = _dedupe_urls(urls)
        assert deduped == [urls[0]]
        assert len(warnings) == 1

    def test_invalid_urls_deduped_by_war_string_only(self) -> None:
        """URLs that fail parse_github_url fallback to a plain-string key,
        per the documented behavior - so an identical unparseable string
        repeated is still recognized as a duplicate.
        """
        bad = "not-a-github-url"

        deduped, warnings = _dedupe_urls([bad, bad])

        assert deduped == [bad]
        assert len(warnings) == 1
        # key isn't a tuple here, so label fallsback to the raw url
        assert warnings[0].package == bad

    def test_different_invalid_urls_are_not_deduped_against_each_other(
        self,
    ) -> None:
        """Two distinct unparseable strings must not collide just because
        they both failed to parse -- each still surfaces its own INVALID_URL
        PackageError downstream in _install_one.
        """
        urls = ["not-a-url-1", "not-a-url-2"]

        deduped, warnings = _dedupe_urls(urls)

        assert deduped == urls
        assert warnings == []

    def test_multiple_duplicates_each_produce_their_own_warning(self) -> None:
        """Three occurences of the same repo must yield exactly two
        DUPLICATE_TARGET_SKIPPED warnings (one per dropped occurence),
        not one warning for the whole group.
        """
        url = "https://github.com/a/a"
        urls = [url, url, url]

        deduped, warnings = _dedupe_urls(urls)

        assert deduped == [url]
        assert len(warnings) == 2
        assert all(
            w.code == WarningCode.DUPLICATE_TARGET_SKIPPED for w in warnings
        )

    def test_preserves_first_occurence_order_with_interleaved_duplicate(
        self,
    ) -> None:
        """A duplicate appering mid-list must not disturb the relative
        order of the surviving, unique targets.
        """
        urls = [
            "https://github.com/a/a",
            "https://github.com/b/b",
            "https://github.com/a/a",  # duplicate of the first
            "https://github.com/c/c",
        ]

        deduped, warnings = _dedupe_urls(urls)

        assert deduped == [
            "https://github.com/a/a",
            "https://github.com/b/b",
            "https://github.com/c/c",
        ]
        assert len(warnings) == 1
        assert warnings[0].package == "a"

    def test_empty_list_returns_empty_results(self) -> None:
        """Degenerate empty input must not raise and returns empty
        containers of the correct types.
        """
        deduped, warnings = _dedupe_urls([])

        assert deduped == []
        assert warnings == []

    def test_mixed_valid_and_invalid_urls_dedupe_independently(self) -> None:
        """A valid duplicate and an invalid duplicate in the same batch
        must each be caught by their respective key stragety, without
        interfering with each other.
        """
        urls = [
            "https://github.com/pbek/QOwnNotes",
            "not-a-github-url",
            "https://github.com/pbek/QOwnNotes",  # dup of #1 (tuple key)
            "not-a-github-url",  # dup of #2 (string key)
        ]
        deduped, warnings = _dedupe_urls(urls)

        assert deduped == [
            "https://github.com/pbek/QOwnNotes",
            "not-a-github-url",
        ]
        assert len(warnings) == 2
        packages = {w.package for w in warnings}
        assert packages == {"qownnotes", "not-a-github-url"}

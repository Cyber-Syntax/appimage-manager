"""Utility functions for the appimage-manager package."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from weakref import WeakKeyDictionary

# These limits are intentionally seperate because API request
# and download have different rate limits and concurrency limits.
#
# NOTE: these cap requests *in flight at the same moment*. They do not
# track the hourly GitHub quotes.
API_CONCURRENCY = 50

# Download happen via direct url and can support 100 concurrent downloads,
# but all the github developers recommend a max of 20 concurrent downloads
# to prevent server overload and to avoid being rate limited.
DOWNLOAD_CONCURRENCY = 20


@dataclass(frozen=True, slots=True)
class ConcurrencyLimits:
    """The semaphores that cap concurrent work for one event loop.

    Example:
        limits = get_concurrency_limits()
        async with limits.api: # take an API request slot
            ...                # do the API request
        # take a api slot

        async with limits.download:
            ...                # do the download
        # The semaphores are automatically released when the "async with"
        # block exits, even if an exception is raised.

    Args:
        api: The semaphore used to limit concurrent GitHub API requests.
        download: The semaphore used to limit concurrent asset downloads.
    """

    api: asyncio.Semaphore
    download: asyncio.Semaphore


# NOTE:
# A semaphore belongs to the event loop that uses it, so we keep one
# ConcurrenyLimits per loop.
#
# WeakKeyDictionary is a dict that hold its keys "weakly": when
# a loop is no longer used anywhere else, python deletes it
# from dict automatically. A normal dict would keep every old loop
# alive forever, which would be a memory leak.
_LIMITS_BY_LOOP: WeakKeyDictionary[
    asyncio.AbstractEventLoop, ConcurrencyLimits
] = WeakKeyDictionary()


def get_concurrency_limits() -> ConcurrencyLimits:
    """Return the concurrency limits for the current running event loop.

    asyncio.run() creates a new event loop every call, and a Semaphore must
    not be reused acroos loops, so each loop gets its own limits, created
    lazily on first use.

    Returns:
        The ConcurrencyLimits (api + download semaphores) for the current
        event loop.

    Raises:
        RuntimeError: If there is no running event loop.
    """
    # Get the current running event loop. asyncio.run() creates a new loop
    # every time, so we can't use a global semaphore. Each loop gets its own.
    loop = asyncio.get_running_loop()

    # Get the limits for this loop, creating them if they don't exist yet.
    limits = _LIMITS_BY_LOOP.get(loop)

    # Create the limits for this loop if they don't exist yet.
    if limits is None:
        # Create the semaphores for this loop. The semaphore is used to limit
        # the number of concurrent API requests and downloads. The semaphore
        # is used to limit the number of concurrent API requests and downloads.
        limits = ConcurrencyLimits(
            api=asyncio.Semaphore(API_CONCURRENCY),
            download=asyncio.Semaphore(DOWNLOAD_CONCURRENCY),
        )
        # Store the limits for this loop in the weak key dictionary.
        _LIMITS_BY_LOOP[loop] = limits

    return limits

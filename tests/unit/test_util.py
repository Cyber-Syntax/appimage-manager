import asyncio
from contextlib import suppress

import pytest

from appman.util import (
    API_CONCURRENCY,
    DOWNLOAD_CONCURRENCY,
    ConcurrencyLimits,
    get_concurrency_limits,
)


@pytest.mark.asyncio
async def test_get_concurrency_limits_reuses_limits_in_same_loop() -> None:
    # ask for the limits twice in the same loop, should return the same object
    first = get_concurrency_limits()
    second = get_concurrency_limits()

    # is checks the exact same object, not just equality.
    # This is important because the semaphores
    assert first is second

    # _value is the number of currently left in semaphore
    # No one has taken any slots yet, so we expect the full amount.
    assert (
        first.api._value == API_CONCURRENCY
    )  # Initial value of the semaphore
    assert (
        first.download._value == DOWNLOAD_CONCURRENCY
    )  # Initial value of the download semaphore


@pytest.mark.asyncio
async def test_api_and_download_semaphores_are_different() -> None:
    """API and download concurrency limits use separate semaphores."""
    limits = get_concurrency_limits()

    # if both fields were the same semaphore, a busy download
    # could use up the API slots and vice versa, which is not what we want.
    # They must be different objects, even though they are both semaphores.
    assert limits.api is not limits.download


# NOTE: this test is not asnyc. It needs to create two event loops by itself
# with asnycio.run(), and you can't call asyncio.run() from inside an async
# function, so this test is synchronous.
#
# paramatrize runs this test twice, once for the "api" semaphore and
# once for the "download" semaphore.
@pytest.mark.parametrize(
    "name",
    ["api", "download"],
)
def test_semaphore_can_be_used_after_previous_loop_was_closed(
    name: str,
) -> None:
    """Each event loop must get its own usable smepahores.

    Args:
        name: The name of the semaphore to test, either "api" or "download".
    """
    # a list we fill from inside both loops, so we can compare the two
    # ConcurrencyLimits objects we got from the two loops.
    seen: list[ConcurrencyLimits] = []

    async def use_all_slots() -> None:
        """Runs in loop #1: use every slot of the semaphore, then force wait."""
        limits = get_concurrency_limits()

        # append the limits object to the list so we can compare it later
        seen.append(limits)

        # getattr(limits, "api") is the same as limits.api
        # we use it so one test body can handle both "api" and "download"
        semaphore = getattr(limits, name)

        # take every slot of the semaphore, so the next acquire() will block
        # After this loop, the box is empty.
        for _ in range(semaphore._value):
            await semaphore.acquire()

        # ask for one more slot. None are left, so this task must WAIT.
        # waiting is exactly what ties ("binds") a semaphore to loop #1.
        waiter = asyncio.create_task(semaphore.acquire())

        # sleep(0) means "pause for a moment so other tasks can run".
        # It gives `waiter` a chance to actually start and get stuck waiting.
        await asyncio.sleep(0)

        # cancel the stuck task. If we skipped this, it would wait forever
        # and the test would hang.
        waiter.cancel()

        # awaiting a cancelled task raises CancelledError. We expected that,
        # so "supress" quitely ignores it instead of failing the test.
        with suppress(asyncio.CancelledError):
            await waiter

    async def use_in_new_loop() -> None:
        """Runs in loop #2: get a new semaphore and use it, it must be usable."""
        limits = get_concurrency_limits()
        # remember loop #2 boxes so we can compare it to loop #1 boxes later
        seen.append(limits)

        semaphore = getattr(limits, name)

        # take one slot of the semaphore.
        await semaphore.acquire()

        # give it back so the semaphore is not left empty.
        semaphore.release()

    # hires the first loop #1, runs the function then loop
    # #1 is closed automatically.
    asyncio.run(use_all_slots())

    # hires the second brand new loop #2, runs the function then loop
    asyncio.run(use_in_new_loop())

    # loop #2 got a different ConcurrencyLimits object than loop #1.
    # If they were the same object, the semaphore would be tied to loop #1
    # and loop #2 would not be able to use it, which is exactly what we want to prevent.
    # This is the main point of this test: each loop must get its own usable semaphores.
    assert seen[0] is not seen[1]

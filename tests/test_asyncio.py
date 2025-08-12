import asyncio
import logging
import signal
from typing import Callable, Iterable, NoReturn, cast
from unittest import IsolatedAsyncioTestCase

from bot.utils.asyncio import run_eternal_tasks


async def _task(
    *,
    set: asyncio.Event | None = None,
    wait: asyncio.Event | None = None,
    exception: BaseException | None = None,
    cleanup: asyncio.Event | BaseException | None = None,
) -> NoReturn:
    try:
        if set is not None:
            set.set()
        if wait is not None:
            await wait.wait()
        if exception is not None:
            raise exception
    finally:
        if isinstance(cleanup, asyncio.Event):
            cleanup.set()
        elif cleanup is not None:
            raise cleanup

    # Return from a NoReturn
    cast(Callable[[], NoReturn], lambda: None)()


async def _keyboard_interrupter(*, wait: Iterable[asyncio.Event] = ()) -> None:
    for event in wait:
        await event.wait()
    signal.raise_signal(signal.SIGINT)


async def _canceller(*, wait: Iterable[asyncio.Event] = (), cancel: asyncio.Task[object]) -> None:
    for event in wait:
        await event.wait()
    cancel.cancel()


class TestPermanentTasks(IsolatedAsyncioTestCase):
    def test_reaching_normal_state(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task2_started = asyncio.Event()

        # KeyboardInterrupt does weird things to the event loop so this runs in its own loop
        with asyncio.Runner() as runner:

            async def main():
                task1 = asyncio.create_task(_task(set=task1_started, wait=never))
                task2 = asyncio.create_task(_task(set=task2_started, wait=never))

                asyncio.create_task(_keyboard_interrupter(wait=[task1_started, task2_started]))
                await run_eternal_tasks(task1, task2)

            with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
                with self.assertRaises(KeyboardInterrupt):
                    runner.run(main())

    async def test_one_of_the_tasks_finishes(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(wait=task1_started))

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(RuntimeError):
                await run_eternal_tasks(task1, task2)

        self.assertTrue(task1_cleanup.is_set())

    async def test_one_of_the_tasks_errors(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(wait=task1_started, exception=ValueError()))

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(ValueError):
                await run_eternal_tasks(task1, task2)

        self.assertTrue(task1_cleanup.is_set())

    async def test_two_tasks_error(self):
        task1_started = asyncio.Event()
        task2_started = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=task2_started, exception=ValueError()))
        task2 = asyncio.create_task(_task(set=task2_started, wait=task1_started, exception=ValueError()))

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(ExceptionGroup):
                await run_eternal_tasks(task1, task2)

    async def test_one_of_the_tasks_errors_and_cleanup_errors(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()

        task1 = asyncio.create_task(
            _task(set=task1_started, wait=task2_started, exception=ValueError(), cleanup=task1_cleanup)
        )
        task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=ValueError()))

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(ExceptionGroup):
                await run_eternal_tasks(task1, task2)

        self.assertTrue(task1_cleanup.is_set())

    async def test_one_of_the_tasks_cancelled(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()
        task2_cleanup = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=task2_cleanup))

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            asyncio.create_task(_canceller(wait=[task1_started, task2_started], cancel=task1))
            with self.assertRaises(asyncio.CancelledError):
                await run_eternal_tasks(task1, task2)

        self.assertTrue(task1_cleanup.is_set())
        self.assertTrue(task2_cleanup.is_set())

    async def test_one_of_the_tasks_cancelled_and_cleanup_errors(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=ValueError()))

        with self.assertLogs("bot.utils.asyncio", logging.ERROR):
            asyncio.create_task(_canceller(wait=[task1_started, task2_started], cancel=task1))
            with self.assertRaises(asyncio.CancelledError):
                await run_eternal_tasks(task1, task2)

        self.assertTrue(task1_cleanup.is_set())

    async def test_main_cancelled(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()
        task2_cleanup = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=task2_cleanup))

        main = asyncio.create_task(run_eternal_tasks(task1, task2))

        await _canceller(wait=[task1_started, task2_started], cancel=main)

        with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(asyncio.CancelledError):
                await main

        self.assertTrue(task1_cleanup.is_set())
        self.assertTrue(task2_cleanup.is_set())

    async def test_main_cancelled_and_cleanup_errors(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()

        task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
        task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=ValueError()))

        main = asyncio.create_task(run_eternal_tasks(task1, task2))

        await _canceller(wait=[task1_started, task2_started], cancel=main)

        with self.assertLogs("bot.utils.asyncio", logging.ERROR):
            with self.assertRaises(asyncio.CancelledError):
                await main

        self.assertTrue(task1_cleanup.is_set())

    def test_keyboardinterrupt_cleanup(self):
        never = asyncio.Event()
        task1_started = asyncio.Event()
        task1_cleanup = asyncio.Event()
        task2_started = asyncio.Event()
        task2_cleanup = asyncio.Event()

        # KeyboardInterrupt does weird things to the event loop so this runs in its own loop
        with asyncio.Runner() as runner:

            async def main():
                task1 = asyncio.create_task(_task(set=task1_started, wait=never, cleanup=task1_cleanup))
                task2 = asyncio.create_task(_task(set=task2_started, wait=never, cleanup=task2_cleanup))

                asyncio.create_task(_keyboard_interrupter(wait=[task1_started, task2_started]))
                await run_eternal_tasks(task1, task2)

            with self.assertNoLogs("bot.utils.asyncio", logging.ERROR):
                with self.assertRaises(KeyboardInterrupt):
                    runner.run(main())

        self.assertTrue(task1_cleanup.is_set())
        self.assertTrue(task2_cleanup.is_set())

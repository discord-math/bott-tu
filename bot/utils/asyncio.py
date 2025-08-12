import asyncio
import logging
from typing import NoReturn, cast


logger = logging.getLogger(__name__)


def _noreturn_task_exception(task: asyncio.Task[NoReturn], /) -> BaseException:
    # A completed NoReturn task must contain an exception. If it doesn't we make one up.
    return task.exception() or RuntimeError(f"{task!r} completed despite being marked NoReturn")


def _make_exception_group(message: str, exceptions: tuple[BaseException, ...], /) -> BaseException:
    if len(exceptions) == 1:
        raise exceptions[0]
    elif all(isinstance(exc, Exception) for exc in exceptions):
        exceptions = cast(tuple[Exception, ...], exceptions)
        raise ExceptionGroup(message, exceptions)
    else:
        raise BaseExceptionGroup(message, exceptions)


async def run_eternal_tasks(*args: asyncio.Task[NoReturn]) -> NoReturn:
    """
    Ensure the given tasks are running. If any of the tasks stops running for any reason, other tasks are cancelled.

    If the reason for the stop was an exception, we reraise it. If it was a cancel, we bubble it up. If
    run_eternal_tasks itself is cancelled, we also cancel all tasks.
    """
    try:
        cancelled_by_us: set[asyncio.Task[NoReturn]] = set()
        try:
            await asyncio.wait(args, return_when=asyncio.FIRST_COMPLETED)  # (1)
        finally:
            # We get here if (1) returned, or if it was cancelled. Either case cancel all tasks:
            for task in args:
                if task.cancel():
                    cancelled_by_us.add(task)

        # We get here if (1) returned. This means that at least one task has returned/raised, or was cancelled (not by
        # us). We have already requested cancellation of all other tasks, and now wait for them to complete:
        await asyncio.wait(args, return_when=asyncio.ALL_COMPLETED)  # (2)

        # Collect exceptions. A task we cancelled could raise during finalization, and we want to collect such
        # exceptions too. On the other hand, if we find a cancelled task that we didn't cancel, that means we should
        # bubble up a CancelledError. This is taken care of by calling task.exception(), which will raise CancelledError
        # if the task was cancelled.
        raise _make_exception_group(
            "run_eternal_tasks",
            tuple(_noreturn_task_exception(task) for task in args if not (task.cancelled() and task in cancelled_by_us)),
        )  # (3)

    except asyncio.CancelledError:
        try:
            # We get here if (1) was cancelled, or if (2) was cancelled, or if during (3) we discovered that one of the
            # tasks was cancelled not by us. In all cases cancellation of all tasks has already been requested.
            #
            # In all branches we give the tasks exactly one chance to wrap up. If we got here from (1), this is their
            # first chance. If we got here from (2), then their first chance was interrupted and we resume it. If we got
            # here from (3), the tasks have already wrapped up and this is a no-op.
            await asyncio.wait(args, return_when=asyncio.ALL_COMPLETED)  # (4)
            raise
        finally:
            # We get here in any situation where we bubble up a CancelledError. Which implies that if there are any
            # tasks that raised an exception, we cannot report those exceptions by reraising. Instead we do the next
            # best thing and log them. Note that it's possible that we got here because (4) was cancelled, and thus some
            # tasks are still pending. Not much we can do about those.
            for task in args:
                if task.done() and not task.cancelled():
                    logger.error(
                        f"run_eternal_tasks was cancelled, but {task!r} raised",
                        exc_info=_noreturn_task_exception(task),
                    )

    # Possible control flows:
    # - Task raised:
    #   (1) -> (2) -> (3)
    # - Task cancelled not by us:
    #   (1) -> (2) -> (3) -> (4)
    # - Task raised, and during finalization some other task got cancelled not by us:
    #   (1) -> (2) -> (4)
    # - We were cancelled:
    #   (1) -> (4)

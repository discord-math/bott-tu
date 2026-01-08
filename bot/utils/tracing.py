"""
This module defines utilities for tracing spans.

Tracing is like logging, but while a log message represents an instant in time, a "span" instead represends an interval,
a block of code being entered and exited. A span has an associated start and end timestamp, and a unique span ID. Spans
can be nested inside each other, in which case a span links to its parent's ID, forming a tree.

Traces are output to the logs, every time a span ends, a log message is emitted describing the span.

Nesting of spans is tracked using :mod:`py:contextvars`, meaning it will not jump between :class:`py:threading.Thread` s
or :class:`py:asyncio.Task` s but can be made to, if needed.
"""

import asyncio
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import MISSING, dataclass
from datetime import datetime, timezone
import functools
import logging
import sys
from types import TracebackType
from typing import Any, Callable, ParamSpec, TypeVar, override
from uuid import UUID, uuid4


_trace_span_id: ContextVar[tuple[UUID, UUID] | None] = ContextVar("_trace_span_id", default=None)


_no_caller_info = ("(unknown file)", 0, "(unknown function)")


def _get_caller_info(level: int) -> tuple[str, int, str]:
    frame = logging.currentframe()
    for _ in range(level):
        if frame is None:
            return _no_caller_info
        frame = frame.f_back
    if frame is None:
        return _no_caller_info
    return frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name


@dataclass(kw_only=True, frozen=True)
class _TraceStartInfo:
    msg: str
    caller_info: tuple[str, int, str]
    parent_trace_span_id: tuple[UUID, UUID] | None
    trace_id: UUID
    span_id: UUID
    start_time: datetime


def _start_trace(msg: str, caller_info: tuple[str, int, str], /) -> _TraceStartInfo:
    parent_trace_span_id = _trace_span_id.get()
    trace_id = uuid4() if parent_trace_span_id is None else parent_trace_span_id[0]
    span_id = uuid4()
    _trace_span_id.set((trace_id, span_id))
    return _TraceStartInfo(
        msg=msg,
        caller_info=caller_info,
        parent_trace_span_id=parent_trace_span_id,
        trace_id=trace_id,
        span_id=span_id,
        start_time=datetime.now(timezone.utc),
    )


@dataclass(kw_only=True, frozen=True)
class _TraceEndInfo:
    end_time: datetime
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None


def _end_trace(
    start: _TraceStartInfo,
    /,
    *,
    exc_info: tuple[type[BaseException] | None, BaseException | None, TracebackType | None] | None,
) -> _TraceEndInfo:
    end_time = datetime.now(timezone.utc)
    _trace_span_id.set(start.parent_trace_span_id)
    return _TraceEndInfo(
        end_time=end_time,
        exc_info=(
            (exc_info[0], exc_info[1], exc_info[2])
            if exc_info is not None and exc_info[0] is not None and exc_info[1] is not None
            else None
        ),
    )


def _log_trace(
    logger: logging.Logger, start: _TraceStartInfo, end: _TraceEndInfo, /, *, extra: dict[str, object] = {}
) -> None:
    # Functions like `logger.debug` will collect the caller info on their own, but there's no way to override it, and we
    # want the logs to point to the invocations of `trace` and `traced`, not this `_log_trace` function. So we have to
    # obtain caller info and construct a record manually:
    fn, lno, func = start.caller_info
    logger.handle(
        logger.makeRecord(
            name=logger.name,
            level=logging.DEBUG,
            fn=fn,
            lno=lno,
            msg=start.msg,
            args=(),
            exc_info=end.exc_info,
            func=func,
            extra={
                "trace": {
                    "trace_id": start.trace_id,
                    "span_id": start.span_id,
                    "parent_span_id": None if start.parent_trace_span_id is None else start.parent_trace_span_id[1],
                    "start_time": start.start_time,
                    "end_time": end.end_time,
                    **extra,
                },
            },
        )
    )


class trace(AbstractContextManager[None]):
    """
    A context manager (:ref:`py:context-managers`) causing the contained block to be traced as a span:

    .. code-block:: python

        with trace(logger, "sleeping"):
            await asyncio.sleep(1)
    """

    __slots__ = (
        "_logger",
        "_msg",
        "_log_exceptions",
        "_start",
    )

    def __init__(self, logger: logging.Logger, msg: str, /, *, log_exceptions: bool = True):
        self._logger = logger
        self._msg = msg
        self._log_exceptions = log_exceptions

    def __enter__(self) -> None:
        # level 0 is `_get_caller_info`
        # level 1 is `__enter__`
        # level 2 is the location of the `with` block that invoked `__enter__`
        self._start = _start_trace(self._msg, _get_caller_info(level=2))

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        end = _end_trace(self._start, exc_info=(exc_type, exc, tb) if self._log_exceptions else None)
        _log_trace(self._logger, self._start, end)


P = ParamSpec("P")
R = TypeVar("R")


def traced(
    logger: logging.Logger, /, *, log_args: bool = False, log_result: bool = False, log_exceptions: bool = True
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    A decorator causing the entire function to be traced as a span, starting when it is called, ending when it returns
    or throws an exception:

    .. code-block:: python

        @traced(logger)
        def foo():
            ...

    The function can be an async coroutine.
    """

    # level 0 is `_get_caller_info``
    # level 1 is `traced``
    # level 2 is wherever `@traced` was called
    caller_info = _get_caller_info(level=2)
    # ^ Importantly, collect the caller info during decoration, and not when the decorated function is called.

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if not asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                start = _start_trace(func.__qualname__, caller_info)
                result = MISSING
                try:
                    return (result := func(*args, **kwargs))
                finally:
                    end = _end_trace(start, exc_info=sys.exc_info() if log_exceptions else None)
                    extra: dict[str, object] = {}
                    if log_args:
                        extra["args"] = args
                        extra["kwargs"] = kwargs
                    # Be careful to distinguish the case where the function threw an exception, vs the case where it
                    # returned None
                    if log_result and result is not MISSING:
                        extra["result"] = result
                    _log_trace(logger, start, end, extra=extra)

            return wrapper
        else:
            # If `func` is a coroutine, then `func()` actually returns immediately, and the above wrapper would give us
            # an unhelpful `end_time`. Instead we have to create an async wrapper, that performs `await func()` and only
            # afterwards ends the trace.
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # ^ Any because the R = Coroutine[?, None, None] and the return type is the ?
                start = _start_trace(func.__qualname__, caller_info)
                result = MISSING
                try:
                    return (result := await func(*args, **kwargs))
                finally:
                    end = _end_trace(start, exc_info=sys.exc_info() if log_exceptions else None)
                    extra: dict[str, object] = {}
                    if log_args:
                        extra["args"] = args
                        extra["kwargs"] = kwargs
                    # Be careful to distinguish the case where the function threw an exception, vs the case where it
                    # returned None
                    if log_result and result is not MISSING:
                        extra["result"] = result
                    _log_trace(logger, start, end, extra=extra)

            return async_wrapper  # type: ignore

    return decorator


class SpanIdInjector(logging.Filter):
    """
    A :class:`py:logging.Filter` that adds parent span IDs to ordinary log messages, whenever they occur inside a span.
    """

    @override
    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        """Doesn't filter, only adds tracing data."""
        if parent_trace_span_id := _trace_span_id.get():
            trace: dict[str, object]
            if hasattr(record, "trace"):
                trace = record.trace  # type: ignore
            else:
                trace = {}
                record.trace = trace

            trace["trace_id"] = parent_trace_span_id[0]
            trace["parent_span_id"] = parent_trace_span_id[1]
        return record

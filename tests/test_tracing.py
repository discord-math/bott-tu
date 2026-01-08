import logging
import os
from unittest import IsolatedAsyncioTestCase, TestCase

from bot.utils.tracing import SpanIdInjector, trace, traced


logger = logging.getLogger(__name__)


class TestTracing(TestCase):
    def setUp(self):
        self._injector = SpanIdInjector()
        logger.addFilter(self._injector)

    def tearDown(self):
        logger.removeFilter(self._injector)

    def test_contextmanager(self):
        with self.assertLogs(__name__, logging.DEBUG) as record:
            with trace(logger, "foo"):
                pass

        self.assertTrue(any(getattr(record, "trace", None) for record in record.records))

    def test_decorator(self):
        @traced(logger)
        def foo() -> None:
            pass

        with self.assertLogs(__name__, logging.DEBUG) as record:
            foo()

        self.assertTrue(any(getattr(record, "trace", None) for record in record.records))

    def test_nesting(self):
        with self.assertLogs(__name__, logging.DEBUG) as record:
            with trace(logger, "foo"):
                with trace(logger, "bar"):
                    pass
                with trace(logger, "baz"):
                    pass

        self.assertEqual(len(record.records), 3)
        log1, log2, log3 = record.records
        self.assertEqual(log1.msg, "bar")
        self.assertEqual(log2.msg, "baz")
        self.assertEqual(log3.msg, "foo")
        trace1 = getattr(log1, "trace")
        trace2 = getattr(log2, "trace")
        trace3 = getattr(log3, "trace")
        self.assertEqual(trace1["parent_span_id"], trace3["span_id"])
        self.assertEqual(trace2["parent_span_id"], trace3["span_id"])
        self.assertEqual(trace3.get("parent_span_id"), None)
        self.assertEqual(trace1["trace_id"], trace3["trace_id"])
        self.assertEqual(trace2["trace_id"], trace3["trace_id"])

    def test_log_nesting(self):
        with self.assertLogs(__name__, logging.DEBUG) as record:
            with trace(logger, "foo"):
                logger.debug("bar")

        self.assertEqual(len(record.records), 2)
        log1, log2 = record.records
        self.assertEqual(log1.msg, "bar")
        self.assertEqual(log2.msg, "foo")
        trace1 = getattr(log1, "trace")
        trace2 = getattr(log2, "trace")
        self.assertEqual(trace1["parent_span_id"], trace2["span_id"])
        self.assertEqual(trace1.get("span_id"), None)
        self.assertEqual(trace1["trace_id"], trace2["trace_id"])

    def test_log_exception(self):
        for log_exceptions in (False, True):
            with self.assertLogs(__name__, logging.DEBUG) as record:
                with self.assertRaises(ValueError):
                    with trace(logger, "foo", log_exceptions=log_exceptions):
                        raise ValueError()

            for record in record.records:
                if hasattr(record, "trace"):
                    if log_exceptions:
                        self.assertIsNotNone(record.exc_info)
                    else:
                        self.assertIsNone(record.exc_info)

            @traced(logger, log_exceptions=log_exceptions)
            def foo():
                raise ValueError()

            with self.assertLogs(__name__, logging.DEBUG) as record:
                with self.assertRaises(ValueError):
                    foo()

            for record in record.records:
                if hasattr(record, "trace"):
                    if log_exceptions:
                        self.assertIsNotNone(record.exc_info)
                    else:
                        self.assertIsNone(record.exc_info)

    def test_log_args(self):
        for log_args in (False, True):

            @traced(logger, log_args=log_args)
            def foo(x: int, y: int) -> int:
                return x

            with self.assertLogs(__name__, logging.DEBUG) as record:
                foo(42, 0)

            for record in record.records:
                if span := getattr(record, "trace", None):
                    if log_args:
                        self.assertIn("args", span)
                        self.assertSequenceEqual(span["args"], [42, 0])
                    else:
                        self.assertNotIn("args", span)

    def test_log_result(self):
        for log_result in (False, True):

            @traced(logger, log_result=log_result)
            def foo(x: int, y: int) -> int:
                return x // y

            with self.assertLogs(__name__, logging.DEBUG) as record:
                foo(42, 1)

            for record in record.records:
                if span := getattr(record, "trace", None):
                    if log_result:
                        self.assertIn("result", span)
                        self.assertEqual(span["result"], 42)
                    else:
                        self.assertNotIn("result", span)

            with self.assertLogs(__name__, logging.DEBUG) as record:
                with self.assertRaises(ZeroDivisionError):
                    foo(42, 0)

            for record in record.records:
                if span := getattr(record, "trace", None):
                    self.assertNotIn("result", span)

    def test_trace_caller(self):
        def function_containing_with():
            with trace(logger, "foo"):
                pass

        with self.assertLogs(__name__, logging.DEBUG) as record:
            function_containing_with()

        self.assertEqual(record.records[0].funcName, "function_containing_with")
        self.assertEqual(record.records[0].filename, os.path.basename(__file__))

        def function_containing_def():
            @traced(logger)
            def foo():
                pass

            return foo

        with self.assertLogs(__name__, logging.DEBUG) as record:
            function_containing_def()()

        self.assertEqual(record.records[0].funcName, "function_containing_def")
        self.assertEqual(record.records[0].filename, os.path.basename(__file__))


class TestAsyncTracing(IsolatedAsyncioTestCase):
    async def test_coroutine_decorator(self):
        @traced(logger, log_result=True)
        async def foo(x: int) -> int:
            return x

        with self.assertLogs(__name__, logging.DEBUG) as record:
            await foo(42)

        for record in record.records:
            if span := getattr(record, "trace", None):
                self.assertIn("result", span)
                self.assertEqual(span["result"], 42)

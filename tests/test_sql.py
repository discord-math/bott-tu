from dataclasses import dataclass
import logging
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import sentinel

from bot.database.pool import create_database_pool
from bot.database.queries import FieldOrder, insert, select_single
from tests.database import TEST_DB, InTransactionMixin


@dataclass
class MyClass:
    x: int
    y: str


@dataclass
class OtherClass:
    z: int


@dataclass
class ExtraClass:
    w: float


class TestFieldOrder(TestCase):
    def test_rendering(self):
        fields = FieldOrder(MyClass)
        self.assertEqual(fields.columns, "x, y")
        self.assertEqual(fields.placeholders, "$1, $2")
        self.assertEqual(fields.set_list, "x = $1, y = $2")

    def test_rendering_prefix(self):
        fields = FieldOrder(MyClass, prefix="test")
        self.assertEqual(fields.columns, "test.x, test.y")
        self.assertEqual(fields.placeholders, "$1, $2")
        self.assertEqual(fields.set_list, "test.x = $1, test.y = $2")

    def test_rendering_tupled(self):
        fields = FieldOrder(MyClass).tupled(OtherClass).tupled(ExtraClass)
        self.assertEqual(fields.columns, "x, y, z, w")
        self.assertEqual(fields.placeholders, "$1, $2, $3, $4")
        self.assertEqual(fields.set_list, "x = $1, y = $2, z = $3, w = $4")

    def test_rendering_tupled_prefix(self):
        fields = FieldOrder(MyClass, prefix="my").tupled(OtherClass, prefix="other")
        self.assertEqual(fields.columns, "my.x, my.y, other.z")
        self.assertEqual(fields.placeholders, "$1, $2, $3")
        self.assertEqual(fields.set_list, "my.x = $1, my.y = $2, other.z = $3")

    def test_rendering_tupled_aliased(self):
        fields = FieldOrder(MyClass).tupled(MyClass)
        self.assertEqual(fields.columns, "x, y, x, y")
        self.assertEqual(fields.placeholders, "$1, $2, $3, $4")
        self.assertEqual(fields.set_list, "x = $1, y = $2, x = $3, y = $4")

    def test_construction(self):
        x = sentinel.x
        y = sentinel.y
        fields = FieldOrder(MyClass)
        self.assertEqual(
            MyClass(x=x, y=y),
            fields.from_tuple((x, y)),
        )
        self.assertEqual(
            (x, y),
            fields.to_tuple(MyClass(x=x, y=y)),
        )

    def test_construction_prefix(self):
        x = sentinel.x
        y = sentinel.y
        fields = FieldOrder(MyClass, prefix="test")
        self.assertEqual(
            MyClass(x=x, y=y),
            fields.from_tuple((x, y)),
        )
        self.assertEqual(
            (x, y),
            fields.to_tuple(MyClass(x=x, y=y)),
        )

    def test_construction_tupled(self):
        x = sentinel.x
        y = sentinel.y
        z = sentinel.z
        w = sentinel.w
        fields = FieldOrder(MyClass).tupled(OtherClass).tupled(ExtraClass)
        self.assertEqual(
            ((MyClass(x=x, y=y), OtherClass(z=z)), ExtraClass(w=w)),
            fields.from_tuple((x, y, z, w)),
        )
        self.assertEqual(
            (x, y, z, w),
            fields.to_tuple(((MyClass(x=x, y=y), OtherClass(z=z)), ExtraClass(w=w))),
        )

    def test_construction_tupled_aliased(self):
        x1 = sentinel.x1
        y1 = sentinel.y1
        x2 = sentinel.x2
        y2 = sentinel.y2
        fields = FieldOrder(MyClass).tupled(MyClass)
        self.assertEqual(
            (MyClass(x=x1, y=y1), MyClass(x=x2, y=y2)),
            fields.from_tuple((x1, y1, x2, y2)),
        )
        self.assertEqual(
            (x1, y1, x2, y2),
            fields.to_tuple((MyClass(x=x1, y=y1), MyClass(x=x2, y=y2))),
        )


class TestQueries(InTransactionMixin):
    async def test_example(self):
        await self.conn.execute(
            """
            CREATE TABLE tbl
                ( x BIGINT PRIMARY KEY
                , y TEXT NOT NULL
                )
            """
        )

        val = await select_single(self.conn, "tbl", MyClass)
        self.assertIs(val, None)

        mc1 = MyClass(x=123, y="foo")
        mc2 = MyClass(x=456, y="bar")

        await insert(self.conn, "tbl", mc1)

        val = await select_single(self.conn, "tbl", MyClass)
        self.assertEqual(mc1, val)

        await insert(self.conn, "tbl", mc2)

        val = await select_single(self.conn, "tbl", MyClass, "x = 456")
        self.assertEqual(mc2, val)


class TestLogging(IsolatedAsyncioTestCase):
    async def test_logging(self):
        async with await create_database_pool(database_connection_string=TEST_DB) as pool:
            with self.assertLogs("bot.database.logging", logging.DEBUG) as record:
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
            self.assertIn("DEBUG:bot.database.logging:SELECT 1", record.output)

from unittest import IsolatedAsyncioTestCase

import asyncpg
import asyncpg.transaction


TEST_DB = "postgres://bot:bot@localhost/bot"


class DatabaseConnectedMixin(IsolatedAsyncioTestCase):
    conn: asyncpg.Connection

    async def asyncSetUp(self):
        await super().asyncSetUp()

        self.conn = await asyncpg.connect(TEST_DB)

    async def asyncTearDown(self) -> None:
        await self.conn.close()

        await super().asyncTearDown()


class InTransactionMixin(DatabaseConnectedMixin):
    trans: asyncpg.transaction.Transaction

    async def asyncSetUp(self):
        await super().asyncSetUp()

        self.trans = self.conn.transaction()
        await self.trans.start()

    async def asyncTearDown(self) -> None:
        await self.trans.rollback()

        await super().asyncTearDown()

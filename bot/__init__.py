"""
The main entrypoint. This module contains code necessary for interfacing with the CLI, which should be restricted to
accepting parameters that describe how the bot is deployed and where to find services like the DB.
"""

import asyncio
import os

from bot.config.bot import ConfigStore
from bot.database.pool import create_database_pool


def get_database_connection_string():
    try:
        return os.environ["DATABASE"]
    except KeyError:
        raise KeyError(
            "Environment variable DATABASE is not set. "
            + "It needs to be set to the database URI: postgres://user:pass@host/dbname"
        )


async def _async_main():
    pool = await create_database_pool(database_connection_string=get_database_connection_string())
    store = ConfigStore(pool)
    print(await store.get_bot_config())


def main():
    asyncio.run(_async_main())

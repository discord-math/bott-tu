"""
The main entrypoint. This module contains code necessary for interfacing with the CLI, which should be restricted to
accepting parameters that describe how the bot is deployed and where to find services like the DB.
"""

import asyncio
import logging
import os

from pythonjsonlogger.json import JsonFormatter

from bot.config.bot import ConfigStore
from bot.database.pool import create_database_pool


def get_database_connection_string() -> str:
    try:
        return os.environ["DATABASE"]
    except KeyError:
        raise KeyError(
            "Environment variable DATABASE is not set. "
            + "It needs to be set to the database URI: postgres://user:pass@host/dbname"
        )


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            # The text portion of this format string is ignored, but the list of placeholders used determines which keys
            # are put into the logged JSON object.
            # Note that exc_info and stack_info are already included (when available).
            # {name} is the Logger name (usually name of module where it is created)
            "{asctime}{levelname}{name}{taskName}{module}{funcName}{lineno}{message}",
            style="{",
        )
    )
    logging.basicConfig(
        force=True,
        level=logging.NOTSET,
        handlers=(handler,),
    )


async def _async_main():
    task = asyncio.current_task()
    assert task
    task.set_name("Main Task")

    async with await create_database_pool(database_connection_string=get_database_connection_string()) as pool:
        store = ConfigStore(pool)
        logging.info(await store.get_bot_config())


def main():
    setup_logging()
    asyncio.run(_async_main())

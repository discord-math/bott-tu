"""
The main entrypoint. This module contains code necessary for interfacing with the CLI, which should be restricted to
accepting parameters that describe how the bot is deployed and where to find services like the DB.
"""

import asyncio
from datetime import datetime, timezone
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
    formatter = JsonFormatter(
        # The text portion of this format string is ignored, but the list of placeholders used determines which keys are
        # put into the logged JSON object.
        # Note that exc_info and stack_info are already included (when available).
        # {name} is the Logger name (usually name of module where it is created)
        "{asctime}{levelname}{name}{taskName}{module}{funcName}{lineno}{message}",
        style="{",
    )
    # When converting any extra data in logs into JSON, JsonFormatter will format datetime objects as ISO8601/RFC-3339,
    # e.g. "1970-01-01T00:00:00.000000+00:00". However the timestamp of the log itself is formatted by a separate
    # procedure in `logging`. The default time format in `logging` is a little quirky, so we replace it to use
    # ISO8601/RFC-3339 as well.
    formatter.formatTime = lambda record, datefmt=None: datetime.fromtimestamp(record.created, timezone.utc).isoformat(
        timespec="microseconds"  # Don't omit the .000000 just because the timestamp turned out to be an integer
    )
    handler.setFormatter(formatter)
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

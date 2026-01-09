"""
A callback that logs raw SQL statements is defined here, so that all raw SQL logs are attributed to this module.
"""

import logging

import asyncpg


logger = logging.getLogger(__name__)


def log_query(query: asyncpg.connection.LoggedQuery) -> None:
    """A logging callback automatically installed by :func:`bot.database.pool.create_database_pool`."""
    kwargs: dict[str, object] = {}
    if query.args:
        kwargs["args"] = query.args
    if query.exception:
        kwargs["exception"] = str(query.exception)

    logger.debug(query.query, extra={"query": kwargs})

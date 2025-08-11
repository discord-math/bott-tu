import logging

import asyncpg


logger = logging.getLogger(__name__)


def log_query(query: asyncpg.connection.LoggedQuery) -> None:
    kwargs: dict[str, object] = {}
    if query.args:
        kwargs["args"] = query.args
    if query.exception:
        kwargs["exception"] = str(query.exception)

    logger.info("%s", query.query, extra={"query": kwargs})

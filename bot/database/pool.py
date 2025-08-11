import asyncpg

import bot.database.logging


async def _init_connection(connection: asyncpg.Connection) -> None:
    connection.add_query_logger(bot.database.logging.log_query)


async def create_database_pool(*, database_connection_string: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=database_connection_string,
        init=_init_connection,
        min_size=10,
        max_size=20,
    )
    return pool

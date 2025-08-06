import asyncpg


async def create_database_pool(*, database_connection_string: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=database_connection_string, min_size=10, max_size=20)

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def create_database_pool(*, database_connection_string: str) -> AsyncEngine:
    return create_async_engine(url=database_connection_string, pool_size=10, max_overflow=10)

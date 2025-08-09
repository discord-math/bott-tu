from dataclasses import dataclass

import asyncpg


@dataclass(kw_only=True)
class BotConfig:
    """
    Top-level configuration, meaning values that scope over the entire bot, instead of being local to some guild,
    channel, user etc.
    """

    discord_token: str


class BotConfigModel:
    __slots__ = "_pool", "_config"
    _config: BotConfig | None

    def __init__(self, pool: asyncpg.Pool, /):
        self._pool = pool
        self._config = None

    async def get_config(self) -> BotConfig:
        if self._config is None:
            self._config = await self._select()
        return self._config

    async def set_config(self, config: BotConfig, /) -> None:
        await self._update(config)
        self._config = config

    async def create_initial_config(self, config: BotConfig, /) -> None:
        await self._insert(config)
        self._config = config

    async def _select(self) -> BotConfig:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT discord_token FROM bot.bot_config
                """
            )
            if row is None:
                raise LookupError(
                    "No rows in bot.bot_config\n\n"
                    + "You need to run 'python -m bot.setup' to create an initial configuration."
                )
            return BotConfig(discord_token=row["discord_token"])

    async def _insert(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO bot.bot_config
                        (discord_token)
                        VALUES
                        ($1)
                    """,
                    config.discord_token,
                )
            except asyncpg.exceptions.UniqueViolationError:
                raise LookupError("A row in bot.bot_config already exists")

    async def _update(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            updated = await conn.fetchval(
                """
                UPDATE bot.bot_config
                SET
                    discord_token = $1
                RETURNING TRUE
                """,
                config.discord_token,
            )
            if updated is None:
                raise LookupError("No rows in bot.bot_config")

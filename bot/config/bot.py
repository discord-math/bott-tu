from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from bot.database.interpolation import FieldOrder


@dataclass(kw_only=True)
class BotConfig:
    """
    Top-level configuration, meaning values that scope over the entire bot, instead of being local to some guild,
    channel, user etc.
    """

    discord_token: str


@dataclass(kw_only=True)
class BotConfigRow:
    discord_token: str

    def to_data(self) -> BotConfig:
        return BotConfig(discord_token=self.discord_token)

    @staticmethod
    def from_data(data: BotConfig) -> BotConfigRow:
        return BotConfigRow(discord_token=data.discord_token)


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
            fields = FieldOrder(BotConfigRow)
            row = await conn.fetchrow(f"SELECT {fields.columns} FROM bot.bot_config")
            if row is None:
                raise LookupError(
                    "No rows in bot.bot_config\n\n"
                    + "You need to run 'python -m bot.setup' to create an initial configuration."
                )
            return fields.from_tuple(row).to_data()

    async def _insert(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            try:
                fields = FieldOrder(BotConfigRow)
                await conn.execute(
                    f"INSERT INTO bot.bot_config ({fields.columns}) VALUES ({fields.placeholders})",
                    *fields.to_tuple(BotConfigRow.from_data(config)),
                )
            except asyncpg.exceptions.UniqueViolationError:
                raise LookupError("A row in bot.bot_config already exists")

    async def _update(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            fields = FieldOrder(BotConfigRow)
            updated = await conn.fetchval(
                f"UPDATE bot.bot_config SET {fields.set_list} RETURNING TRUE",
                *fields.to_tuple(BotConfigRow.from_data(config)),
            )
            if updated is None:
                raise LookupError("No rows in bot.bot_config")

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from bot.database.queries import FieldOrder, insert, select_single


@dataclass(kw_only=True, frozen=True)
class BotConfig:
    """
    Top-level configuration, meaning values that scope over the entire bot, instead of being local to some guild,
    channel, user etc.
    """

    discord_token: str


@dataclass(kw_only=True, frozen=True)
class BotConfigRow:
    discord_token: str

    def to_data(self) -> BotConfig:
        return BotConfig(discord_token=self.discord_token)

    @staticmethod
    def from_data(data: BotConfig) -> BotConfigRow:
        return BotConfigRow(discord_token=data.discord_token)


_bot_config_table = "bot.bot_config"


class ConfigStore:
    __slots__ = "_pool", "_bot_config"
    _bot_config: BotConfig | None

    def __init__(self, pool: asyncpg.Pool, /):
        self._pool = pool
        self._bot_config = None

    async def get_bot_config(self) -> BotConfig:
        if self._bot_config is None:
            self._bot_config = await self._select()
        return self._bot_config

    async def set_bot_config(self, config: BotConfig, /) -> None:
        await self._update(config)
        self._bot_config = config

    async def create_initial_config(self, config: BotConfig, /) -> None:
        await self._insert(config)
        self._bot_config = config

    async def _select(self) -> BotConfig:
        async with self._pool.acquire() as conn:
            row = await select_single(conn, _bot_config_table, BotConfigRow)
            if row is None:
                raise LookupError(
                    f"No rows in {_bot_config_table}\n\n"
                    + "You need to run 'python -m bot.setup' to create an initial configuration."
                )
            return row.to_data()

    async def _insert(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            try:
                await insert(conn, _bot_config_table, BotConfigRow.from_data(config))
            except asyncpg.exceptions.UniqueViolationError:
                raise LookupError(f"A row in {_bot_config_table} already exists")

    async def _update(self, config: BotConfig, /) -> None:
        async with self._pool.acquire() as conn:
            fields = FieldOrder(BotConfigRow)
            updated = await conn.fetchval(
                f"UPDATE {_bot_config_table} SET {fields.set_list} RETURNING TRUE",
                *fields.to_tuple(BotConfigRow.from_data(config)),
            )
            if updated is None:
                raise LookupError(f"No rows in {_bot_config_table}")

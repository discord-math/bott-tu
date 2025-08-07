from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import sqlalchemy
from sqlalchemy import TEXT
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.schema.base import Base


@dataclass(kw_only=True)
class BotConfig:
    """
    Top-level configuration, meaning values that scope over the entire bot, instead of being local to some guild,
    channel, user etc.
    """

    discord_token: str


class BotConfigRow(Base, kw_only=True):
    __tablename__ = "bot_config"
    __table_args__ = {"schema": "bot"}

    discord_token: Mapped[str] = mapped_column(TEXT, nullable=False, primary_key=True)
    # In reality the primary key is the empty tuple, meaning only 1 row allowed. But sqlalchemy wants at least one
    # primary key column, so we use a random column. This is actually a strictly weaker primary key than the empty
    # tuple.

    def to_data(self) -> BotConfig:
        return BotConfig(discord_token=self.discord_token)

    def as_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @staticmethod
    def from_data(config: BotConfig) -> BotConfigRow:
        return BotConfigRow(discord_token=config.discord_token)


class BotConfigModel:
    __slots__ = "_pool", "_config"
    _config: BotConfig | None

    def __init__(self, pool: AsyncEngine, /):
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
        async with AsyncSession(self._pool) as session:
            row = await session.scalar(sqlalchemy.select(BotConfigRow))

            if row is None:
                raise LookupError(
                    f"No rows in {BotConfigRow.__table__}\n\n"
                    + "You need to run 'python -m bot.setup' to create an initial configuration."
                )
            return row.to_data()

    async def _insert(self, config: BotConfig, /) -> None:
        async with AsyncSession(self._pool) as session:
            try:
                session.add(BotConfigRow.from_data(config))
                await session.commit()
            except IntegrityError:
                raise LookupError(f"A row in {BotConfigRow.__table__} already exists")

    async def _update(self, config: BotConfig, /) -> None:
        async with AsyncSession(self._pool) as session:
            updated = await session.scalar(
                sqlalchemy.update(BotConfigRow)
                .values(**BotConfigRow.from_data(config).as_dict())
                .returning(sqlalchemy.true())
            )
            if updated is None:
                raise LookupError(f"No rows in {BotConfigRow.__table__}")
            await session.commit()

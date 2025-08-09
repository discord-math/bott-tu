"""
A simple setup script that prompts the user for some initial configuration that the user cannot otherwise set via bot's
other interfaces.
"""

import asyncio

from bot import get_database_connection_string
from bot.config.bot import BotConfig, ConfigStore
from bot.database.pool import create_database_pool


def _prompt_yes_no(prompt: str, /) -> bool:
    while True:
        print(f"{prompt} [Y/n] ", end="")
        match input():
            case "" | "y":
                return True
            case "n":
                return False
            case _:
                continue


async def _async_main():
    pool = await create_database_pool(database_connection_string=get_database_connection_string())
    store = ConfigStore(pool)

    discord_token = input("Enter Discord bot token: ")

    config = BotConfig(discord_token=discord_token)

    try:
        await store.create_initial_config(config)
    except LookupError:
        if _prompt_yes_no("A config already exists. Overwrite?"):
            await store.set_bot_config(config)


if __name__ == "__main__":
    asyncio.run(_async_main())

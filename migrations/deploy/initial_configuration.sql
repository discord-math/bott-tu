-- Deploy bot:initial_configuration to pg

BEGIN;

CREATE SCHEMA bot;

CREATE TABLE bot.bot_config
    ( discord_token TEXT NOT NULL
    );

-- Make it so that the table can only ever hold at most 1 row.
CREATE UNIQUE INDEX bot_config_one_row_only ON bot.bot_config ( (TRUE) );

COMMIT;

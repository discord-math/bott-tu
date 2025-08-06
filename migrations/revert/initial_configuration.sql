-- Revert bot:initial_configuration from pg

BEGIN;

DROP TABLE bot.bot_config;

DROP SCHEMA bot;

COMMIT;

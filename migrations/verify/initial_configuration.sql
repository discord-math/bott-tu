-- Verify bot:initial_configuration on pg

BEGIN;

SELECT FROM bot.bot_config WHERE FALSE;

ROLLBACK;

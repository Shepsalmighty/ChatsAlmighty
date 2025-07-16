import asyncio
import logging
import sqlite3
from concurrent.futures.thread import ThreadPoolExecutor

import asqlite
import twitchio
from twitchio.ext import commands
from twitchio import eventsub
from os import getenv
from dotenv import load_dotenv
from twitchio.ext.commands import is_owner

from db_interface import DataBaseInterface as DB
from audio_player import Player

LOGGER: logging.Logger = logging.getLogger("Bot")
load_dotenv()


#TODO blacklist count to 4 song

# #TODO switch over from self botting to bot account

class Bot(commands.Bot):
    def __init__(self, *, token_database: asqlite.Pool, pool: asqlite.Pool) -> None:
        self.token_database = token_database
        super().__init__(
            client_id=getenv("CLIENT_ID"),
            client_secret=getenv("CLIENT_SECRET"),
            bot_id=getenv("BOT_ID"),
            owner_id=getenv("OWNER_ID"),
            prefix="!",
            case_insensitive=True

        )
        self.pool = pool
        self.file_path = "bot_db.db"
        self.db = DB(self.file_path, self.pool)



    async def setup_hook(self) -> None:
        # Add our component which contains our commands...
        # await self.add_component(MyComponent(self))
        await self.load_module("gen_cmds")
        await self.load_module("mod_cmds")

        sub = eventsub.ChatMessageSubscription(broadcaster_user_id=getenv("BOT_ID"), user_id=getenv("BOT_ID"))
        await self.subscribe_websocket(sub)

        with open("db_schema.sql") as fp:
            async with self.pool.acquire() as conn:
                await conn.executescript(fp.read())

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        await self.process_commands(payload)

    async def add_token(self, token: str, refresh: str) -> twitchio.authentication.ValidateTokenPayload:
        # Make sure to call super() as it will add the tokens interally and return us some data...
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        # Store our tokens in a simple SQLite Database when they are authorized...
        query = """
        INSERT INTO tokens (user_id, token, refresh)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            token = excluded.token,
            refresh = excluded.refresh;
        """

        async with self.token_database.acquire() as con:
            await con.execute(query, (resp.user_id, token, refresh))

        LOGGER.info("Added token to the database for user: %s", resp.user_id)
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        # We don't need to call this manually, it is called in .login() from .start() internally...

        async with self.token_database.acquire() as connection:
            rows: list[sqlite3.Row] = await connection.fetchall("""SELECT * from tokens""")

        for row in rows:
            await self.add_token(row["token"], row["refresh"])

    async def setup_database(self) -> None:
        # Create our token table, if it doesn't exist..
        query = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""
        async with self.token_database.acquire() as connection:
            await connection.execute(query)

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_command_error(self, payload: commands.CommandErrorPayload) -> None:
        ctx = payload.context
        command = ctx.command
        error = payload.exception

        # We don't want to dispatch errors that have already been handled before...
        if command and command.has_error and ctx.error_dispatched:
            return
        # Example: A common error to suppress is the CommandNotFound error...
        if isinstance(error, commands.CommandNotFound):
            return
        # Example: As an example if a guard fails we can send a default message back...
        if isinstance(error, commands.GuardFailure):
            if isinstance(error, commands.CommandOnCooldown):
                await ctx.reply(f"{ctx.command.qualified_name} on cooldown for {ctx.author.name},  {int(error.remaining)}s until next use")
                print(error)
            return

        # For all unhandled errors, we should log them so we know what went wrong...
        msg = f'Ignoring exception in command "{ctx.command}":\n'
        LOGGER.error(msg, exc_info=error)





def main() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)
    async def runner() -> None:
        async with (asqlite.create_pool("tokens.db") as tdb,
            asqlite.create_pool("bot_db.db") as pool, Bot(token_database=tdb, pool=pool) as bot):
            await bot.setup_database()
            await bot.start()


    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")


if __name__ == "__main__":
    main()




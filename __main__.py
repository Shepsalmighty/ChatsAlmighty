import asyncio
import logging
import sqlite3

import asqlite
import twitchio
from twitchio.ext import commands
from twitchio import eventsub
from os import getenv
from dotenv import load_dotenv
from db_interface import DataBaseInterface as DB
from audio_player import Player

LOGGER: logging.Logger = logging.getLogger("Bot")
load_dotenv()

perms_list = ["sea_of_tranquility", "stderr_dk"]
#TODO blacklist count to 4 song

def has_perm():
    async def predicate(ctx: commands.Context) -> bool:
        chatter = ctx.chatter
        if not isinstance(chatter, twitchio.Chatter):
            return False

        query = """SELECT has_perms
                            FROM user_perms
                            WHERE user_id = ?
                            LIMIT 1"""

        async with ctx.bot.pool.acquire() as con:
            result = await con.fetchone(query, (ctx.chatter.id,))

        return chatter.broadcaster or chatter.moderator or (result is not None and bool(result[0]))

    return commands.guard(predicate)


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


    async def setup_hook(self) -> None:
        # Add our component which contains our commands...
        await self.add_component(MyComponent(self))
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
            return

        # For all unhandled errors, we should log them so we know what went wrong...
        msg = f'Ignoring exception in command "{ctx.command}":\n'
        LOGGER.error(msg, exc_info=error)


class MyComponent(commands.Component):
    def __init__(self, bot: Bot):
        # Passing args is not required...
        # We pass bot here as an example...
        self.bot = bot
        self.derp_trigger = 69
        self.derp_count = 0
        self.leviosah_trigger = 5
        self.leviosah_count = 0
        self.file_path = "bot_db.db"
        self.db = DB(self.file_path, self.bot.pool)
        self.seen_users = set()
        # self.player = Player(self.onPlaybackFinished)

    def onPlaybackFinished(self, played_url: str):
        """ clear the played song from DB
            check if there are more songs in queue
            requests the new song to play"""
        # self.player.play_song(await db_interface.get_song[0])
        pass
    @has_perm()
    @commands.command(aliases=["hello", "howdy", "how_are_ya", "rainbow_dicks"])
    async def hi(self, ctx:commands.Context):
        # perms_list.append(ctx.chatter.name)
        await ctx.reply(f"Hello, World! Oh, and you {ctx.chatter.mention}")


#TODO song request command
#TODO:
# if the bot detects that the song contains vocals, the bot responds to the request,
# asking if the vocals should be disabled. if the requester confirms,
# you use another neuronal network to remove the vocals and play clean-version

    @has_perm()
    @commands.command(aliases=["song_req", "song_request", "s_r"])
    async def sr(self, ctx:commands.Context, song: str) -> None:
        #INFO youtube may shorten link so if check could break/cause issues
        if not song.startswith("https://www.youtube.com/watch?v="):
            return
        user = ctx.author.id
        await self.db.song_req(user=user, song=song)

    @commands.command(aliases=["undo", "cancel", "remove"])
    async def remove_last(self, ctx:commands.Context):
        await self.db.remove(ctx.author.id)

    @commands.is_owner()
    async def clear(self, ctx:commands.Context):
        await self.db.clear_songs()

    # TODO: add timestamps to left messages AND figure out a re-notify timer
    #  if a new message is left users should be told after 30 mins (for example)
    @has_perm()
    @commands.command(aliases=["leave_msg", "lm", "send_msg", "sendmsg", "hatemsg"])
    async def leavemsg(self, ctx:commands.Context, receiver: twitchio.User):
        msg = ctx.message.text
        msg_time = ctx.message.timestamp
        sender = ctx.author.id
        target = receiver.id
        await self.db.leave_message(sender=sender, reciever=target, msg=msg)

    @has_perm()
    @commands.command(aliases=["get_msg", "gm", "showfeet", "fwends"])
    async def getmsg(self, ctx:commands.Context, sender: twitchio.User):
        # sender_id = sender
        receiver = ctx.author
        messages = await self.db.get_message(sender=sender, receiver=receiver)
        for msg in messages:
            await ctx.reply(msg)

    @commands.command(aliases=["messages", "msgs"])
    async def inbox(self, ctx: commands.Context):
        response = await self.db.notify(chatter_id=ctx.author.id)

        notify_parts: list[str] = []

        if not response:
            return

        for count, user_id in response:
            user = await self.bot.fetch_user(id=user_id)
            notify_parts.append(f"{user.name} ({count})")

        notify = (f"{ctx.author.mention} you have messages stored from: " +
                  ", ".join(notify_parts) +
                  " to get a message use !getmsg @username")

        await ctx.broadcaster.send_message(message=notify, sender=self.bot.user, token_for=self.bot.user)

    @commands.command()
    async def new_error(self, ctx:commands.Context):
        raise ValueError("a new error occurs")

    @commands.Component.listener("message")
    async def seen_chatter(self, payload: twitchio.ChatMessage):
        if payload.chatter.id in self.seen_users:
            return
        self.seen_users.add(payload.chatter.id)
        response = await self.db.notify(chatter_id=payload.chatter.id)

        notify_parts: list[str] = []

        if not response:
            return

        for count, user_id in response:
            user = await self.bot.fetch_user(id=user_id)
            notify_parts.append(f"{user.name} ({count})")

        notify = (f"{payload.chatter.mention} you have messages stored from: " +
                  ", ".join(notify_parts) +
                  " to get a message use !getmsg @username")

        await payload.broadcaster.send_message(message=notify, sender=self.bot.user, token_for=self.bot.user)

#INFO leviosaAH func
    # @commands.Component.listener()
    # async def leviosah_message(self, payload: twitchio.ChatMessage):
    #     self.leviosah_count += 1
    #     if self.leviosah_count <= self.leviosah:
    #         return
    #     elif payload.chatter.id == self.bot.owner_id: #make me look big smart - no derp string for me
    #         return
    #     """word = msg.split()[-1]
    #      if len(word) >= 3 and (word[-3] in "aeiou") and (word[-1] in "aeiou"):
    #       reply(f"its called {word[:-1] + word[-1] * 4} not {word[:-3] + word[-3] * 4 + word[-2:]}")
    #       """
    #     word = payload.text.split()[-1].lower()
    #     if len(word) >= 3 and (word[-3] in "aeiou") and (word[-1] in "aeiou"):
    #         self.leviosah_count = 0
    #
    #         derp_string = f"its called {word[:-1] + word[-1] * 4} not {word[:-3] + word[-3] * 4 + word[-2:]}"
    #
    #         await payload.broadcaster.send_message(message=derp_string, sender=self.bot.user, token_for=self.bot.user)



#INFO derp func
    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage):
        self.derp_count += 1
        self.leviosah_count += 1
        if payload.chatter.id != self.bot.owner_id and self.derp_count % self.derp_trigger == 0:
            derp_string = ""
            letters = 0
            for index in range(len(payload.text)):
                if payload.text[index].isalpha():
                    if letters % 2 == 0:
                        derp_string += payload.text[index].lower()
                    else:
                        derp_string += payload.text[index].upper()
                    letters += 1
                else:
                    derp_string += payload.text[index]
            await payload.broadcaster.send_message(message=derp_string, sender=self.bot.user, token_for=self.bot.user)

        if payload.chatter.id != self.bot.owner_id and self.leviosah_count % self.leviosah_trigger == 0:
            word = payload.text.split()[-1].lower()
            if len(word) >= 3 and (word[-3] in "aeiou") and (word[-1] in "aeiou"):
                self.leviosah_count = 0

                derp_string = f"its called {word[:-1] + word[-1].upper() * 4} not {word[:-3] + word[-3] * 4 + word[-2:]}"

                await payload.broadcaster.send_message(message=derp_string, sender=self.bot.user, token_for=self.bot.user)


    @commands.is_elevated()
    @commands.command(aliases=["allow", "fine", "ok"])
    async def permit(self, ctx:commands.Context, *users: twitchio.User) -> None:
        query = """INSERT INTO user_perms(user_id, has_perms)
                VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE
                SET has_perms = 1;"""

        user_names = ", ".join(u.name for u in users)
        await ctx.send(f"permissions granted to: {user_names}")
        # perms_list.extend(u.name for u in users)

        async with self.bot.pool.acquire() as con:
            values = [(u.id, 1) for u in users]
            await con.executemany(query, values)
            # await con.execute(query, ((u.id for u in users), "True"))

    @commands.is_elevated()
    @commands.command(aliases=["fuck_you", "fuck_off", "get_rekt", "rekt", "fu"])
    async def deny(self, ctx: commands.Context, *users: twitchio.User) -> None:
        sql_upsert = """
        INSERT INTO user_perms (user_id, has_perms)
        VALUES (?, 0)
        ON CONFLICT(user_id) DO UPDATE
        SET has_perms = 0;
        """

        user_names = ", ".join(u.name for u in users)
        await ctx.send(f"{user_names} got rekt")

        params = [(u.id,) for u in users]

        async with self.bot.pool.acquire() as con:
            await con.executemany(sql_upsert, params)


    @commands.command()
    async def claire(self, ctx: commands.Context):
        await ctx.reply("Wavegie")

    @commands.command(aliases=["discord", "community"])
    async def socials(self, ctx: commands.Context) -> None:
        await ctx.send("discord.gg/DBaUMawHhJ")
        #await ctx.send("other social") --- to print on new lines

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




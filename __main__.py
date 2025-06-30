import asyncio
import logging
import sqlite3

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
        self.lurkers = set()
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
        """if you need to be told what this does even i can't help you"""
        # perms_list.append(ctx.chatter.name)
        await ctx.reply(f"Hello, World! Oh, and you {ctx.chatter.mention}")


#TODO switch over from self botting to bot account


#TODO song request command
#TODO:
# if the bot detects that the song contains vocals, the bot responds to the request,
# asking if the vocals should be disabled. if the requester confirms,
# you use another neuronal network to remove the vocals and play clean-version

    @has_perm()
    @commands.command(aliases=["song_req", "song_request", "s_r"])
    async def sr(self, ctx:commands.Context, song: str) -> None:
        """request a song from a youtube link from browser: !sr https://www.youtube.com/watch?v=....."""
        #INFO youtube may shorten link so if check could break/cause issues
        #TODO use yt_dlp to check link is allowable yt link
        if not song.startswith("https://www.youtube.com/watch?v="):
            return
        user = ctx.author.id
        await self.db.song_req(user=user, song=song)

    @commands.command(aliases=["undo", "cancel", "remove"])
    async def remove_last(self, ctx:commands.Context):
        """remove the last song you requested"""
        await self.db.remove(ctx.author.id)

    @commands.is_owner()
    async def clear(self, ctx:commands.Context):
        """clear all song requests from queue"""
        await self.db.clear_songs()

    @has_perm()
    @commands.command(aliases=["leave_msg", "lm", "send_msg", "sendmsg", "hatemsg"])
    async def leavemsg(self, ctx:commands.Context, receiver: twitchio.User):
        """leave a message for someone: !leavemsg @someone"""
        msg = ctx.message.text
        msg_time = ctx.message.timestamp
        sender = ctx.author.id
        target = receiver.id
        await self.db.leave_message(sender=sender, reciever=target, msg=msg)

    @has_perm()
    @commands.command(aliases=["get_msg", "gm", "showfeet", "fwends"])
    async def getmsg(self, ctx:commands.Context, sender: twitchio.User):
        """get a message someone left you: !getmsg @username"""
        # sender_id = sender
        receiver = ctx.author
        messages = await self.db.get_message(sender=sender, receiver=receiver)
        for msg in messages:
            await ctx.reply(msg)

    @is_owner()
    @commands.command()
    async def brb(self, ctx: commands.Context):
        await ctx.send("Sheps will be right back, he's probably poopin")

    @commands.command(aliases=["mopLurk"])
    async def lurk(self, ctx: commands.Context):
        self.lurkers.add(ctx.author.name)

    @commands.command()
    async def lurkers(self, ctx: commands.Context):
        if len(self.lurkers) == 0:
            await ctx.send("No one hiding in the bushes")
            return
        await ctx.send("Lurkers: " + ", ".join(self.lurkers))

    @commands.command(aliases=["messages", "msgs"])
    async def inbox(self, ctx: commands.Context):
        """shows how many messages you have waiting for you"""
        response = await self.db.notify(chatter_id=ctx.author.id)

        notify_parts: list[str] = []

        if not response:
            await ctx.reply("you have no messages because no one loves you... obv")
            return

        for count, user_id in response:
            user = await self.bot.fetch_user(id=user_id)
            notify_parts.append(f"{user.name} ({count})")

        notify = (f"{ctx.author.mention} you have messages stored from: " +
                  ", ".join(notify_parts) +
                  " to get a message use !getmsg @username")

        await ctx.broadcaster.send_message(message=notify, sender=self.bot.user, token_for=self.bot.user)

    @commands.command(aliases=["clear", "clear_messages", "clear_msgs", "empty"])
    async def clear_inbox(self, ctx: commands.Context):
        """deletes all stored messages for this user"""
        count = await self.db.clear_inbox(ctx.author.id)
        await ctx.reply(f"{count} msgs deleted")

    @commands.group(invoke_fallback=True)
    async def help(self, ctx: commands.Context, *, cmd: str | None = None):
        """no help is coming! PANIC!!!!"""
        if not cmd:
            await ctx.send("use !help example_command_name to learn how that command works blah blah")
            return

        cmd = cmd.removeprefix(ctx.prefix)
        command = ctx.bot.get_command(cmd)
        if not command:
            await ctx.send(f'No command "{cmd}" found')
            return

        docs = command.callback.__doc__
        if not docs:
            return

        await ctx.send(f"{command.name} {docs}")


    @commands.command(aliases=["commands"])
    async def cmds(self, ctx:commands.Context):
        """lists all current commands for this channel"""
        cmds = []

        for cmd in ctx.bot.unique_commands:
            try:
                # I'll make this public before full release
                await cmd._run_guards(ctx, with_cooldowns=False)
            except commands.GuardFailure:
                continue

            cmds.append(f"{ctx.prefix}{cmd}")

        joined = " ".join(cmds)
        await ctx.send(f"Commands: {joined}")


#TODO move commands into 2 modules 1 for admins (permit/deny etc)
# one for everyone 

    @commands.Component.listener("event_message")
    async def seen_chatter(self, payload: twitchio.ChatMessage):
        #if chatter was lurking, remove from lurker list
        self.lurkers.discard(payload.chatter.name)

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


    @commands.Component.listener("event_message")
    async def derp_msg(self, payload: twitchio.ChatMessage):
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
        """say "hi" to Claire!"""
        await ctx.reply("Wavegie")

    @commands.command(aliases=["discord", "community"])
    async def socials(self, ctx: commands.Context) -> None:
        """get all active social links"""
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




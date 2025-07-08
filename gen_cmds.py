import asyncio
from datetime import datetime, timedelta
from unicodedata import category

import twitchio
from twitchio.ext import commands
from song_req import YoutubeAudio




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



class GenCmds(commands.Component):
    MAX_VID_LEN = 600 #seconds
    MIN_SUBSCRIBERS = 100
    ESTIMATOR_THRESHOLD = 0.2
    MIN_VID_AGE = 7
    def __init__(self, bot: commands.Bot):
        # Passing args is not required...
        # We pass bot here as an example...
        self.bot = bot
        self.derp_trigger = 69
        self.derp_count = 0
        self.leviosah_trigger = 5
        self.leviosah_count = 0
        self.seen_users = set()
        self.lurkers = set()
        # self.player = Player(self.onPlaybackFinished)
        self.rejected_songs = set()



    # #TODO song request command
    # #TODO:
    # # if the bot detects that the song contains vocals, the bot responds to the request,
    # # asking if the vocals should be disabled. if the requester confirms,
    # # you use another neuronal network to remove the vocals and play clean-version

    #TODO - command: !LMGTFY or !LMKTFY - searches the arg and returns the summary/explanation


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


    @has_perm()
    @commands.command(aliases=["song_req", "song_request", "s_r"])
    async def sr(self, ctx:commands.Context, song: str) -> None:
        """request a song from a youtube link from browser: !sr https://www.youtube.com/watch?v=.....
         songs are auto-rejected if they are too long, have lyrics or the channel is too new.
         pester the streamer if you want your song heard"""
        user = ctx.author.id
        song_object = YoutubeAudio(song)

        if song_object.info is not None:
            if ctx.author == self.bot.user:
                await self.bot.db.song_req(user=user, song=song)
                return

            song_len_ok = song_object.info.duration < GenCmds.MAX_VID_LEN
            older_than_a_week = (song_object.info.upload_date <
                                 (datetime.now() - timedelta(days=GenCmds.MIN_VID_AGE)))
            enough_subs = song_object.info.channel_follower_count > GenCmds.MIN_SUBSCRIBERS

            if song_len_ok and (older_than_a_week or enough_subs):
                loop = asyncio.get_event_loop()
                no_vocals = not await loop.run_in_executor(self.bot.executor,
                                     song_object.contains_vocals,
                                     GenCmds.ESTIMATOR_THRESHOLD)
                #INFO below is where the audio is downloaded
                if no_vocals:
                    await self.bot.db.song_req(user=user, song=song)
                    await ctx.reply("song added to queue")
                    return
                await ctx.reply("your song was rejected. reason: song has lyrics")
            else:
                await ctx.reply("your song was rejected. reason: too long (10min max) or video too new/unknown")
            self.rejected_songs.add((ctx.author.name, song))

    @commands.command()
    async def show_rejected(self, ctx: commands.Context):
        for song in self.rejected_songs:
            notify_parts: list[str] = []
            notify_parts.append(f"{song[0]} ({song[1]})")
            notify = (f"there are songs from: " +
                      ", ".join(notify_parts) )

            if len(notify) < 450:
                await ctx.send(notify)

    @commands.command(aliases=["undo", "cancel", "remove"])
    async def remove_last(self, ctx:commands.Context):
        """remove the last song you requested"""
        await self.bot.db.remove(ctx.author.id)


    @has_perm()
    @commands.command(aliases=["leave_msg", "lm", "send_msg", "sendmsg", "hatemsg"])
    async def leavemsg(self, ctx:commands.Context, receiver: twitchio.User):
        """leave a message for someone: !leavemsg @someone"""
        msg = ctx.message.text
        sender = ctx.author.id
        target = receiver.id
        await self.bot.db.leave_message(sender=sender, reciever=target, msg=msg)

    @has_perm()
    @commands.command(aliases=["get_msg", "gm", "showfeet", "fwends"])
    async def getmsg(self, ctx:commands.Context, sender: twitchio.User):
        """get a message someone left you: !getmsg @username"""
        # sender_id = sender
        receiver = ctx.author
        messages = await self.bot.db.get_message(sender=sender, receiver=receiver)
        for msg in messages:
            await ctx.reply(msg)

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
        response = await self.bot.db.notify(chatter_id=ctx.author.id)

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
        count = await self.bot.db.clear_inbox(ctx.author.id)
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



    @commands.Component.listener("event_message")
    async def seen_chatter(self, payload: twitchio.ChatMessage):
        #if chatter was lurking, remove from lurker list
        self.lurkers.discard(payload.chatter.name)

        if payload.chatter.id in self.seen_users:
            return
        self.seen_users.add(payload.chatter.id)
        response = await self.bot.db.notify(chatter_id=payload.chatter.id)

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



    @commands.command()
    async def claire(self, ctx: commands.Context):
        """say "hi" to Claire!"""
        await ctx.reply("Wavegie")

    @commands.command(aliases=["discord", "community"])
    async def socials(self, ctx: commands.Context) -> None:
        """get all active social links"""
        await ctx.send("discord.gg/DBaUMawHhJ")
        #await ctx.send("other social") --- second await is the only way to print on new lines


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GenCmds(bot))


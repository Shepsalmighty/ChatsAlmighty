import asyncio
from datetime import datetime, timedelta
from unicodedata import category
from warnings import deprecated

import twitchio
from twitchio.ext import commands
from song_req import YoutubeAudio
import mpv
from functools import partial


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
    ESTIMATOR_THRESHOLD = 0.3
    MIN_VID_AGE = 7
    MIN_USERNAME_LEN = 3
    COOLDOWN_UPPER = 5 * 60 * 60 #5hour cooldown
    COOLDOWN_LOWER = 60 #60second cooldown
    SCREAM_INTO_THE_VOID = 20
    def __init__(self, bot: commands.Bot):
        # Passing args is not required...
        # We pass bot here as an example...
        self.bot = bot
        self.derp_trigger = 69
        self.derp_count = 0
        self.leviosah_trigger = 10
        self.leviosah_count = 0
        self.seen_users = set()
        self.those_who_lurk = set()
        self.rejected_songs = set()
        self.alerts_player = mpv.MPV(ytdl=True, video=False)
        # self.alerts_player = mpv.MPV(ytdl=True)

    #TODO - command: !LMGTFY or !LMKTFY - searches the arg and returns the summary/explanation

    @commands.command(aliases=["q"])
    async def queue(self, ctx: commands.Context):
        count = await self.bot.db.queue_len()
        await ctx.send(f"{count} songs in queue")


    @has_perm()
    @commands.command(aliases=["hello", "howdy", "how_are_ya", "rainbow_dicks"])
    async def hi(self, ctx:commands.Context):
        """if you need to be told what this does even i can't help you"""
        # perms_list.append(ctx.chatter.name)
        await ctx.reply(f"Hello, World! Oh, and you {ctx.chatter.mention}")

    @commands.command(aliases=["sit"])
    async def code_cuck(self, ctx:commands.Context):
        await ctx.send(f"@{ctx.channel.name} SIT")

    @commands.command(aliases=["term", "ugly_term", "coolterm", "uglyterm"])
    async def cool_term(self, ctx:commands.Context):
        await ctx.send("get the AWESOME term here https://github.com/Swordfish90/cool-retro-term")

    @has_perm()
    @commands.cooldown(rate=1, per=SCREAM_INTO_THE_VOID, key=commands.BucketType.chatter)
    @commands.command()
    async def listen(self, ctx:commands.Context):
        listen = YoutubeAudio.get("https://www.youtube.com/watch?v=raClhK0dbts")
        file_path = await asyncio.to_thread(lambda: str(listen.audio_file))
        self.alerts_player.play(file_path)
        self.alerts_player.wait_for_playback()

#TODO - download the audio for the !listen commands for faster command speed (probably using
# !sr and taking that self.yt.filepath obj)???
    @has_perm()
    @commands.cooldown(rate=1, per=COOLDOWN_LOWER, key=commands.BucketType.chatter)
    @commands.command(aliases=["song_req", "song_request"])
    async def sr(self, ctx:commands.Context, song: str) -> None:
        """request a song from a youtube link from browser: !sr https://www.youtube.com/watch?v=.....
         songs are auto-rejected if they are over 10mins, have lyrics or the channel is too new.
         pester the streamer if you want your song heard"""
        user = ctx.author.id
        song_object = YoutubeAudio.get(song)

        whale_request = 0

        if song_object.info is not None:
            if ctx.author == self.bot.user:
                await self.bot.db.song_req(user=user, song=song, whale=whale_request)
                return

            song_len_ok = song_object.info.duration < GenCmds.MAX_VID_LEN
            older_than_a_week = (song_object.info.upload_date <
                                 (datetime.now() - timedelta(days=GenCmds.MIN_VID_AGE)))
            enough_subs = song_object.info.channel_follower_count > GenCmds.MIN_SUBSCRIBERS


            if song_len_ok and (older_than_a_week or enough_subs):
                # INFO below is where the audio is downloaded
                no_vocals = not await asyncio.to_thread(
                                     song_object.contains_vocals,
                                     GenCmds.ESTIMATOR_THRESHOLD)

                if no_vocals:
                    await self.bot.db.song_req(user=user, song=song, whale=whale_request)
                    await ctx.reply("song added to queue")
                    return
                await ctx.reply("your song was rejected. reason: song has lyrics")
            else:
                await ctx.reply("your song was rejected. reason: too long (10min max) or video too new/unknown")
            self.rejected_songs.add((ctx.author.name, song))



#INFO - Below command generates a custom point reward id -- maybe useful later
    # @commands.is_owner()
    # @commands.command()
    # async def create_point_redeem_id(self, ctx:commands.Context):
    #     reward = await ctx.broadcaster.create_custom_reward(title="song_perms", cost=5_000,
    #                                                         prompt="pay your song request taxes",
    #                                                         redemptions_skip_queue=True)
    #
    #     print(reward.id)


    @commands.cooldown(rate=1, per=COOLDOWN_UPPER, key=commands.BucketType.chatter)
    @commands.reward_command(id="b8abfe46-7c5d-4e4a-89f2-be4c78a94fd4", invoke_when=commands.RewardStatus.unfulfilled)
    async def whale_song_perms(self, ctx: commands.Context, song: str) -> None:
        user_has_perms = ("""SELECT user_id FROM user_perms WHERE user_id = ? AND has_perms = 1""",
                     (ctx.chatter.id,))

        if user_has_perms[0]:
            await ctx.redemption.refund(token_for=ctx.broadcaster)
            return


        query = """INSERT INTO user_perms(user_id, user_name, has_perms)
                        VALUES(?,?,?)
                        ON CONFLICT(user_id) DO UPDATE
                        SET has_perms = 1;"""

        user = ctx.chatter

        async with self.bot.pool.acquire() as con:
            await con.executemany(query, (user.id, user.name, 1)) # 1 used for True in our sqlite table
            await ctx.redemption.fulfill(token_for=ctx.broadcaster)
            await ctx.send(f"permissions granted to: {user.name}")


    @commands.cooldown(rate=1, per=COOLDOWN_LOWER, key=commands.BucketType.chatter)
    @commands.reward_command(id="dc1514be-75a5-4d48-bde1-8da26bc193bd", invoke_when=commands.RewardStatus.unfulfilled)
    async def whale_req(self, ctx: commands.Context, song: str) -> None:
        """jump to the front of the song_requests queue.
         songs are auto-rejected if they are too long, have lyrics or the channel is too new.
         pester the streamer if you want your song heard"""
        # print(ctx)
        user = ctx.author.id
        song_object = YoutubeAudio.get(song)

        whale_request = 1

        if song_object.info is not None:
            if ctx.author == self.bot.user:
                await self.bot.db.song_req(user=user, song=song, whale=whale_request)
                return

            song_len_ok = song_object.info.duration < GenCmds.MAX_VID_LEN
            older_than_a_week = (song_object.info.upload_date <
                                 (datetime.now() - timedelta(days=GenCmds.MIN_VID_AGE)))
            enough_subs = song_object.info.channel_follower_count > GenCmds.MIN_SUBSCRIBERS

            if song_len_ok and (older_than_a_week or enough_subs):
                # INFO below is where the audio is downloaded
                no_vocals = not await asyncio.to_thread(
                    song_object.contains_vocals,
                    GenCmds.ESTIMATOR_THRESHOLD)

                if no_vocals:
                    await self.bot.db.song_req(user=user, song=song, whale=whale_request)
                    await ctx.redemption.fulfill(token_for=ctx.broadcaster)
                    await ctx.send("song added to queue")
                    return
                await ctx.send("your song was rejected. reason: song has lyrics")
            else:
                await ctx.send("your song was rejected. reason: too long (10min max) or video too new/unknown")
            await ctx.redemption.refund(token_for=ctx.broadcaster)
            self.rejected_songs.add((ctx.author.name, song))

    @commands.command(aliases=["rejected"])
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
    @commands.command(aliases=["send_msg", "sendmsg"])
    async def leavemsg(self, ctx: commands.Context, target: str, *, msg: str):
        """leave a message for someone: !leavemsg @someone"""
        sender = ctx.author.id

        if target.startswith("@"):
            name = await self.bot.fetch_user(login=target.removeprefix("@"))
            if name is None:
                await ctx.send(f"Unknown user: {target}")
                return
            target = name.id

        else:
            names_array = await self.bot.db.lookup_name(name=target)
            if not names_array:
                await ctx.reply(f"Unknown user: {target}")
                return
            if len(names_array) > 1:
                await ctx.reply(f"Msg not sent: multiple users found with {target} name.")
                return
            target = names_array[0][0]

        await self.bot.db.leave_message(sender=sender, receiver=target, msg=msg)


    @commands.command(aliases=["get_msg", "gm", "showfeet"])
    async def getmsg(self, ctx:commands.Context, sender: twitchio.User):
        """get a message someone left you: !getmsg @username"""
        receiver = ctx.author
        messages = await self.bot.db.get_message(sender=sender, receiver=receiver)
        for msg in messages:
            await ctx.reply(msg)

    @getmsg.error
    async def getmsg_error(self, payload: commands.CommandErrorPayload):
        if isinstance(payload.exception, commands.BadArgument):
            return False


    @commands.command(aliases=["mopLurk"])
    async def lurk(self, ctx: commands.Context):
        self.those_who_lurk.add(ctx.author.name)

    @commands.command()
    async def lurkers(self, ctx: commands.Context):
        if len(self.those_who_lurk) == 0:
            await ctx.send("No one hiding in the bushes")
            return
        await ctx.send("Lurkers: " + ", ".join(self.those_who_lurk))

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

    @commands.command(aliases=["clear", "clear_messages", "clear_msgs"])
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
        cmds: list[str] = []

        for cmd in self.bot.unique_commands:
            if isinstance(cmd, commands.RewardCommand):
                continue

            try:
                await cmd._run_guards(ctx, with_cooldowns=False)
            except commands.GuardFailure:
                continue

            cmds.append(f"{ctx.prefix}{cmd.name}")

        joined = " ".join(cmds)
        await ctx.send(f"Commands: {joined}")


    @commands.Component.listener("event_message")
    async def seen_chatter(self, payload: twitchio.ChatMessage):
        #if chatter was lurking, remove from lurker list
        self.those_who_lurk.discard(payload.chatter.name)

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
            custom_emote = " shepsa1DErP" #add your chosen emote to the derp message by default goes at the end line 352
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
            derp_string += custom_emote #add your chosen emote to the end of the derp message
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


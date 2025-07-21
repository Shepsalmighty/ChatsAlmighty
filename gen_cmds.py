import asyncio
from datetime import datetime, timedelta
from unicodedata import category

import twitchio
from twitchio.ext import commands
from song_req import YoutubeAudio
import mpv
from functools import partial

#TODO: figure out a function to work "code cuck" in to the project


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
        self.leviosah_trigger = 10
        self.leviosah_count = 0
        self.seen_users = set()
        self.those_who_lurk = set()
        self.rejected_songs = set()
        self.player = mpv.MPV()
        self.yt = YoutubeAudio
        self.loop = asyncio.get_running_loop()
        self.player.observe_property("track-list", self.schedule_callback)
        self.has_called = False
        self.stop_flag = False


    #TODO implement whale_requests channel point redeem song req with priority // consider renaming song_req
    # to peasant_req

    #TODO fix lurk cmd

    # #TODO:
    # # if the bot detects that the song contains vocals, the bot responds to the request,
    # # asking if the vocals should be disabled. if the requester confirms,
    # # you use another neuronal network to remove the vocals and play clean-version

    #TODO - command: !LMGTFY or !LMKTFY - searches the arg and returns the summary/explanation

    #TODO Sheps, I think I have a suggestion for the bot. Normally when I want to write something
    # to Sea, I type @Sea and press tab... But that of course doesn't work, if Sea isn't here.
    # Can we come up with something smart, so I don't have to remember how the name his spelled?
    # -- add username table for easy look up "WHERE username LIKE '@Sea%';"
    def _play(self, audio_file) -> None:
        self.player.play(filename=audio_file)

    def _skip(self):
        self.player.stop()

    def schedule_callback(self, *t):
        asyncio.run_coroutine_threadsafe(self._callback(*t), loop=self.loop)


    async def _callback(self, event, tracks):
        if not self.has_called:
            self.has_called = True
            return

        if not self.stop_flag:
            print(f"in callback{tracks}")
            if tracks:
                return
            await self.play(self.ctx)
        return


    @commands.is_owner()
    @commands.command()
    async def skip(self, ctx:commands.Context):
        self.player.stop()

    @commands.is_owner()
    @commands.command()
    async def stop(self, ctx:commands.Context):
        self.stop_flag = True
        self.player.stop()


    @commands.command()
    async def play(self, ctx:commands.Context):
        """ clear the played song from DB
            check if there are more songs in queue
            requests the new song to play"""
        self.stop_flag = False
        self.ctx = ctx

        #request 0-2 == row_id, user_id, song_request
        request = await self.bot.db.get_song()

        if request is None:
            await ctx.send("no songs in queue")
            return

        #get username by creating user object from user_id pulled from db and calling name attr
        user_name_from_id = (await ctx.bot.fetch_user(id=request[1])).display_name
        #create YoutubeAudio object
        vid_obj = self.yt.get(request[2])

        await ctx.send(f"now playing {vid_obj.info.title} requested by {user_name_from_id}")
        file_path = await asyncio.to_thread(lambda: str(vid_obj.audio_file))
        await asyncio.to_thread(self._play, file_path)
        # remove song from db/queue
        await self.bot.db.delete_one(request[0])





#TODO skip song option times out the user who requested the skipped song for the len
# of the song they req - GROUP COMMAND commands.group() would be skip and skip.command() would include the timeout

    @commands.command(aliases=["q", "songs", "song_list", "song_queue"])
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


    @has_perm()
    @commands.cooldown(rate=1, per=60, key=commands.BucketType.chatter)
    @commands.command(aliases=["song_req", "song_request", "s_r"])
    async def sr(self, ctx:commands.Context, song: str) -> None:
        """request a song from a youtube link from browser: !sr https://www.youtube.com/watch?v=.....
         songs are auto-rejected if they are too long, have lyrics or the channel is too new.
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

#info test command to generate a custom point reward id maybe useful later
    # @commands.is_owner()
    # @commands.command()
    # async def test_cmd(self, ctx:commands.Context):
    #     reward = await ctx.broadcaster.create_custom_reward(title="whale_song", cost=10_000,
    #                                                         prompt="request a song from a youtube link",
    #                                                         redemptions_skip_queue=True)
    #
    #     print(reward.id)

#TODO create whale song request channel point redeem

    @commands.cooldown(rate=1, per=60, key=commands.BucketType.chatter)
    @commands.reward_command(id="dc1514be-75a5-4d48-bde1-8da26bc193bd")
    async def whale_req(self, ctx: commands.Context, song: str) -> None:
        """jump to the front of the song_requests queue.
         songs are auto-rejected if they are too long, have lyrics or the channel is too new.
         pester the streamer if you want your song heard"""
        print(ctx)
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
                    await ctx.reply("song added to queue")
                    return
                await ctx.reply("your song was rejected. reason: song has lyrics")
            else:
                await ctx.reply("your song was rejected. reason: too long (10min max) or video too new/unknown")
            self.rejected_songs.add((ctx.author.name, song))

    @commands.command(aliases=["reject", "rejected"])
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


import asyncio
from datetime import datetime, timedelta
from unicodedata import category

import twitchio
from twitchio.ext import commands
from song_req import YoutubeAudio
import mpv


class MusicCmds(commands.Component):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rejected_songs = set()
        self.player = mpv.MPV()
        self.yt = YoutubeAudio
        self.loop = asyncio.get_running_loop()
        self.player.observe_property("track-list", self.schedule_callback)
        self.has_called = False
        self.stop_flag = False
        self.current_song : YoutubeAudio | None = None
        self.person_to_rek = None

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


    # @commands.group(name="skip", invoke_fallback=True)
    @commands.is_owner()
    @commands.command()
    async def skip(self, ctx: commands.Context):
        self.player.stop()

    @commands.is_owner()
    @commands.command(aliases=["rekt"])
    async def getrekt(self, ctx: commands.Context):
        if self.current_song is not None and self.person_to_rek is not None:
            timeout_len = self.current_song.info.duration

            await ctx.chatter.timeout_user(user=self.person_to_rek.id,
                                           duration=timeout_len,
                                           moderator=self.bot.user)

            await ctx.send(f"{self.person_to_rek.name} timed out for {timeout_len}, trolls get rolled")

        self.player.stop()

    @commands.is_owner()
    @commands.command()
    async def stop(self, ctx: commands.Context):
        self.stop_flag = True
        self.player.stop()

    @commands.is_owner()
    @commands.command()
    async def play(self, ctx: commands.Context):
        """ clear the played song from DB
            check if there are more songs in queue
            requests the new song to play"""
        self.stop_flag = False
        self.ctx = ctx

        # request 0-2 == row_id, user_id, song_request
        request = await self.bot.db.get_song()

        if request is None:
            await ctx.send("no songs in queue")
            return

        # get username by creating user object from user_id pulled from db and calling name attr
        self.person_to_rek = await ctx.bot.fetch_user(id=request[1])
        user_name_from_id = self.person_to_rek.display_name
        # create YoutubeAudio object
        vid_obj = self.yt.get(request[2])
        self.current_song = vid_obj


        await ctx.send(f"now playing {vid_obj.info.title} requested by {user_name_from_id}")
        file_path = await asyncio.to_thread(lambda: str(vid_obj.audio_file))
        await asyncio.to_thread(self._play, file_path)
        # remove song from db/queue
        await self.bot.db.delete_one(request[0])

async def setup(bot: commands.Bot) -> None:
    await bot.add_component(MusicCmds(bot))
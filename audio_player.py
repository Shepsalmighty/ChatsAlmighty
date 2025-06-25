from nicegui import ui
from song_req import YoutubeAudio as yt
from threading import Thread
from typing import override, Callable

#TODO don't forget to start the thread
# don't forget to uncomment all the nicegui shtuff below the class (IT CURRENTLY BLOCKS THE BOT BTW)
class Player(Thread):

    def __init__(self, playback_finished_callback: Callable[[str], None]):
        super().__init__(daemon=True)
        self.playbackFin = playback_finished_callback

        pass

    @override
    def run(self):
        # calls playback_finished_callback(played_url) after the song was played
        """running the player GUI"""
        # a = ui.audio(yt("https://www.youtube.com/shorts/8XxSdqr8qkQ").audio_file)
        # a.on('ended', lambda _: self.playbackFin(a))
        #
        # ui.button('Play', on_click=a.play)
        # ui.button('Pause', on_click=a.pause)
        # ui.button(on_click=lambda: a.props('muted'), icon='volume_off').props('outline')
        # ui.button(on_click=lambda: a.props(remove='muted'), icon='volume_up').props('outline')
        # ui.button('SKIP', on_click=a.pause) #TODO <----- on click needs to be a db_interface func call

        a.on('ended', lambda _: self.playbackFin(a))
        pass

    def play_song(self, yt_url: str):
        """tells the GUI which song to play"""
        pass

#TODO implement ^^^



# a = ui.audio(yt("https://www.youtube.com/shorts/8XxSdqr8qkQ").audio_file)
# a.on('ended', lambda _: self.playbackFin(a))
#
# ui.button('Play', on_click=a.play)
# ui.button('Pause', on_click=a.pause)
# ui.button(on_click=lambda: a.props('muted'), icon='volume_off').props('outline')
# ui.button(on_click=lambda: a.props(remove='muted'), icon='volume_up').props('outline')
# ui.button('SKIP', on_click=a.pause) #TODO <----- on click needs to be a db_interface func call

#was trying to make a table showing vid info but i gor confuzed
#https://nicegui.io/documentation/section_data_elements
# cols = [{}]
# rows = [{yt.info["title"]}, {yt.info["duration"]}, {yt.info["view_count"]}]
# ui.table()

# ui.run()
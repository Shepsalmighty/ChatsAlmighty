import shutil
import tempfile
import threading
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any

import ffmpeg
import silero_vad as vad
import vlc
import yt_dlp

class YoutubeAudio:
    """
    This class represents the audio and metadata of a youtube video.
    It can be used to download and analyze audio-data from YouTube.

    .. note:: This class creates a cache-directory on your system to store downloaded audio data.
              You can use :func:`YoutubeAudio.clear_file_cache` to fully clear that directory.
    """

    __FILE_CACHE: Path = Path(tempfile.gettempdir()) / "python_youtube_audio"
    """ Path to the cache directory that all instances of this class are using """

    __CACHE_LOCK: threading.RLock = threading.RLock()
    """ Threading lock to make sure that any changes to the cache can be done concurrently """

    __VAD_MODEL: vad.model.OnnxWrapper = vad.load_silero_vad()
    """ Machine-learning model to detect voice activity in audio data """

    def __init__(self, url: str):
        """
        :param url: Youtube video URL
        """

        self.__url: str = url
        # create file-cache directory if it doesn't exist already
        with YoutubeAudio.__CACHE_LOCK:
            if not YoutubeAudio.__FILE_CACHE.is_dir():
                YoutubeAudio.__FILE_CACHE.mkdir(exist_ok=False, parents=False)

    @cached_property
    def info(self) -> dict[str, Any]:
        """
        :return: Dictionary containing all meta-data of this youtube-video
        """

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'format': 'bestaudio/best'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.__url, download=False)
            return info

    @cached_property
    def audio_file(self) -> Path:
        """
        :return: Path to the downloaded audio-file of this youtube-video
        """

        target: Path = YoutubeAudio.__FILE_CACHE / f'{self.info["display_id"]}.wav'
        with YoutubeAudio.__CACHE_LOCK:
            # check if file is already in cache
            if target.is_file():
                return target
            # create a temporary directory which will be deleted after this operation
            with tempfile.TemporaryDirectory(delete=True) as tmpdir:
                download_file: Path = Path(tmpdir).resolve() / f"downloaded.{self.info.get('ext', 'm4a')}"
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'noprogress': True,
                    'format': 'bestaudio/best',
                    'outtmpl': {
                        'default': str(download_file.as_posix())
                    }
                }
                # download the audio from youtube and store it in the file-cache
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.__url])
                    ffmpeg.input(str(download_file.as_posix()), loglevel="error").output(str(target.as_posix()),
                                                                                         ar=16_000).run()
        # return the file-cache path
        return target

    @lru_cache(maxsize=1024)
    def contains_vocals(self, threshold: float) -> bool:
        audio = vad.read_audio(str(self.audio_file), sampling_rate=16_000)
        detections: list[tuple[float, float]] = vad.get_speech_timestamps(audio, YoutubeAudio.__VAD_MODEL,
                                                                          return_seconds=True, threshold=threshold)
        return len(detections) > 0

    @staticmethod
    def clear_file_cache():
        with YoutubeAudio.__CACHE_LOCK:
            shutil.rmtree(YoutubeAudio.__FILE_CACHE)
            YoutubeAudio.__FILE_CACHE.mkdir(exist_ok=False, parents=False)

    def __hash__(self) -> int:
        return hash(self.info["display_id"])


# def play_audio_stream(audio_file: Path):
#     """
#     Plays a provided audio file using VLC
#     :param audio_file: Path to the audio file
#     """
#     instance = vlc.Instance('--input-repeat=-1', '--no-video')
#     player = instance.media_player_new()
#     media = instance.media_new(audio_file)
#     player.set_media(media)
#     player.play()
#
#     input("Press Enter to stop playback...\n")
#     player.stop()
#
#
# def main():
#     # youtube_link: str = input("Enter YouTube URL: ")
#     youtube_link: str = "https://www.youtube.com/watch?v=bv1NJsJyDXI"
#     print("downloading and analyzing audio from YouTube...")
#     audio: YoutubeAudio = YoutubeAudio(youtube_link)
#     if (not audio.contains_vocals(0.2)) or input("this video contains vocals. press P to play anyway: ").lower() == "p":
#         play_audio_stream(audio.audio_file)
#
#     print(audio.info)
#
#
# if __name__ == "__main__":
#     main()
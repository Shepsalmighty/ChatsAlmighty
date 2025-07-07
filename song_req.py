import shutil
import tempfile
import threading
from datetime import datetime
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Annotated, Literal

import ffmpeg
import silero_vad as vad
import vlc
import yt_dlp
from pydantic import BaseModel, BeforeValidator, HttpUrl, ValidationError, conint, constr
from yt_dlp.utils import YoutubeDLError


class Metadata(BaseModel):
    """ Metadata object that belongs to a YouTube video """

    id: constr(min_length=1)
    title: constr(min_length=1)
    thumbnail: HttpUrl
    description: str
    channel_id: constr(min_length=1)
    channel_url: HttpUrl
    duration: conint(gt=0)
    view_count: conint(ge=0)
    age_limit: conint(ge=0)
    webpage_url: HttpUrl
    categories: list[str]
    tags: list[str]
    comment_count: conint(ge=0)
    like_count: conint(ge=0)
    channel: constr(min_length=1)
    channel_follower_count: conint(ge=0)
    upload_date: Annotated[datetime, BeforeValidator(lambda d: datetime.strptime(d, "%Y%m%d"))]
    extractor: Literal["youtube"]
    ext: constr(min_length=1)


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
    def info(self) -> Metadata | None:
        """
        .. note: returns ``None`` if not a valid youtube url

        :return: Dictionary containing all meta-data of this youtube-video
        """

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'format': 'bestaudio/best'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.__url, download=False)
                return Metadata.model_validate(info)
            except YoutubeDLError:
                return None
            except ValidationError as vle:
                print(vle)
                return None

    @cached_property
    def audio_file(self) -> Path | None:
        """
        .. note: returns ``None`` if not a valid youtube url

        :return: Path to the downloaded audio-file of this youtube-video
        """

        if self.info is None:
            return None

        target: Path = YoutubeAudio.__FILE_CACHE / f'{self.info.id}.wav'
        with (YoutubeAudio.__CACHE_LOCK):
            # check if file is already in cache
            if target.is_file():
                return target
            # create a temporary directory which will be deleted after this operation
            with tempfile.TemporaryDirectory(delete=True) as tmpdir:
                download_file: Path = Path(tmpdir).resolve() / f"downloaded.{self.info.ext}"
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
                if not download_file.is_file():
                    return None

                ffmpeg \
                    .input(str(download_file.as_posix()), loglevel="error") \
                    .output(str(target.as_posix()), r=16_000).run()
        # return the file-cache path
        return target

    @lru_cache(maxsize=1024)
    def contains_vocals(self, threshold: float) -> bool:
        """ Returns true if the YouTube video contains vocals

        .. note: lower threshold means more false-positives, higher means more false-negatives
                 (0.2 seems to be a decent value)

        :param threshold: threshold-likelihood for voice detections
        :return: True if vocals were detected
        """

        if self.audio_file is None:
            return False

        audio = vad.read_audio(str(self.audio_file), sampling_rate=16_000)
        detections: list[tuple[float, float]] = vad.get_speech_timestamps(audio, YoutubeAudio.__VAD_MODEL,
                                                                          return_seconds=True, threshold=threshold)
        return len(detections) > 0

    @staticmethod
    def clear_file_cache():
        """ remove all cached audio files """

        with YoutubeAudio.__CACHE_LOCK:
            shutil.rmtree(YoutubeAudio.__FILE_CACHE)
            YoutubeAudio.__FILE_CACHE.mkdir(exist_ok=False, parents=False)

    def __hash__(self) -> int:
        if self.info is None:
            return 0
        return hash(self.info.id)


def play_audio_stream(audio_file: Path):
    """
    Plays a provided audio file using VLC

    :param audio_file: Path to the audio file
    """

    instance = vlc.Instance('--input-repeat=-1', '--no-video')
    player = instance.media_player_new()
    media = instance.media_new(audio_file)
    player.set_media(media)
    player.play()

    input("Press Enter to stop playback...\n")
    player.stop()


# def main():
#     youtube_link: str = input("Enter YouTube URL: ")
#     print("downloading and analyzing audio from YouTube...")
#     audio: YoutubeAudio = YoutubeAudio(youtube_link)
#     if (not audio.contains_vocals(0.2)) or input("this video contains vocals. press P to play anyway: ").lower() == "p":
#         if audio.info is None:
#             print("Invalid link")
#             return
#
#         print(audio.info.model_dump_json(indent=4))
#
#         if audio.audio_file is None:
#             print("Unable to download audio from YouTube")
#             return
#
#         play_audio_stream(audio.audio_file)
#
#
# if __name__ == "__main__":
#     main()

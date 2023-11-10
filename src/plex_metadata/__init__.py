import collections as coll
import subprocess as proc

from .movie_name_lookup import MOVIE_KEYS, SPECIAL_MOVIE_NAMES
from .PlexMetadataException import PlexMetadataException

VIDEO_CODECS = ["h264", "hevc", "mpeg2video", "mpeg4", "vc1"]
AUDIO_CODECS = ["aac", "ac3", "dts", "mp3", "vorbis"]

_PIXEL_SUBTITLE_CODECS = ["dvd_subtitle", "hdmv_pgs_subtitle", "dvb_subtitle", "vobsub"]
_TEXT_SUBTITLE_CODECS = ["mov_text"]

_CODECS_TO_IGNORE = ["", "bin_data", "png"]

DESIRED_VIDEO_CODEC = "hevc"
DESIRED_AUDIO_CODEC = "ac3"
DESIRED_PIXEL_SUBTITLE_CODEC = "dvbsub"
DESIRED_TEXT_SUBTITLE_CODEC = "srt"
LEAVE_SUBTITLES_ALONE = "copy"

CodecSet = coll.namedtuple("CodecSet", ["audio_codec", "video_codec", "subtitle_codec"])


def movie_search_name(movie_name: str):
    if movie_name in movie_name_lookup.MOVIE_KEYS:
        return movie_name_lookup.SPECIAL_MOVIE_NAMES[movie_name]

    return movie_name


def video_codec_to_use(all_codecs: [str]) -> str:
    return DESIRED_VIDEO_CODEC


def audio_codec_to_use(all_codecs: [str]) -> str:
    return DESIRED_AUDIO_CODEC


def subtitle_codec_to_use(all_codecs: [str]) -> str:
    pixel_st: bool = False
    text_st: bool = False
    for codec in all_codecs:
        if codec in _PIXEL_SUBTITLE_CODECS:
            pixel_st = True
        elif codec in _TEXT_SUBTITLE_CODECS:
            text_st = True

    if pixel_st and text_st:
        return LEAVE_SUBTITLES_ALONE
    if pixel_st:
        return DESIRED_PIXEL_SUBTITLE_CODEC
    return DESIRED_TEXT_SUBTITLE_CODEC


def all_codecs_for(file_name: str) -> [str]:
    result: proc.CompletedProcess = proc.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_name,
        ],
        capture_output=True,
    )

    if result.returncode != 0:
        raise PlexMetadataException(f"An error occurred while probing {file_name}. Return code: {result.returncode}")

    return_val: [str] = []

    for codec in str(result.stdout, 'UTF-8').split("\n"):
        return_val.append(codec)

    return return_val


def transcode_codecs_for(file_name: str) -> CodecSet:
    codecs: [str] = all_codecs_for(file_name)
    return CodecSet(audio_codec_to_use(codecs),
                    video_codec_to_use(codecs),
                    subtitle_codec_to_use(codecs)
                    )

import subprocess as proc

from .movie_name_lookup import MOVIE_KEYS, SPECIAL_MOVIE_NAMES
from .PlexMetadataException import PlexMetadataException

_VIDEO_CODECS = ["h264", "hevc"]
_AUDIO_CODECS = ["aac", "ac3", "vorbis"]
_CODECS_TO_IGNORE = [""]


def movie_search_name(movie_name: str):
    if movie_name in movie_name_lookup.MOVIE_KEYS:
        return movie_name_lookup.SPECIAL_MOVIE_NAMES[movie_name]

    return movie_name


def audio_visual_codecs_for(file_name: str) -> (str, str):
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
        raise PlexMetadataException(f"An error occurred while probing {file_name}")

    audio_codec: str | None = None
    video_codec: str | None = None

    for codec in str(result.stdout, 'UTF-8').split("\n"):
        if codec in _AUDIO_CODECS:
            audio_codec = codec
        elif codec in _VIDEO_CODECS:
            video_codec = codec
        elif codec in _CODECS_TO_IGNORE:
            pass
        else:
            raise PlexMetadataException(f"Unknown codec: {codec}")


    return audio_codec, video_codec

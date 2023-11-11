import collections as coll
import configparser as cp
import enum
import http
import logging as log
import optparse as op
import os
import requests as req
import shutil
import subprocess as proc
import sys

import plexapi.library as plib
import plexapi.server as psvr
import plexapi.video as pvid

import plex_metadata as pmd
from plex_metadata.PlexMetadataException import PlexMetadataException

_DEFAULT_SUBTITLE_CODEC = "mov_text"
_TEMP_FILE_NAME = "temp-video.mkv"
_COMMAND_LINE_ARGS = None

PathSet = coll.namedtuple("PathSet", ["file_names", "current_dir", "local_dir", "plex_dir"])


class CommandLineOptions(str, enum.Enum):
    """
    Enumeration of valid command line parameters.
    """
    SUB_DIR = "sub-dir"
    LIB_SECT = "library"
    URL = "url"
    TOKEN = "token"
    ALWAYS = "always_process"


URL_IDX = 0
TOKEN_IDX = 1
SUBDIR_IDX = 2
LIBRARY_IDX = 3
ALWAYS_IDX = 4

config: cp.ConfigParser | None = None
if "__main__" == __name__:
    # SETUP LOGGER BEFORE IMPORTS SO THEY CAN USE THESE SETTINGS
    log.basicConfig(filename="plex-store-metadata.log",
                    filemode="w",
                    format="%(asctime)s %(filename)15.15s %(funcName)15.15s %(levelname)5.5s %(lineno)4.4s %(message)s",
                    datefmt="%Y%m%d %H%M%S"
                    )
    log.getLogger().setLevel(log.INFO)

    # READ SETUP.INI FILE
    log.debug("Reading setup.ini file.")
    config = cp.ConfigParser()
    config.read("setup.ini")


def get_dirs_for(section: str, sub_dir: str) -> (list, list):
    global config

    log.debug(f"Lookup directories for {section}.")
    dir_count = config.getint(section, "folder-count", fallback=0)

    plex_folders: list = []
    local_folders: list = []

    for i in range(1, 1 + dir_count):
        path: str = config.get(section, f"plex-loc-{i:02}")
        full_path: str = os.path.join(path, sub_dir)
        plex_folders.append(full_path)

        path = config.get(section, f"local-dir-{i:02}")
        full_path = os.path.join(path, sub_dir)
        local_folders.append(full_path)

    return plex_folders, local_folders


def parse_command_line() -> dict:
    parser = op.OptionParser()
    parser.add_option("-d", "--dir",
                      dest=CommandLineOptions.SUB_DIR,
                      default="",
                      help="Directory under library to process."
                      )
    parser.add_option("-l", "--lib",
                      dest=CommandLineOptions.LIB_SECT,
                      default="",
                      help="Name of plex library to process."
                      )
    parser.add_option("-u", "--url",
                      dest=CommandLineOptions.URL,
                      default="http://plex.local:32400",
                      help="URL of plex server."
                      )
    parser.add_option("-t", "--token",
                      dest=CommandLineOptions.TOKEN,
                      default="",
                      help="Default connect token."
                      )
    parser.add_option("-a", "--always",
                      dest=CommandLineOptions.ALWAYS,
                      action="store_true",
                      default=False,
                      help="Process item(s) even when not transcoded."
                      )
    options, _ = parser.parse_args()

    return vars(options)


def connect_to_plex(url: str, token: str) -> psvr.PlexServer:
    # CONNECT TO PLEX SERVER
    return psvr.PlexServer(url, token)


def determine_movie_name(file_name: str) -> str:
    dot_idx = file_name.find(".")
    paren_idx = file_name.find("(")
    if paren_idx < 0:
        end_idx = dot_idx
    else:
        end_idx = min(dot_idx, paren_idx)

    movie_name = file_name[:end_idx].strip()
    return pmd.movie_search_name(movie_name)


def is_correct_movie(movie: pvid.Movie, paths: PathSet) -> bool:
    compare_path = os.path.join(paths.current_dir.replace(paths.local_dir, paths.plex_dir), paths.file_names[0])

    for plex_path in movie.locations:
        if plex_path == compare_path:
            return True


def read_command_line() -> (str, str, str, str):
    # READ COMMAND LINE ARGUMENTS
    cl_opts = parse_command_line()
    sub_dir = cl_opts[CommandLineOptions.SUB_DIR]
    library_name = cl_opts[CommandLineOptions.LIB_SECT]
    url = cl_opts[CommandLineOptions.URL]
    token = cl_opts[CommandLineOptions.TOKEN]
    always = cl_opts[CommandLineOptions.ALWAYS]

    return url, token, sub_dir, library_name, always


def is_movie_setup_correctly(m) -> bool:
    if len(m.locations) != 1:
        log.error(f"Found {len(m.locations)} locations for {m.title}. Should be 1!")
        return False

    return True


def verify(paths: PathSet, library_to_search: plib.MovieSection) -> bool:
    if len(paths.file_names) > 1:
        log.error(f"{len(paths.file_names)} files found in {paths.current_dir}")
        return False
    elif len(paths.file_names) == 0:
        return False

    movie_search_name: str = determine_movie_name(paths.file_names[0])
    for m in library_to_search.search(movie_search_name):
        if is_correct_movie(m, paths):
            if is_movie_setup_correctly(m):
                return True

    log.error(f"Could not find a match for movie titled {movie_search_name}")
    return False


def transcode(original_file_name: str, new_file_name: str, codecs: pmd.CodecSet) -> None:
    assert original_file_name.endswith(".mp4") or original_file_name.endswith(".mkv")

    result: proc.CompletedProcess = proc.run(
        [
            "ffmpeg",
            "-y",
            "-i", original_file_name,       # input file
            "-map", "0:v:0",                # Use 1st video stream
            "-map", "0:a",                  # Keep all audio streams
            "-map", "0:s?",                  # Keep all subtitles
            "-c:s", codecs.subtitle_codec,  # subtitle codec (matches original)
            "-c:v", codecs.video_codec,     # video codec (hevc/h.265)
            "-c:a", codecs.audio_codec,     # audio codec (aac)
            new_file_name                   # output file name
        ],
        capture_output=False,
    )

    if result.returncode != 0:
        raise PlexMetadataException(f"An error occurred while transcoding "
                                    + f"{original_file_name}. Return code: {result.returncode}"
                                    )


def transcode_to_desired_codecs(file_name: str) -> str:
    codecs: pmd.CodecSet = pmd.transcode_codecs_for(file_name)
    log.info(f"Transcode {file_name} using {codecs.subtitle_codec} for subs.")
    transcode(file_name, _TEMP_FILE_NAME, codecs)
    log.info("... Transcode complete.  Rename file.")
    try:
        # RENAME NEW FILE TO ORIGINAL NAME (with .mkv extension) AND DELETE ORIGINAL
        backup_file_name: str = f"{file_name}.bak"
        end_file_name: str = file_name.replace(".mp4", ".mkv")

        shutil.move(file_name, backup_file_name)
        shutil.move(_TEMP_FILE_NAME, end_file_name)
        os.remove(backup_file_name)
        log.info("... File successfully renamed.")

        return end_file_name

    except IOError as ioe:
        log.critical("DISK I/O ERROR AFTER TRANSCODING COMPLETE. 2 COPIES OF THIS MOVIES MAY EXIST.")
        log.exception(ioe)
        sys.exit(1)


def needs_transcoding(found_codecs: [str], use_codecs: pmd.CodecSet) -> bool:
    for codec in found_codecs:
        if codec in pmd.VIDEO_CODECS \
                and use_codecs.video_codec != pmd.LEAVE_CODEC_ALONE \
                and codec != use_codecs.video_codec:
            return True
        if codec in pmd.AUDIO_CODECS \
                and use_codecs.audio_codec != pmd.LEAVE_CODEC_ALONE \
                and codec != use_codecs.audio_codec:
            return True
    return False


def save_poster(file_name: str, location: str) -> None:
    url = f"{_COMMAND_LINE_ARGS[URL_IDX]}{location}?X-Plex-Token={_COMMAND_LINE_ARGS[TOKEN_IDX]}"
    response = req.get(url)

    if http.HTTPStatus.OK == response.status_code:
        data = response.content
        log.info(f"... Saving poster information in {file_name}")
        with open(f"{file_name}", "wb") as f:
            f.write(data)
    else:
        raise PlexMetadataException(f"Invalid response from Plex web server while reading poster data. ({location})")


def add_metadata_to_file(file_name: str, movie: pvid.Movie) -> None:
    # Clean up (remove) any existing metadata
    attr_names = (attr for attr in os.listxattr(file_name) if attr.startswith("user."))
    for name in attr_names:
        os.removexattr(file_name, name)

    guids: list = [movie.guid]
    for g in movie.guids:
        guids.append(g.id)

    log.info(f"... ... adding x-attr user.guid to {file_name}, value={guids}")
    os.setxattr(file_name, "user.guid", bytes(str(guids), 'utf-8'))

    # Add changed values as extended file attributes (metadata)
    if len(movie.fields) > 0:
        for f in movie.fields:
            # ADD TO FILE AS EXTENDED ATTRIBUTES
            if "collection" == f.name:
                field_name: str = "collections"
                colls: list = eval("movie.collections")
                field_val: str = str([c.tag for c in colls])
            else:
                field_name: str = f.name
                field_val:str = str(eval(f"movie.{f.name}"))
            log.info(f"... ... adding x-attr user.{field_name} to {file_name} value={field_val}")
            os.setxattr(file_name, f"user.{field_name}", bytes(field_val, "utf-8"))
            if "thumb" == f.name:
                save_poster(f"{file_name}.jpg", field_val)


def process(paths: PathSet, library_to_search: plib.MovieSection) -> None:
    movie_search_name: str = determine_movie_name(paths.file_names[0])
    for movie in library_to_search.search(movie_search_name):
        if is_correct_movie(movie, paths):
            original_file_name: str = os.path.join(paths.current_dir, paths.file_names[0])

            try:
                codecs_in_use: [str] = pmd.all_codecs_for(original_file_name)
                codecs_to_use: pmd.CodecSet = pmd.transcode_codecs_for(original_file_name)

                if needs_transcoding(codecs_in_use, codecs_to_use):
                    new_file_name = transcode_to_desired_codecs(original_file_name)
                    scan_library_files(library_to_search, paths.current_dir)
                    add_metadata_to_file(new_file_name, movie)
                    analyze_video(movie)
                else:
                    log.info(f"No conversion required for {original_file_name}")
                    if _COMMAND_LINE_ARGS[ALWAYS_IDX]:
                        add_metadata_to_file(original_file_name, movie)

            except PlexMetadataException as e:
                log.error(f"{e} ({original_file_name})")
                log.exception(e)


def count_next(last_count: int) -> int:
    new_count = last_count + 1
    if new_count % 100 == 0:
        log.info(f"Process movie {new_count:7,d}.")
    return new_count


def scan_library_files(library_to_scan: plib.LibrarySection, path_to_scan: str) -> None:
    log.info(f"... Scanning library files in {path_to_scan}")
    library_to_scan.update()
    library_to_scan.update(path_to_scan)


def analyze_video(movie: pvid.Movie) -> None:
    log.info(f"... Analyzing {movie.title}")
    # Does not seem to work, but scanning from web app does refresh things.
    movie.analyze()


def main():
    count = 0

    plex = connect_to_plex(_COMMAND_LINE_ARGS[URL_IDX], _COMMAND_LINE_ARGS[TOKEN_IDX]
                           )
    plex_dirs, local_dirs = get_dirs_for(_COMMAND_LINE_ARGS[LIBRARY_IDX],
                                         _COMMAND_LINE_ARGS[SUBDIR_IDX]
                                         )
    library_to_search: plib.MovieSection = plex.library.section(_COMMAND_LINE_ARGS[LIBRARY_IDX])

    # PROCESS EACH FOLDER FROM THE LIBRARY SECTION
    for idx, nfs_dir in enumerate(local_dirs):
        # GET A LOCAL DIRECTORY AND MATCHING PLEX DIRECTORY.
        plex_dir = plex_dirs[idx]
        # WALK THE (nfs) DIRECTORY TREE ON LOCAL MACHINE
        for root, dirs, files in os.walk(nfs_dir):
            dirs.sort()
            vid_files = list(filter(lambda fn: fn.endswith(".mp4") or fn.endswith(".mkv"), files))

            paths = PathSet(vid_files, root, nfs_dir, plex_dir)
            if verify(paths, library_to_search):
                count = count_next(count)
                process(paths, library_to_search)

    log.info(f"Processed a total of {count} movies.  See this log for details.")


if __name__ == "__main__":
    _COMMAND_LINE_ARGS = read_command_line()
    main()

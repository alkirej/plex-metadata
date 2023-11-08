import collections as coll
import configparser as cp
import enum
import logging as log
import optparse as op
import os
import sys

import plexapi.library as plib
import plexapi.server as psvr
import plexapi.video as pvid

import plex_metadata as pmd

PathSet = coll.namedtuple("PathSet", ["file_names", "current_dir", "local_dir", "plex_dir"])

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


def get_dirs_for(section: str) -> (dict, dict):
    global config

    log.debug(f"Lookup directories for {section}.")
    dir_count = config.getint(section, "folder-count", fallback=0)

    plex_folders = []
    local_folders = []

    for i in range(1, 1 + dir_count):
        plex_folders.append(config.get(section, f"plex-loc-{i:02}"))
        local_folders.append(config.get(section, f"local-dir-{i:02}"))

    return plex_folders, local_folders


class CommandLineOptions(str, enum.Enum):
    """
    Enumeration of valid command line parameters.
    """
    SUB_DIR = "sub-dir"
    LIB_SECT = "library"
    URL = "url"
    TOKEN = "token"


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
    options, _ = parser.parse_args()

    return vars(options)


def connect_to_plex(url: str, token: str) -> psvr.PlexServer:
    # CONNECT TO PLEX SERVER
    # url: str = "http://matrix.local:32400"
    # token: str = "juJUVz7rXs3MtoyeEsBm"
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


# def is_correct_movie(movie: pvid.Movie, current_dir: str, file_name: str, local_dir: str, plex_dir: str) -> bool:
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

    return url, token, sub_dir, library_name


def is_movie_setup_correctly(m) -> bool:
    if len(m.locations) != 1:
        log.error(f"Found {len(m.locations)} locations for {m.title}. Should be 1!")
        return False

    return True


def count_next_movie(last_count: int) -> int:
    new_count = last_count + 1
    if new_count % 100 == 0:
        log.info(f"Process movie {new_count:7,d}.")
    return new_count


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


def process(paths: PathSet, library_to_search: plib.MovieSection):
    movie_search_name: str = determine_movie_name(paths.file_names[0])
    for m in library_to_search.search(movie_search_name):
        if is_correct_movie(m, paths):
            # ENCODE 265 (if necessary)
            # REPLACE FILE (if encoding changed)
            # STORE GUIDS AS FILE ATTRIBUTES
            # STORE ANY CHANGED FIELDS AS FILE ATTRIBUTES

            for f in m.fields:
                # ADD TO FILE AS EXTENDED ATTRIBUTES
                pass
            break


def count_next(last_count: int) -> int:
    new_count = last_count + 1
    if new_count % 100 == 0:
        log.info(f"Process movie {new_count:7,d}.")
    return new_count


def main():
    count = 0

    url, token, sub_dir, library_name = read_command_line()
    plex = connect_to_plex(url, token)
    plex_dirs, local_dirs = get_dirs_for(library_name)
    library_to_search: plib.MovieSection = plex.library.section(library_name)

    # PROCESS EACH FOLDER FROM THE LIBRARY SECTION
    for idx, nfs_dir in enumerate(local_dirs):
        # GET A LOCAL DIRECTORY AND MATCHING PLEX DIRECTORY.
        start_dir = os.path.join(nfs_dir, sub_dir)
        plex_dir = plex_dirs[idx]

        # WALK THE (nfs) DIRECTORY TREE ON LOCAL MACHINE
        for root, _, files in os.walk(start_dir):
            paths = PathSet(files, root, nfs_dir, plex_dir)
            if verify(paths, library_to_search):
                count = count_next(count)
                process(paths, library_to_search)
                if count == 555:
                    sys.exit()

    log.info(f"Processed a total of {count} movies.  See this log for details.")


if __name__ == "__main__":
    main()

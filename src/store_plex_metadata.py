import enum
import optparse as op
import os
import sys

import plexapi.library as plib
import plexapi.server as psvr

import plex_metadata as pmd


class CommandLineOptions(str, enum.Enum):
    """
    Enumeration of valid command line parameters.
    """
    PLEX_DIR = "plex-dir"
    LOCAL_DIR = "local-dir"


def parse_command_line() -> dict:
    parser = op.OptionParser()
    parser.add_option("-p", "--plex-dir",
                      dest=CommandLineOptions.PLEX_DIR,
                      help="Root dir to search on plex server."
                      )
    parser.add_option("-d", "--dir",
                      dest=CommandLineOptions.LOCAL_DIR,
                      help="Local dir to process on local machine."
                      )
    options, _ = parser.parse_args()

    return vars(options)


def main() -> None:
    # CONNECT TO PLEX SERVER
    baseurl = "http://matrix.local:32400"
    token = "juJUVz7rXs3MtoyeEsBm"
    plex: psvr.PlexServer = psvr.PlexServer(baseurl, token)

    # GET REFERENCE TO THE MOVIES LIBRARY ON PLEX SERVER
    movies: plib.MovieSection = plex.library.section("Movies")

    # GET DIRECTORIES TO PROCESS FROM COMMAND LINE
    cl_opts = parse_command_line()

    start_dir = cl_opts[CommandLineOptions.LOCAL_DIR]
    plex_dir = cl_opts[CommandLineOptions.PLEX_DIR]

    count = 0
    for root, dirs, files in os.walk(start_dir):
        dirs.sort()

        found_match = False
        for file_name in files:
            dot_idx = file_name.find(".")
            paren_idx = file_name.find("(")
            if paren_idx < 0:
                end_idx = dot_idx
            else:
                end_idx = min(dot_idx, paren_idx)

            movie_name = file_name[:end_idx].strip()
            movie_search_name = pmd.movie_search_name(movie_name)

            for m in movies.search(movie_search_name):
                for plex_path in m.locations:
                    compare_path = os.path.join(root.replace(start_dir, plex_dir), file_name)

                    if plex_path == compare_path:
                        found_match = True
                    if found_match:
                        break

                if found_match:
                    break

            if not found_match:
                print(movie_name)
                count += 1
                if count == 10:
                    sys.exit()
                # raise Exception


if __name__ == "__main__":
    main()

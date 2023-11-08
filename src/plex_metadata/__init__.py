from .movie_name_lookup import MOVIE_KEYS, SPECIAL_MOVIE_NAMES


def movie_search_name(movie_name: str):
    if movie_name in movie_name_lookup.MOVIE_KEYS:
        return movie_name_lookup.SPECIAL_MOVIE_NAMES[movie_name]

    return movie_name

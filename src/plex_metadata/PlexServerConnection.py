
import plexapi.myplex as plex
import plexapi.server


class PlexServerConnection:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(PlexServerConnection, cls).__new__(cls)

        return cls._instance

    def __init__(self, server_name: str, username: str, password: str) -> None:
        self._account = None
        self.connection: plexapi.server.PlexServer | None = None

        self._server_name = server_name
        self._username = username
        self._password = password

        self.make_connection()

    def make_connection(self):
        self._account = plex.MyPlexAccount(self._username, self._password)
        print(self._account.authToken)
        self.connection = self._account.resource(self._server_name).connect()

        return self.connection

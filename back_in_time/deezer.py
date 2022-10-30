import sys
import requests
from typing import Type
from back_in_time import BillBoardTrack

# APP_SETTINGS_FILE = "./data/settings.json"


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class User:

    def __init__(self, id_: int, name_: str, email_: str):
        self.id = id_
        self.name = name_
        self.email = email_


class Artist:

    def __init__(self, id_, name_):
        self.id = id_
        self.name = name_


class Track:

    def __init__(self, id_: int = None, title_: str = None, artist_: Type[Artist] = None):
        self.id = id_
        self.title = title_
        self.artist = artist_


class Playlist:

    def __init__(self, id_: int, title_: str):
        self.id = id_
        self.title = title_


class Deezer:

    def __init__(self, deezer_token: str):
        self.oauth_token = {
            "access_token": deezer_token,
        }
        self.DEEZER_BASE_ENDPOINT = "https://api.deezer.com"
        self.session = requests.Session()
        self.user = self.get_user_data()

    def request(self, method: str, api_path: str, api_params: dict = None) -> dict:
        if api_params is None:
            api_params = self.oauth_token
        else:
            api_params = self.oauth_token | api_params

        response = self.session.request(
            method=method,
            url=f"{self.DEEZER_BASE_ENDPOINT}{api_path}",
            params=api_params,
        )

        response.raise_for_status()
        json_data = response.json()
        return json_data

    def get_user_data(self) -> Type[User]:
        get_user_path = f"/user/me"

        try:
            get_user_data_output = self.request(method="GET", api_path=get_user_path)
        except:
            print(f"\n{bcolors.FAIL}ERROR - No data found for the specified user token.{bcolors.ENDC}\n")
            sys.exit(1)
        else:
            # Extract User data
            user_id = get_user_data_output["id"]
            user_name = get_user_data_output["name"]
            user_email = get_user_data_output["email"]

            user = User(user_id, user_name, user_email)

            return user

    def search_track(self, track_: Type[BillBoardTrack]) -> Type[Track]:
        search_track_path = "/search"
        search_track_params = {
            "q": f"track:'{track_.title}' artist:'{track_.artist}'"
        }

        # Skip BillBoardTrack (return as None) if an exception is raised
        try:
            search_track_output = self.request(method="GET",
                                               api_path=search_track_path,
                                               api_params=search_track_params)
        except:
            return Track()

        # If BillBoardTrack is not found try searching by title only
        # Otherwise skip BillBoardTrack (return as None)
        if search_track_output["total"] == 0:
            try:
                search_track_params = {
                    "q": f"track:'{track_.title}'"
                }

                search_track_output = self.request(method="GET",
                                                   api_path=search_track_path,
                                                   api_params=search_track_params)
                track = search_track_output["data"][0]
            except IndexError:
                return Track()
        else:
            track = search_track_output["data"][0]

        # Extract Artist data
        artist_id = track["artist"]["id"]
        artist_name = track["artist"]["name"]
        artist = Artist(artist_id, artist_name)

        # Extract Track data
        track_id = track["id"]
        track_title = track["title"]

        return Track(track_id, track_title, artist)

    def create_playlist(self, title_: str) -> Type[Playlist]:
        create_playlist_path = f"/user/{self.user.id}/playlists"
        create_playlist_params = {
            "title": title_
        }

        create_playlist_output = self.request(method="POST",
                                              api_path=create_playlist_path,
                                              api_params=create_playlist_params)

        # Extract Playlist data
        playlist_id = create_playlist_output["id"]
        playlist = Playlist(playlist_id, title_)

        return playlist

    def add_tracks_playlist(self, playlist_: Type[Playlist], tracks_: list[Type[Track]]) -> bool:
        add_tracks_playlist_path = f"/playlist/{playlist_.id}/tracks"
        add_tracks_playlist_params = {
            # slicing resulting string to remove last space and comma
            "songs": (''.join([f"{track.id}, " for track in tracks_]))[:-2]
        }

        add_tracks_playlist_output = self.request(method="POST",
                                                  api_path=add_tracks_playlist_path,
                                                  api_params=add_tracks_playlist_params)

        return add_tracks_playlist_output

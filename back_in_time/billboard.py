import requests
from typing import Type
from bs4 import BeautifulSoup


class BillBoardTrack:

    def __init__(self, artist_, title_):
        self.artist = artist_
        self.title = title_


class BillBoard:

    def __init__(self):
        self.BILLBOARD_BASE_URL = "https://www.billboard.com/charts/hot-100/"
        self.tracks: list[Type[BillBoardTrack]] = []

    def get_hot_100_by_date(self, user_date: str):
        custom_url = f"{self.BILLBOARD_BASE_URL}{user_date}"
        response = requests.get(custom_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        entries = soup.select(selector="div .o-chart-results-list-row-container")

        for entry in entries:
            title = entry.find(name="h3", attrs={"id": "title-of-a-story"}).text.strip()
            artist = entry.find(name="h3", attrs={"id": "title-of-a-story"}).find_next().text.strip()
            track = BillBoardTrack(artist, title)
            self.tracks.append(track)

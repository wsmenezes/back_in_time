# Standard library imports
from multiprocessing import Process
import os
import sys
from typing import Type, List
import webbrowser

# Third party imports
from flask import Flask, redirect, request, render_template
import json
from redislite import Redis
import requests

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib as glib

# Local application imports
from back_in_time import BillBoard
from back_in_time import Deezer, Track


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


# ---- CONSTANTS ---- #
APP_SETTINGS_FILE = "./data/settings.json"

# ---- GLOBALS ---- #
'''
settings keys:

["APP_NAME"]
["DEEZER_APP_ID"]
["DEEZER_APP_SECRET"] 
["DEEZER_APP_PERMS"]
["DEEZER_WIDGET_URL"]
["DEEZER_AUTH_URL"]
["DEEZER_TOKEN_URL"]
["DEEZER_REDIRECT_URI"]
["FLASK_SERVER_URL"]
'''
app_settings: dict

'''
redis keys:

["token"]
["playlist_name"]
["playlist_date"]
["playlist_ready"]
["flask_stage"]
["flask_error"]
'''
"""
Due to Pyinstaller peculiarities redislite.Client.RedisMixin._start_redis().redis_executable
should be changes as follows:

from: redis_executable = 'redis-server'
to: redis_executable = './bin/redis-server' 
"""
redis_conn = Redis("./data/vars.db")

app = Flask("Back in Time")
flask_server = Process(target=app.run)


def load_app_settings():
    global app_settings

    try:
        with open(APP_SETTINGS_FILE, "r") as settings_file:
            app_settings = json.load(settings_file)
    except FileNotFoundError:
        print(f"\n{bcolors.FAIL}ERROR - app settings file is missing.{bcolors.ENDC}\n")
        sys.exit(1)
    except json.decoder.JSONDecodeError:
        print(f"\n{bcolors.FAIL}ERROR - app settings file is corrupted. Check the file structure and run again.{bcolors.ENDC}\n")
        sys.exit(1)


@app.route('/', methods=['GET'])
def default():
    return render_template('welcome.html')  # -> HTML meta redirect to /authenticate


@app.route('/authenticate', methods=['GET'])
def authenticate():
    # Set Flask stage
    redis_conn.set("flask_stage", "Deezer Authentication...")

    # TODO Test authentication removing app access from my deezer account
    url = (f"{app_settings['DEEZER_AUTH_URL']}?app_id={app_settings['DEEZER_APP_ID']}"
           f"&redirect_uri={app_settings['DEEZER_REDIRECT_URI']}&perms={app_settings['DEEZER_APP_PERMS']}")
    return redirect(url)  # -> URL forced redirect for Deezer callback to /deezer/login


@app.route('/deezer/login', methods=['GET'])
def deezer_login():
    # retrieve the authorization code given in the url
    code = request.args.get('code')

    token_params = {
        "app_id": app_settings['DEEZER_APP_ID'],
        "secret": app_settings['DEEZER_APP_SECRET'],
        "code": code,
        "output": "json"
    }
    response = requests.get(url=app_settings['DEEZER_TOKEN_URL'], params=token_params)
    response.raise_for_status()

    # Deezer replies in a custom way if it's not a good code.
    if response.text == 'wrong code':
        error_message = f"ERROR - Please check Deezer oauth permissions."
        redis_conn.set("flask_error", error_message)
        return redirect(f"{app_settings['FLASK_SERVER_URL']}/error?error_message={error_message}")

    response = response.json()
    # Retrieve and commit access token into Redis
    redis_conn.set("token", response['access_token'])

    return redirect(f"{app_settings['FLASK_SERVER_URL']}/date_select")


@app.route('/date_select', methods=['GET'])
def date_select():
    # Set Flask stage
    redis_conn.set("flask_stage", "Playlist date selection...")

    return render_template('selection.html')  # -> HTML form submission to /progress


@app.route('/progress', methods=['GET'])
def progress():
    # Set Flask stage
    redis_conn.set("flask_stage", "Building Playlist...")

    playlist_date = request.args.get("playlist_date")
    # Retrieve and commit playlist_date into Redis
    redis_conn.set("playlist_date", playlist_date)

    return render_template('progress.html')  # -> HTML meta redirect to /create_playlist


@app.route('/create_playlist', methods=['GET'])
def create_playlist():
    billboard = BillBoard()
    deezer = Deezer(deezer_token=redis_conn.get("token"))
    deezer_tracks: List[Type[Track]] = []

    playlist_date: str = (redis_conn.get("playlist_date")).decode('utf-8')

    billboard.get_hot_100_by_date(playlist_date)

    print("\n Retrieving playlist tracks: \n")
    for billboard_track in billboard.tracks:
        deezer_track = deezer.search_track(billboard_track)
        # Track not found in Deezer or duplicated track in BillBoard list
        if deezer_track.id is not None and deezer_track.id not in [track.id for track in deezer_tracks]:
            print(f"{deezer_track.artist.name} : {deezer_track.title}")
            deezer_tracks.append(deezer_track)
    print("\n Playlist tracks retrieved! \n")

    # Create Playlist
    playlist = deezer.create_playlist(title_=f"{app_settings['APP_NAME']} to {playlist_date}")
    redis_conn.set("playlist_name", playlist.title)

    # Add tracks to Playlist
    redis_conn.set("playlist_ready", str(deezer.add_tracks_playlist(playlist, deezer_tracks)))

    if redis_conn.get("playlist_ready").decode("utf-8") == "True":
        return redirect(f"{app_settings['FLASK_SERVER_URL']}/play?id={playlist.id}")
        print(f"\n{bcolors.OKBLUE}Playlist '{playlist.title}' successfully created! Enjoy!{bcolors.ENDC}\n")
    else:
        print(f"\n{bcolors.FAIL}ERROR - Playlist '{playlist.title}' could not be created. "
              f"Please check Deezer oauth permissions.{bcolors.ENDC}\n")
        redis_conn.set("flask_error", f"ERROR - Playlist '{playlist.title}' could not be created. "
                                      f"Please check Deezer oauth permissions.")
        error_message = f"ERROR - Playlist '{playlist.title}' could not be created. \n" \
                        f"Please check Deezer oauth permissions."
        return redirect(f"{app_settings['FLASK_SERVER_URL']}/error?error_message={error_message}")


@app.route('/play', methods=['GET'])
def play():
    id_ = request.args.get('id')

    url = f"{app_settings['DEEZER_WIDGET_URL']}/{id_}"

    return render_template('player.html', playlist_url=url)


@app.route('/error', methods=['GET'])
def error():
    error_message_ = request.args.get('error_message')

    return render_template('error.html', error_message=error_message_)


@Gtk.Template(filename=f"./ui/back_in_time.ui")
class MainWindow(Gtk.ApplicationWindow):
    __gtype_name__ = "mainWindow"

    flask_launcher_button = Gtk.Template.Child()
    status_bar = Gtk.Template.Child()
    progress_spinner = Gtk.Template.Child()
    quit_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # config status bar context
        self.status_bar_ctx = self.status_bar.get_context_id("status_bar")

        flask_server.start()

    def check_flask_progress(self):
        if redis_conn.get("playlist_ready") is not None and \
                redis_conn.get("playlist_ready").decode("utf-8") == "True":
            self.flask_launcher_button.set_sensitive(True)
            self.quit_button.set_sensitive(True)
            self.status_bar.push(self.status_bar_ctx, f"Playlist '{redis_conn.get('playlist_name').decode('utf-8')}' "
                                                      f"ready. Enjoy!")
            self.progress_spinner.stop()

            # Delete ["playlist_ready"] and ["flask_stage"] Redis keys, prepping for next run
            redis_conn.delete("playlist_ready")
            redis_conn.delete("flask_stage")
        elif redis_conn.get("flask_stage") is not None:
            # Update Status Bar with Flask status
            self.status_bar.push(self.status_bar_ctx, redis_conn.get("flask_stage").decode("utf-8"))
            glib.timeout_add_seconds(1, self.check_flask_progress)
        else:
            glib.timeout_add_seconds(1, self.check_flask_progress)

        if redis_conn.get("flask_error") is not None:
            # Update Status Bar with Flask error message and interrupt GUI timeout
            self.status_bar.push(self.status_bar_ctx, redis_conn.get("flask_error").decode("utf-8"))
            self.quit_button.set_sensitive(True)
            self.progress_spinner.stop()

    def safe_app_exit(self):
        # Purge Redis db on exit
        redis_conn.flushall()
        flask_server.terminate()
        flask_server.join()
        Gtk.main_quit()

    @Gtk.Template.Callback()
    def on_flask_launcher_pressed(self, *args):
        # Linux Chrome path
        chrome_path = '/usr/bin/google-chrome %s'
        webbrowser.get(chrome_path).open(app_settings['FLASK_SERVER_URL'])

        self.flask_launcher_button.set_sensitive(False)
        self.quit_button.set_sensitive(False)
        self.status_bar.push(self.status_bar_ctx, "Follow the steps in your browser...")
        self.progress_spinner.start()
        glib.timeout_add_seconds(1, self.check_flask_progress)

    @Gtk.Template.Callback()
    def on_mainWindow_destroy(self, *args):
        self.safe_app_exit()

    @Gtk.Template.Callback()
    def on_quit_button_pressed(self, *args):
        self.safe_app_exit()


def main():
    load_app_settings()
    print(f"Startup settings: \n {app_settings} \n")
    print(f"Binary temp dir: \n {os.path.abspath(os.path.dirname(__file__))} \n")
    window = MainWindow(title=f"{app_settings['APP_NAME']}")
    window.show()
    Gtk.main()


if __name__ == '__main__':
    main()

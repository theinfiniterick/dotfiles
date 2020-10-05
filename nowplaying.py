#!/usr/bin/python

"""
TODO: How often should spotify token be updated?
TODO: Config file
TODO: Ingtegrate albumartist
"""

import argparse
import mpd
import mutagen
import notify2
import os.path
import re
import requests
import signal
import sys
import urllib.request

import gi.repository
from gi.repository import Gio
gi.require_version("GdkPixbuf", "2.0")
from gi.repository.GdkPixbuf import Pixbuf

PROG = 'nowplaying'
# api credentials
SPOTIFY_CLIENT_ID = '3ad71cf0ae544e7e935927e5d9a5cbad'
SPOTIFY_CLIENT_SECRET = '862905d9380645a9ba29789308d795d5'
# mpd client
MPD_BIND_ADDRESS = '127.0.0.1'
MPD_BIND_PORT = 6600
MPD_PASSWORD = None
MPD_TIMEOUT = None
MPD_IDLE_TIMEOUT = None
# notification
NOTIFY_DEFAULT_IMAGE = '/home/user/images/icon/pacman/red.png'
NOTIFY_ID = 999999
NOTIFY_TIMEOUT = 1500
NOTIFY_URGENCY = 0  # 0 = low, 1 = normal, 2 = critical


class TrackInfo:

    def __init__(self, path=None, token=None, mpd_data=None):

        if not path:
            print("error: no path specified")
            return None
        if not os.path.exists(path):
            print(f"error: path '{path}' does not exist.")
            return None
        if not os.path.isfile(path):
            print(f"error: path '{path}' is not a file.")
            return None
        if not token:
            print("error: no spotify token specified.")
            return None
        if not mpd_data:
            print("error: mpd_data not found.")
            return None

        self.path = path
        self.token = token

        self.props = self.gather_properties(mpd_data)

    def __repr__(self):
        return f"TrackInfo('{self.path}')"

    def gather_properties(self, mpd_data):
        """
        Gather song properties from metadata, filename,
        embedded image data, local image file, and api data.
        Fields are title, artist, album, data,
        image_data, image_path and image_url.
        """

        props = {}

        if 'title' in mpd_data:
            props['title'] = mpd_data['title']
        if 'artist' in mpd_data:
            props['artist'] = mpd_data['artist']
        if 'album' in mpd_data:
            props['album'] = mpd_data['album']
        if 'date' in mpd_data:
            props['date'] = mpd_data['date']

        # if title, artist or album still missing, append data parsed from filename
        if props.keys() < {'title', 'artist', 'album'}:

            filename_dict = self.get_filename_data()

            if 'title' not in props and 'title' in filename_dict:
                props['title'] = filename_dict['title']
            if 'artist' not in props and 'artist' in filename_dict:
                props['artist'] = filename_dict['artist']
            if 'album' not in props and 'album' in filename_dict:
                props['album'] = filename_dict['album']

        # append embedded image data to properties if it exists
        image_data = self.get_embedded_image_data()
        if image_data:
            props['image_data'] = image_data

        # if image data not in properties, append local image path to properties if it exists
        if 'image_data' not in props:
            image_path = self.get_local_image_path()
            if image_path:
                props['image_path'] = image_path

        # if artist in properties but album or image data and path are still missing, query api and append it's data to properties
        if 'artist' in props and ('album' in props or 'title' in props) and ('album' not in props or ('image_data' not in props and 'image_path' not in props)):

            api_dict = None

            # if album in properties, query api for album data
            if 'album' in props:

                api_dict = self.get_spotify_album_data(artist=props['artist'], album=props['album'])

                # if api data not found and artist contains underscores, try query by replacing underscores with slashes
                if not api_dict and 'artist' in props and props['artist'].find('_') > 0:
                    api_dict = self.get_spotify_album_data(artist=props['artist'].replace('_', '/'), album=props['album'])

            # else if title in properties, query api for track data
            elif 'title' in props:

                api_dict = self.get_spotify_track_data(artist=props['artist'], track=props['title'])

                # if api data not found and artist contains underscores, try query by replacing underscores with slashes
                if not api_dict and 'artist' in props and props['artist'].find('_') > 0:
                    api_dict = self.get_spotify_track_data(artist=props['artist'].replace('_', '/'), track=props['title'])

            if api_dict:

                # if api returned data then clear any pre-existing album, date or image properties
                if 'album' in props:
                    del props['album']
                if 'date' in props:
                    del props['date']
                if 'image_data' in props:
                    del props['image_data']
                if 'image_path' in props:
                    del props['image_path']

                # append api data to properties
                if 'album' in api_dict:
                    props['album'] = api_dict['album']
                if 'date' in api_dict:
                    props['date'] = api_dict['date']
                if 'image_url' in api_dict:
                    props['image_url'] = api_dict['image_url']

        # clean album name of unwanted substrings
        if 'album' in props:
            props['album'] = self._clean_album_string(props['album'])

        # clean date of all data but year if possible
        if 'date' in props:
            props['date'] = self._clean_date_string(props['date'])

        return props

    def _is_album_name_unwanted(self, album=None):
        """
        Check if album name string contains any unwanted substrings.
        """

        unwanted_substrings = ('best of', 'greatest hits', 'collection', 'b-sides')

        return any([substring in album.lower() for substring in unwanted_substrings])

    def _split_filename(self, filename=None):
        """
        Returns a list of values by splitting filename at delimiters.
        """

        # get filename without extension
        string = os.path.splitext(filename)[0]

        # dictionary of patterns to protect from split
        ignore_patterns = [
            {'initial': 'Ep. ', 'replace': '((EPDOT))'},
            {'initial': 'Dr. ', 'replace': '((DOCTORDOT))'},
            {'initial': 'Jr. ', 'replace': '((JUNIORDOT))'},
            {'initial': 'Sr. ', 'replace': '((SENIORDOT))'},
            {'initial': 'Mr. ', 'replace': '((MISTERDOT))'},
            {'initial': 'Mrs. ', 'replace': '((MISSESDOT))'},
            {'initial': 'Vol. ', 'replace': '((VOLDOT))'}
        ]

        # temporarily replace protected patterns so they do not affect the split
        for i in range(len(ignore_patterns)):
            string = string.replace(ignore_patterns[i]['initial'], ignore_patterns[i]['replace'])

        # replace '00. name' with '00 - name'
        string = re.sub(r"(?<=^\d{2})\.\s+", " - ", string)

        # split sections into a list
        string_list = re.split('\\s+-\\s+', string)

        # replace all protected patterns with their original values
        cleaned_string_list = []
        for var in string_list:
            for i in range(len(ignore_patterns)):
                var = var.replace(ignore_patterns[i]['replace'], ignore_patterns[i]['initial'])
            cleaned_string_list.append(var.strip())

        return cleaned_string_list

    def get_filename_data(self):
        """
        Returns a dictionary of data parsed from the filename (title, album, artist).
        """

        filename = os.path.basename(self.path)

        unassigned_values = self._split_filename(filename)
        unassigned_fields = ['artist', 'album', 'title']
        found_data = {}

        # remove any track numbers from unassigned_values
        for val in unassigned_values:
            if re.match(r'^\d{1,2}$', val):
                unassigned_values.remove(val)
                break

        # if there are more unassigned fields than unassigned values and album is in unassiged fields then remove it
        if 'album' in unassigned_fields and len(unassigned_fields) > len(unassigned_values):
            unassigned_fields.remove('album')

        # if there are still more unassigned values than unassigned fields
        if len(unassigned_values) > len(unassigned_fields):

            # remove first unassigned value until there are the same number of unassigned values and unassigned fields
            while len(unassigned_values) > len(unassigned_fields):
                del unassigned_values[0]

        # assign remaining unassigned_values to remaining unassigned_fields
        for i in range(len(unassigned_values)):
            found_data[unassigned_fields[-1]] = unassigned_values[-1]
            unassigned_fields.remove(unassigned_fields[-1])
            unassigned_values.remove(unassigned_values[-1])

        return found_data

    def get_embedded_image_data(self):

        mutagen_object = mutagen.File(self.path)

        # 3 = Cover (front), 2 = Other file icon, 1 = 32x32 pixel PNG file icon, 0 = Other, 18 = Illustration
        types = [3, 2, 1, 0, 18]
        list = []

        if mutagen_object and mutagen_object.tags and len(mutagen_object.tags.values()) > 0:

            if mutagen_object.mime[0] == "audio/mp3":

                for type in types:
                    for tag in mutagen_object.tags.values():
                        if tag.FrameID == 'APIC' and int(tag.type) == type:
                            return tag.data

            elif mutagen_object.mime[0] == "audio/mp4":

                if 'covr' in mutagen_object.tags.keys():
                    return mutagen_object.tags['covr'][0]

            elif mutagen_object.mime[0] == "audio/flac":

                for type in types:
                    for tag in mutagen_object.pictures:
                        if tag.type == type:
                            return tag.data

    def _get_folder_image(self, folder):

        filenames = [
            "cover", "Cover", "front", "Front",
            "folder", "Folder", "thumb", "Thumb", "album", "Album",
            "albumart", "AlbumArt", "albumartsmall", "AlbumArtSmall"
        ]
        extensions = ["png", "jpg", "jpeg", "gif", "svg", "bmp", "tif", "tiff"]

        # check for the existence of a file in current folder that macthes a combination of filenames and extensions
        for name in filenames:
            for ext in extensions:
                path = folder + '/' + name + '.' + ext
                if os.path.exists(path):
                    return path

    def get_local_image_path(self):

        matching_folder_names = [r'^disc\s?\d+.*$', r'^cd\s?\d+.*$', r'^dvd\s?\d+.*$', r'^set\s?\d+.*$', 'mp3', 'm4a', 'flac', 'wma']

        # set initial value of current folder to the directory of the audio file
        current_folder_path = os.path.dirname(self.path)
        current_folder_name = os.path.basename(current_folder_path)

        # append initial folder to matching_folder_names
        if current_folder_name not in matching_folder_names:
            matching_folder_names.append(current_folder_name)

        # while current_folder_name matches a folder in matching_folder_names and current folder is not "/" or self.music_directory
        while re.match("|".join(matching_folder_names), current_folder_name.lower()) and current_folder_path != "/":

            # assign path to an image if one is found in the current folder
            image_path = self._get_folder_image(current_folder_path)

            # if an image path was assigned then return it
            if image_path:
                return image_path

            # set current_folder to its parent folder
            current_folder_path = os.path.abspath(os.path.join(current_folder_path, os.pardir))
            current_folder_name = os.path.basename(current_folder_path)

    def get_spotify_album_data(self, artist=None, album=None):
        """
        Query Spotify API for album information. Returns artist, album, date and image.
        """

        headers = {'Authorization': f'Bearer {self.token}'}
        params = {'type': 'album', 'offset': 0, 'limit': 5}
        query = f'artist:{artist}%20album:{album}'
        url = f'https://api.spotify.com/v1/search?q={query}'

        try:
            response = requests.get(url, headers=headers, params=params)
            results = response.json()
        except requests.exceptions.ConnectionError:
            return None

        if 'albums' in results and 'total' in results['albums'] and results['albums']['total'] > 0:

            album_results = results['albums']['items']

            selected_index = None

            # locate the index of the first valid album
            for index in range(len(album_results)):

                current_record = album_results[index]

                if 'name' in current_record and 'album_type' in current_record and 'images' in current_record:

                    album = current_record['name']
                    type = current_record['album_type']
                    image = current_record['images'][0]['url']

                    if type == "album" and image != "" and not self._is_album_name_unwanted(album):
                        selected_index = index
                        break

            # if no index was selected then validate the first record
            if not isinstance(selected_index, int):

                current_record = album_results[0]

                if 'name' in current_record and 'album_type' in current_record and 'images' in current_record:

                    album = current_record['name']
                    type = current_record['album_type']
                    image = current_record['images'][0]['url']

                    if type == "album" and image != "" and not self._is_album_name_unwanted(album):
                        selected_index = 0

            # if an index was selected then return it's values
            if isinstance(selected_index, int):

                selected_record = album_results[selected_index]

                artist = selected_record['artists'][0]['name']
                album = selected_record['name']
                date = selected_record['release_date']
                image = selected_record['images'][0]['url']

                return {'artist': artist, 'album': album, 'date': date, 'image_url': image}

    def get_spotify_track_data(self, artist=None, track=None):
        """
        Query Spotify API for track information. Returns title, artist, album, date and image.
        """

        headers = {'Authorization': f'Bearer {self.token}'}
        params = {'type': 'track', 'offset': 0, 'limit': 5}
        query = f'artist:{artist}%20track:{track}'
        url = f'https://api.spotify.com/v1/search?q={query}'

        try:
            response = requests.get(url, headers=headers, params=params)
            results = response.json()
        except requests.exceptions.ConnectionError:
            return None

        if 'tracks' in results and 'total' in results['tracks'] and results['tracks']['total'] > 0:

            track_results = results['tracks']['items']

            selected_index = None

            # locate the index of the first valid album
            for index in range(len(track_results)):

                current_record = track_results[index]

                if 'type' in current_record and 'album' in current_record:

                    type = current_record['album']['type']
                    album = current_record['album']['name']
                    image = current_record['album']['images'][0]['url']

                    if type == "album" and image != "" and not self._is_album_name_unwanted(album):
                        selected_index = index
                        break

            # if no index was selected then validate the first record
            if not isinstance(selected_index, int):

                current_record = track_results[0]

                if 'type' in current_record and 'album' in current_record:

                    type = current_record['album']['type']
                    album = current_record['album']['name']
                    image = current_record['album']['images'][0]['url']

                    if type == "album" and image != "" and not self._is_album_name_unwanted(album):
                        selected_index = 0

            # if an index was selected then return it's values
            if isinstance(selected_index, int):

                selected_record = track_results[selected_index]

                title = selected_record['name']
                album = selected_record['album']['name']
                date = selected_record['album']['release_date']
                image = selected_record['album']['images'][0]['url']

                return {'title': title, 'artist': artist, 'album': album, 'date': date, 'image_url': image}

    def _clean_album_string(self, name=None):

        # remove unwanted strings from album name
        unwanted_substrings = [
            r'\s?\([^\)]*edition\)$', r'\s?\[[^\]]*edition\]$',
            r'\s?\([^\)]*remaster(ed)?\)$', r'\s?\[[^\]]*remaster(ed)?\]$',
            r'\s?\([^\)]*release\)$', r'\s?\[[^\]]*release\]$'
        ]

        for val in unwanted_substrings:
            name = re.sub(val, "", name, flags=re.IGNORECASE)

        return name

    def _clean_date_string(self, date=None):

        if date and re.match(r'^19\d{2}\D?.*$|^20\d{2}\D?.*$', date):
            return date[0:4]
        elif date and re.match(r'|^.*\D19\d{2}$|^.*\D20\d{2}$', date):
            return date[-4:]
        else:
            return date


def get_arguments():

    parser = argparse.ArgumentParser(prog=PROG, usage="%(prog)s [options]", description="Send notification for current MPD track.", prefix_chars='-')
    parser.add_argument("--once", "-o", action="store_true", default=False, help="Send one notification and exit")

    return parser.parse_args()


def get_music_directory():

    config_path = None

    # locate config file path
    path_list = (f"{os.getenv('XDG_CONFIG_HOME')}/mpd/mpd.conf", f"{os.getenv('HOME')}/.config/mpd/mpd.conf", f"/home/{os.getlogin()}/.config/mpd/mpd.conf")
    for path in path_list:
        if os.path.exists(path) and os.path.isfile(path):
            config_path = path
            break

    if config_path:
        for line in open(config_path, 'r'):
            if re.match(r'music_directory.*$', line):
                line_list = line.strip().split()
                if len(line_list) == 2:
                    return os.path.expanduser(line_list[-1].strip("\""))


def open_mpd_connection(address, port, password=None, timeout=None, idle_timeout=None):

    client = mpd.MPDClient()

    if timeout:
        client.timeout = timeout

    if idle_timeout:
        client.idletimeout = idle_timeout

    if password:
        client.password(password)

    try:
        client.connect(address, port)
    except ConnectionRefusedError:
        sys.exit(f"error: could not connect to {MPD_BIND_ADDRESS}:{str(MPD_BIND_PORT)}")

    return client


def interrupt_signal(client):

    # hide output
    sys.stdout.write('\b\b\r')

    # if client connection is open then close it
    if client:
        client.close()

    # exit successfully
    sys.exit(0)


def get_spotify_access_token():

    access_token = None

    auth_response = requests.post('https://accounts.spotify.com/api/token', {
        'grant_type': 'client_credentials',
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
    })

    auth_response_data = auth_response.json()
    access_token = auth_response_data['access_token']

    if access_token:
        return access_token


def get_notification_message(props):

    message = ""

    if 'title' in props:
        message += f"<span size='large'><b>{props['title']}</b></span>"

    if 'album' in props:
        if 'date' in props:
            message += f"\n<span size='small'> on</span> <b>{props['album']}</b> (<b>{props['date']}</b>)"
        else:
            message += f"\n<span size='small'> on</span> <b>{props['album']}</b>"

    if 'artist' in props:
        message += f"\n<span size='small'> by</span> <b>{props['artist']}</b>"

    return message


def generate_pixbuf_from_image(props):

    if NOTIFY_DEFAULT_IMAGE and os.path.exists(NOTIFY_DEFAULT_IMAGE) and 'image_data' not in props and 'image_path' not in props and 'image_url' not in props:
        props['image_path'] = NOTIFY_DEFAULT_IMAGE

    if 'image_data' in props:

        input_stream = Gio.MemoryInputStream.new_from_data(props['image_data'], None)
        return Pixbuf.new_from_stream(input_stream, None)

    elif 'image_path' in props:

        return Pixbuf.new_from_file(props['image_path'])

    elif 'image_url' in props:

        try:
            response = urllib.request.urlopen(props['image_url'])
        except urllib.error.HTTPError:
            return None
        else:
            input_stream = Gio.MemoryInputStream.new_from_data(response.read(), None)
            return Pixbuf.new_from_stream(input_stream, None)


def send_notification(props):

    notify_message = get_notification_message(props)

    notify2.init(PROG)
    n = notify2.Notification(PROG, notify_message)

    if bool(NOTIFY_ID):
        n.id = NOTIFY_ID

    n.set_hint('desktop-entry', PROG)
    n.set_urgency(NOTIFY_URGENCY)
    n.set_timeout(NOTIFY_TIMEOUT)

    pixbuf = generate_pixbuf_from_image(props)

    if bool(pixbuf):
        n.set_icon_from_pixbuf(pixbuf)

    try:
        n.show()
    except Exception:
        print("error: failed to send notification.")


def notify_now():

    client = open_mpd_connection(MPD_BIND_ADDRESS, MPD_BIND_PORT, MPD_PASSWORD, MPD_TIMEOUT, MPD_IDLE_TIMEOUT)

    music_directory = get_music_directory()

    token = get_spotify_access_token()

    if bool(client.currentsong()) and 'file' in client.currentsong() and 'state' in client.status() and client.status()['state'] in ("play", "pause", "stop"):

        path = os.path.join(music_directory, client.currentsong()['file'])
        song = TrackInfo(path, token, client.currentsong())

        if song and song.path == os.path.join(music_directory, client.currentsong()['file']):
            send_notification(song.props)

    client.close()
    client.disconnect()


def notify_on_track_change():

    client = open_mpd_connection(MPD_BIND_ADDRESS, MPD_BIND_PORT, MPD_PASSWORD, MPD_TIMEOUT, MPD_IDLE_TIMEOUT)

    signal.signal(signal.SIGINT, lambda x, y: interrupt_signal(client))

    music_directory = get_music_directory()

    token = get_spotify_access_token()

    path = os.path.join(mpd_music_directory, client.currentsong()['file'])

    while client.idle("player"):

        if bool(client.currentsong()) and 'file' in client.currentsong() and 'state' in client.status() and client.status()['state'] == "play" and os.path.join(mpd_music_directory, client.currentsong()['file']) != path:

            path = os.path.join(music_directory, client.currentsong()['file'])
            song = TrackInfo(path, token, client.currentsong())

            if song and song.path == os.path.join(music_directory, client.currentsong()['file']):
                send_notification(song.props)


def main():

    arguments = get_arguments()

    if arguments.once:
        notify_now()
    else:
        notify_on_track_change()


if __name__ == "__main__":
    main()

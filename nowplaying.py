#!/usr/bin/python

"""
TODO: Move Spotify API auth data to config
TODO: get_image_data - add code for wma, wav, ogg
TODO: get_image_path - folder_name_patterns - perfect patterns for numbers as digits and strings
TODO: get_image_path - _get_folder_image - add all valid cover art filenames
"""

import argparse
import configparser
import os.path
import re
import signal
import sys
import urllib.request

import gi.repository
import mpd
import mutagen
import notify2
import requests
from gi.repository import Gio

gi.require_version("GdkPixbuf", "2.0")
from gi.repository.GdkPixbuf import Pixbuf

PROG = "nowplaying"


class SongInfo:

    def __init__(self, mpd_dict):

        self.id = mpd_dict['id']
        self.path = os.path.join(settings['mpd']['directory'], mpd_dict['file'])
        self.filename = os.path.basename(self.path)

        self.props = self.get_props(mpd_dict)

        os.system('clear')
        print(str(self.props))

    def __repr__(self):
        return "SongInfo('{}')".format(self.filename)

    def get_props(self, mpd_dict):

        def _get_clean_album_string(album):

            return re.sub(r'\s?(\(|\[)[^\)]*(edition|release|remaster|remastered)(\)|\])$', '', album, flags=re.IGNORECASE).strip()

        def _get_clean_date_string(date):

            # if string begins with year, return first four characters
            if date and re.match(r'^19\d{2}\D?.*$|^20\d{2}\D?.*$', date):
                return date[0:4]
            # else if string ends with year, return last four characters
            elif date and re.match(r'|^.*\D19\d{2}$|^.*\D20\d{2}$', date):
                return date[-4:]
            else:
                return date

        props = dict()

        if 'title' in mpd_dict:
            props['title'] = mpd_dict['title']
        if 'artist' in mpd_dict:
            props['artist'] = mpd_dict['artist']
        if 'album' in mpd_dict:
            props['album'] = mpd_dict['album']
        if 'date' in mpd_dict:
            props['date'] = mpd_dict['date']

        if 'title' not in props or 'artist' not in props or 'album' not in props:

            filename_dict = self.get_filename_dict()

            if 'title' not in props and 'title' in filename_dict:
                props['title'] = filename_dict['title']
            if 'artist' not in props and 'artist' in filename_dict:
                props['artist'] = filename_dict['artist']
            if 'album' not in props and 'album' in filename_dict:
                props['album'] = filename_dict['album']

        props['image_data'] = self.get_image_data()

        if props['image_data'] is None:
            del props['image_data']

        if 'image_data' not in props:

            props['image_path'] = self.get_image_path()

            if props['image_path'] is None:
                del props['image_path']

        if 'album' not in props or ('image_data' not in props and 'image_path' not in props):

            if 'artist' in props and 'album' in props:
                api_dict = self.api_album_data(props['artist'], props['album'])
            elif 'artist' in props and 'title' in props:
                api_dict = self.api_track_data(props['artist'], props['title'])
            else:
                api_dict = None

            if api_dict and api_dict.keys() >= {'artist', 'title', 'album', 'date', 'image_url'}:

                if 'image_data' in props:
                    del props['image_data']
                if 'image_path' in props:
                    del props['image_path']

                if 'title' in api_dict:
                    props['title'] = api_dict['title']
                props['artist'] = api_dict['artist']
                props['album'] = api_dict['album']
                props['date'] = api_dict['date']
                props['image_url'] = api_dict['image_url']

        if 'album' in props:
            props['album'] = _get_clean_album_string(props['album'])

        if 'date' in props:
            props['date'] = _get_clean_date_string(props['date'])

        return props

    def get_filename_dict(self):

        def _get_split_filename(filename):

            # get filename without extension
            string = os.path.splitext(filename)[0]

            # declare patterns to protect from split
            ignore_patterns = [
                {'initial': 'Ep. ', 'replace': '((EPDOT))'},
                {'initial': 'Dr. ', 'replace': '((DOCTORDOT))'},
                {'initial': 'Jr. ', 'replace': '((JUNIORDOT))'},
                {'initial': 'Sr. ', 'replace': '((SENIORDOT))'},
                {'initial': 'Mr. ', 'replace': '((MISTERDOT))'},
                {'initial': 'Ms. ', 'replace': '((MISSDOT))'},
                {'initial': 'Mrs. ', 'replace': '((MISSESDOT))'},
                {'initial': 'Vol. ', 'replace': '((VOLDOT))'}
            ]

            # replace protected patterns so prevent splitting
            for i in range(len(ignore_patterns)):
                string = string.replace(
                    ignore_patterns[i]['initial'], ignore_patterns[i]['replace'])

            # modify substrings deemed split points to match split regex
            string = re.sub(r"(?<=^\d{2})\.\s+", " - ", string)

            # split filename into chunks
            chunks_dirty = re.split(r'\s+-\s+', string)

            # replace protected patterns with original values
            chunks_clean = []
            for chunk in chunks_dirty:
                for i in range(len(ignore_patterns)):
                    chunk = chunk.replace(
                        ignore_patterns[i]['replace'], ignore_patterns[i]['initial'])
                chunks_clean.append(chunk.strip())

            return chunks_clean

        filename = os.path.basename(self.path)

        chunks = _get_split_filename(filename)
        assigned = dict()

        # search for track number and add it to dict
        for chunk in chunks:
            if re.match(r'^\d{1,2}$', chunk):
                assigned['track'] = chunk
                chunks.remove(chunk)
                break

        # remove extra chunks from start of list
        if len(chunks) > 3:
            chunks = chunks[-3:]

        if len(chunks) == 3:
            assigned['artist'], assigned['album'], assigned['title'] = chunks
        elif len(chunks) == 2:
            assigned['artist'], assigned['title'] = chunks
        elif len(chunks) == 1:
            assigned['title'] = chunks[0]

        return assigned

    def get_image_data(self):

        file = mutagen.File(self.path)

        # if a valid file with valid tags was found, proceed
        if file and file.tags and len(file.tags.values()) > 0:

            # declare acceptable values for embedded image tag.type
            types = [
                3,  # Cover (front)
                2,  # Other file icon
                1,  # PictureType.FILE_ICON
                0,  # PictureType.OTHER
                18  # Illustration
            ]

            # mp3
            if file.mime[0] == "audio/mp3":

                for type in types:
                    for tag in file.tags.values():
                        if tag.FrameID == 'APIC' and int(tag.type) == type:
                            return tag.data

            # m4a
            elif file.mime[0] == "audio/mp4":

                if 'covr' in file.tags.keys():
                    return file.tags['covr'][0]

            # flac
            elif file.mime[0] == "audio/flac":

                for type in types:
                    for tag in file.pictures:
                        if tag.type == type:
                            return tag.data

    def get_image_path(self):

        def _get_folder_image(folder):

            filenames = [
                'cover',
                'Cover',
                'front',
                'Front',
                'folder',
                'Folder',
                'thumb',
                'Thumb',
                'album',
                'Album',
                'albumart',
                'AlbumArt',
                'albumartsmall',
                'AlbumArtSmall'
            ]

            extensions = [
                'png',
                'jpg',
                'jpeg',
                'gif',
                'bmp',
                'tif',
                'tiff',
                'svg'
            ]

            for name in filenames:
                for ext in extensions:
                    path = f'{folder}/{name}.{ext}'
                    if os.path.exists(path):
                        return path

        folder_name_patterns = [
            r'^disc\s?\d+.*$',
            r'^cd\s?\d+.*$',
            r'^dvd\s?\d+.*$',
            r'^set\s?\d+.*$',
            os.path.basename(os.path.dirname(self.path)),
            os.path.splitext(self.path)[-1].lstrip('.')
        ]

        folder_path = os.path.dirname(self.path)
        folder_name = os.path.basename(folder_path)

        while re.match("|".join(folder_name_patterns), folder_name.lower()):

            image_path = _get_folder_image(folder_path)

            if image_path:
                return image_path

            folder_path = os.path.abspath(os.path.join(folder_path, os.pardir))
            folder_name = os.path.basename(folder_path)

    def _album_contains_bad_substrings(self, album):

        unwanted_substrings = ('best of', 'greatest hits', 'collection', 'b-sides', 'classics')

        return any([substring in album.lower() for substring in unwanted_substrings])

    def api_album_data(self, artist, album):

        artist, album = self.props['artist'], self.props['album']

        headers = {'Authorization': f'Bearer {spotify_token}'}
        params = {'type': 'album', 'offset': 0, 'limit': 5}
        query = f'artist:{artist}%20album:{album}'
        url = f'https://api.spotify.com/v1/search?q={query}'

        try:
            response = requests.get(url, headers=headers, params=params)
            results = response.json()
        except requests.exceptions.ConnectionError:
            return None

        # if requested results are valid, get API data
        if 'albums' in results and 'total' in results['albums'] and results['albums']['total'] > 0:

            album_records = results['albums']['items']
            record_index = None
            first_index = None

            # get the index for the first acceptable record
            for index in range(len(album_records)):
                record = album_records[index]
                if record.keys() >= {'album_type', 'artists', 'name', 'release_date', 'images'}:

                    if not first_index:
                        first_index = index

                    album = record['name']
                    type = record['album_type']
                    if type == "album" and not self._album_contains_bad_substrings(album):
                        record_index = index
                        break

            # if no index was selected, validate the first record and set selected index to 0
            if not isinstance(record_index, int):
                record_index = first_index

            # if a record index was selected, return the values for that record
            if isinstance(record_index, int):
                record = album_records[record_index]
                artist = record['artists'][0]['name']
                album = record['name']
                date = record['release_date']
                image = record['images'][0]['url']
                return {'artist': artist, 'album': album, 'date': date, 'image_url': image}

    def api_track_data(self, artist, track):

        headers = {'Authorization': f'Bearer {spotify_token}'}
        params = {'type': 'track', 'offset': 0, 'limit': 5}
        query = f'artist:{artist}%20track:{track}'
        url = f'https://api.spotify.com/v1/search?q={query}'

        try:
            response = requests.get(url, headers=headers, params=params)
            results = response.json()
        except requests.exceptions.ConnectionError:
            return None

        # if requested results are valid, get API data
        if 'tracks' in results and 'total' in results['tracks'] and results['tracks']['total'] > 0:

            track_records = results['tracks']['items']
            record_index = None
            first_index = None

            # get the index for the first acceptable record
            for index in range(len(track_records)):
                record = track_records[index]
                if record['album'].keys() >= {'type', 'name', 'release_date', 'images'}:

                    if not first_index:
                        first_index = index

                    type = record['album']['type']
                    album = record['album']['name']
                    if type == "album" and not self._album_contains_bad_substrings(album):
                        record_index = index
                        break

            # if no index was selected, validate the first record and set selected index to 0
            if not isinstance(record_index, int):
                record_index = first_index

            # if a record index was selected, return the values for that record
            if isinstance(record_index, int):
                record = track_records[record_index]
                title = record['name']
                artist = record['artists'][0]['name']
                album = record['album']['name']
                date = record['album']['release_date']
                image = record['album']['images'][0]['url']
                return {'title': title, 'artist': artist, 'album': album, 'date': date, 'image_url': image}


def cancel_process(client=None):

    sys.stdout.write('\b\b\r')

    if client is not None:
        client.close()

    sys.exit(0)


def get_settings():

    def _music_directory():

        path_list = (
            "{}/mpd/mpd.conf".format(os.getenv('XDG_CONFIG_HOME')),
            "{}/.config/mpd/mpd.conf".format(os.getenv('HOME')),
            "/home/{}/.config/mpd/mpd.conf".format(os.getenv('USER')),
            "/home/{}/.config/mpd/mpd.conf".format(os.getlogin())
        )

        for path in path_list:
            if os.path.isfile(path):
                for line in open(path, 'r'):
                    if re.match(r'^music_directory\s+\".*\"$', line):
                        return os.path.expanduser(line.strip().split()[-1].strip('\"'))
                    elif re.match(r'^music_directory\s+\'.*\'$', line):
                        return os.path.expanduser(line.strip().split()[-1].strip("\'"))

    def _config_path():

        filename = 'config.ini'

        path_list = (
            "{}/nowplaying/{}".format(os.getenv('XDG_CONFIG_HOME'), filename),
            "{}/.config/nowplaying/{}".format(os.getenv('HOME'), filename),
            "/home/{}/.config/nowplaying/{}".format(os.getlogin(), filename)
        )

        for path in path_list:
            if os.path.isfile(path):
                return path

    def _section_defaults(section):

        new_section_dict = dict()

        for field in expected_data[section]:

            field_name = field['name']
            field_default = field['default']

            new_section_dict[field_name] = field_default

        return new_section_dict

    def _all_defaults(expected_data):

        new_dict = dict()

        for section in expected_data:
            new_dict[section] = _section_defaults(section)

        return new_dict

    # dictionary of fields expected to be in config
    expected_data = {
        'mpd': [
            {'name': 'directory', 'type': 'str', 'default': _music_directory()},
            {'name': 'host', 'type': 'str', 'default': 'localhost'},
            {'name': 'port', 'type': 'int', 'default': 6600},
            {'name': 'password', 'type': 'str', 'default': None},
            {'name': 'timeout', 'type': 'int', 'default': None},
            {'name': 'idletimeout', 'type': 'int', 'default': None}
        ],
        'notify': [
            {'name': 'default_image', 'type': 'str', 'default': None},
            {'name': 'id', 'type': 'int', 'default': None},
            {'name': 'timeout', 'type': 'int', 'default': None},
            {'name': 'urgency', 'type': 'int', 'default': None}
        ]
    }

    config_path = _config_path()

    if config_path is None:

        return _all_defaults(expected_data)

    else:

        config = configparser.ConfigParser()
        config.read(config_path)

        new_dict = dict()

        for section in expected_data:

            if section not in config:

                new_dict[section] = _section_defaults(section)

            else:

                new_section_dict = dict()

                for field in expected_data[section]:

                    field_name = field['name']
                    field_default = field['default']

                    if field_name not in config[section]:

                        new_value = field_default

                    else:

                        field_type = field['type']
                        field_value = config[section][field_name]

                        if field_value == "":

                            new_value = field_default

                        elif field_type == 'int':

                            try:
                                new_value = int(field_value)
                            except ValueError:
                                new_value = field_default

                        else:

                            new_value = field_value

                    new_section_dict[field_name] = new_value

                new_dict[section] = new_section_dict

        if not os.path.isdir(new_dict['mpd']['directory']):
            new_dict['mpd']['directory'] = _music_directory()

        if not os.path.isfile(new_dict['notify']['default_image']):
            new_dict['notify']['default_image'] = None

        return new_dict


def get_mpd_client():

    set = settings['mpd']

    obj = mpd.MPDClient()

    if set['timeout']:
        obj.timeout = set['timeout']

    if set['idletimeout']:
        obj.idletimeout = set['idletimeout']

    if set['password']:
        obj.password(set['password'])

    try:
        obj.connect(set['host'], set['port'])
    except ConnectionRefusedError:
        sys.exit(
            f"error: could not connect to {set['host']}:{str(set['port'])}")

    return obj


def get_spotify_token():

    access_token = None

    auth_response = requests.post('https://accounts.spotify.com/api/token', {
        'grant_type': 'client_credentials',
        'client_id': '3ad71cf0ae544e7e935927e5d9a5cbad',
        'client_secret': '862905d9380645a9ba29789308d795d5',
    })

    auth_response_data = auth_response.json()
    access_token = auth_response_data['access_token']

    return access_token


def get_arguments():

    parser = argparse.ArgumentParser(prog=PROG, usage="%(prog)s [options]", description="Send notification for current MPD track.", prefix_chars='-')
    parser.add_argument("--once", "-o", action="store_true", default=False, help="Send one notification and exit")

    return parser.parse_args()


def get_notify_assets(props):

    message = pixbuf = None

    if 'title' in props:

        if len(props['title']) > 36:
            size = "x-small"
        elif len(props['title']) > 30:
            size = "small"
        else:
            size = "medium"

        message = f"<span size='{size}'><b>{props['title']}</b></span>"

        if 'album' in props:

            if 'date' in props:
                line_length = len(f"by {props['album']} ({props['date']})")
            else:
                line_length = len(f"by {props['album']}")

            if line_length > 36:
                size = "x-small"
            elif line_length > 30:
                size = "small"
            else:
                size = "medium"

            if 'date' in props:
                message += f"\n<span size='x-small'>on </span><span size='{size}'><b>{props['album']}</b> (<b>{props['date']}</b></span>)"
            else:
                message += f"\n<span size='x-small'>on </span><span size='{size}'><b>{props['album']}</b></span>"

        if 'artist' in props:

            if len(props['artist']) > 36:
                size = "x-small"
            elif len(props['artist']) > 30:
                size = "small"
            else:
                size = "medium"

            message += f"\n<span size='x-small'>by </span><span size='{size}'><b>{props['artist']}</b></span>"

    if 'image_data' not in props and 'image_path' not in props and 'image_url' not in props:
        props['image_path'] = settings['notify']['default_image']

    if 'image_data' in props:

        try:
            input_stream = Gio.MemoryInputStream.new_from_data(props['image_data'], None)
            pixbuf = Pixbuf.new_from_stream(input_stream, None)
        except Exception:
            pass

    elif 'image_path' in props:

        try:
            pixbuf = Pixbuf.new_from_file(props['image_path'])
        except Exception:
            pass

    elif 'image_url' in props:

        try:
            response = urllib.request.urlopen(props['image_url'])
            input_stream = Gio.MemoryInputStream.new_from_data(response.read(), None)
            pixbuf = Pixbuf.new_from_stream(input_stream, None)
        except Exception:
            pass

    return message, pixbuf


def get_notification(message, pixbuf):

    if message is not None:

        set = settings['notify']

        notify2.init(PROG)
        obj = notify2.Notification(PROG, message)

        obj.set_hint('desktop-entry', PROG)

        if set['id'] is not None:
            obj.id = set['id']

        if set['timeout'] is not None:
            obj.set_timeout(set['timeout'])

        if set['urgency'] is not None:
            obj.set_urgency(set['urgency'])

        if pixbuf is not None:
            obj.set_icon_from_pixbuf(pixbuf)

        return obj


def notify_user(client):

    if client.currentsong() and 'file' in client.currentsong():

        song = SongInfo(client.currentsong())

        message, pixbuf = get_notify_assets(song.props)

        n = get_notification(message, pixbuf)

        if n is None or client.currentsong()['id'] != song.id:
            return

        n.show()


def notify_on_event(client):

    while client.idle('player'):
        if client.status()['state'] == 'play':
            notify_user(client)


def main():

    client = None

    signal.signal(signal.SIGINT, lambda x, y: cancel_process(client))
    signal.signal(signal.SIGTERM, lambda x, y: cancel_process(client))

    global settings
    settings = get_settings()

    global spotify_token
    spotify_token = get_spotify_token()

    client = get_mpd_client()

    arguments = get_arguments()

    if arguments.once:
        notify_user(client)
    else:
        notify_on_event(client)

    client.close()
    client.disconnect()


if __name__ == "__main__":
    # sys.tracebacklimit = 0
    main()

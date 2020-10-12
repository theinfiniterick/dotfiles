#!/usr/bin/python

import argparse
import configparser
import json
import mimetypes
import os.path
import re
import signal
import sys
import urllib.request

import dateutil.parser
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
        self.mimetype = mimetypes.guess_type(self.filename)[0]

        self.props = self.get_props(mpd_dict)

    def __repr__(self):
        return "SongInfo('{}')".format(self.filename)

    def generate_pixbuf(self, value):

        if isinstance(value, bytes) or isinstance(value, mutagen.mp4.MP4Cover):

            try:
                input_stream = Gio.MemoryInputStream.new_from_data(value, None)
                pixbuf = Pixbuf.new_from_stream(input_stream, None)
            except Exception:
                return None
            else:
                return pixbuf

        elif isinstance(value, str) and re.match(r'^https?://', value):

            try:
                response = urllib.request.urlopen(value)
                input_stream = Gio.MemoryInputStream.new_from_data(response.read(), None)
                pixbuf = Pixbuf.new_from_stream(input_stream, None)
            except Exception:
                return None
            else:
                return pixbuf

        elif isinstance(value, str):

            try:
                pixbuf = Pixbuf.new_from_file(value)
            except Exception:
                return None
            else:
                return pixbuf

    def get_props(self, mpd_dict):

        props = dict()

        if 'title' in mpd_dict:
            props['title'] = mpd_dict['title']
        if 'artist' in mpd_dict:
            props['artist'] = mpd_dict['artist']
        if 'album' in mpd_dict:
            props['album'] = mpd_dict['album']
        if 'date' in mpd_dict:
            props['date'] = mpd_dict['date']

        if props.keys() < {'title', 'artist', 'album'}:

            filename_dict = self.get_filename_dict()

            if 'title' not in props and 'title' in filename_dict:
                props['title'] = filename_dict['title']
            if 'artist' not in props and 'artist' in filename_dict:
                props['artist'] = filename_dict['artist']
            if 'album' not in props and 'album' in filename_dict:
                props['album'] = filename_dict['album']

        if self.mimetype in ('audio/mpeg', 'audio/mp4', 'audio/x-flac'):

            pixbuf = self.generate_pixbuf(self.get_image_data())
            if pixbuf is not None:
                props['pixbuf'] = pixbuf

        if 'pixbuf' not in props:

            pixbuf = self.generate_pixbuf(self.get_image_path())
            if pixbuf is not None:
                props['pixbuf'] = pixbuf

        if 'token' in settings['spotify'] and ('album' not in props or 'pixbuf' not in props):

            if 'artist' in props and 'album' in props:
                api_dict = self.api_album_data(props['artist'], props['album'])
            elif 'artist' in props and 'title' in props:
                api_dict = self.api_track_data(props['artist'], props['title'])
            else:
                api_dict = None

            if api_dict and api_dict.keys() >= {'artist', 'album', 'date', 'image'}:

                props['artist'] = api_dict['artist']
                props['album'] = api_dict['album']
                props['date'] = api_dict['date']

                pixbuf = self.generate_pixbuf(api_dict['image'])
                if pixbuf is not None:
                    props['pixbuf'] = pixbuf

        if 'album' in props:
            regex = re.compile(r'\s?(\(|\[)[^\)]*(version|edition|deluxe|release|remaster|remastered)(\)|\])$', flags=re.IGNORECASE)
            props['album'] = regex.sub('', props['album'])

        if 'date' in props:
            props['date'] = dateutil.parser.parse(props['date']).year

        if 'pixbuf' not in props and settings['notify']['default_image'] is not None:
            pixbuf = self.generate_pixbuf(settings['notify']['default_image'])
            if pixbuf is not None:
                props['pixbuf'] = pixbuf

        if 'pixbuf' not in props:
            props['pixbuf'] = None

        return props

    def get_filename_dict(self):

        string = os.path.splitext(self.filename)[0]

        regex = re.compile(r"\s+-\s+|(?<=^\d{1})\.\s+|(?<=^\d{2})\.\s+|(?<=\s{1}\d{1})\.\s+|(?<=\s{1}\d{2})\.\s+")
        values = regex.split(string)

        values = [val.strip() for val in values]

        assigned = dict()

        for val in values:
            if re.match(r'^\d{1,2}$', val):
                assigned['track'] = val
                values.remove(val)
                break

        if len(values) > 3:
            values = values[-3:]

        if len(values) == 3:
            assigned['artist'], assigned['album'], assigned['title'] = values
        elif len(values) == 2:
            assigned['artist'], assigned['title'] = values
        elif len(values) == 1:
            assigned['title'] = values[0]

        return assigned

    def get_image_data(self):

        file = mutagen.File(self.path)

        if file and file.tags and len(file.tags.values()) > 0:

            image_types = [
                3,  # Cover (front)
                2,  # Other file icon
                1,  # PictureType.FILE_ICON
                0,  # PictureType.OTHER
                18  # Illustration
            ]

            if self.mimetype == "audio/mpeg":  # mp3

                for type in image_types:
                    for tag in file.tags.values():
                        if tag.FrameID == 'APIC' and int(tag.type) == type:
                            return tag.data

            elif self.mimetype == "audio/x-flac":  # flac

                for type in image_types:
                    for tag in file.pictures:
                        if tag.type == type:
                            return tag.data

            elif self.mimetype == "audio/mp4":  # m4a

                if 'covr' in file.tags.keys():
                    return file.tags['covr'][0]

    def get_image_path(self):

        def _folder_image(folder):

            filenames = [
                'cover', 'Cover',
                'front', 'Front',
                'folder', 'Folder',
                'thumb', 'Thumb',
                'album', 'Album',
                'albumart',
                'AlbumArt',
                'albumartsmall',
                'AlbumArtSmall'
            ]

            extensions = [
                'png', 'jpg', 'jpeg', 'gif',
                'bmp', 'tif', 'tiff', 'svg'
            ]

            for name in filenames:
                for ext in extensions:
                    path = f'{folder}/{name}.{ext}'
                    if os.path.exists(path):
                        return path

        folder_name_patterns = [
            r'^disc\s?.*$|^cd\s?.*$|^dvd\s?.*$|^set\s?.*$',
            os.path.basename(os.path.dirname(self.path)),
            os.path.splitext(self.path)[-1].lstrip('.')
        ]

        folder_path = os.path.dirname(self.path)
        folder_name = os.path.basename(folder_path)

        while re.match("|".join(folder_name_patterns), folder_name, flags=re.IGNORECASE):

            image_path = _folder_image(folder_path)

            if image_path:
                return image_path

            folder_path = os.path.abspath(os.path.join(folder_path, os.pardir))
            folder_name = os.path.basename(folder_path)

    def api_album_data(self, artist, album):

        if 'token' not in settings['spotify']:
            return None

        headers = {'Authorization': f"Bearer {settings['spotify']['token']}"}
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

            bad_patterns = re.compile(r'best of|greatest hits|collection|b-sides|classics|live', flags=re.IGNORECASE)
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

                    if type == "album" and not bad_patterns.search(album):
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
                return {'artist': artist, 'album': album, 'date': date, 'image': image}

    def api_track_data(self, artist, track):

        if 'token' not in settings['spotify']:
            return None

        headers = {'Authorization': f"Bearer {settings['spotify']['token']}"}
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

            bad_patterns = re.compile(r'best of|greatest hits|collection|b-sides|classics|live', flags=re.IGNORECASE)
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
                    if type == "album" and not bad_patterns.search(album):
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
                return {'title': title, 'artist': artist, 'album': album, 'date': date, 'image': image}


class Settings():

    def __init__(self):

        mpd_conf_data = self.mpd_conf_data

        self._expected_data = {
            'mpd': [
                {'name': 'directory', 'type': 'str', 'default': mpd_conf_data['directory']},
                {'name': 'host', 'type': 'str', 'default': mpd_conf_data['host']},
                {'name': 'port', 'type': 'int', 'default': mpd_conf_data['port']},
                {'name': 'password', 'type': 'str', 'default': mpd_conf_data['password']}
            ],
            'notify': [
                {'name': 'default_image', 'type': 'str', 'default': None},
                {'name': 'id', 'type': 'int', 'default': None},
                {'name': 'timeout', 'type': 'int', 'default': None},
                {'name': 'urgency', 'type': 'int', 'default': None}
            ],
            'spotify': [
                {'name': 'client_id', 'type': 'str', 'default': None},
                {'name': 'client_secret', 'type': 'str', 'default': None}
            ]
        }

    @property
    def mpd_conf_path(self):

        path_list = (
            "{}/mpd/mpd.conf".format(os.getenv('XDG_CONFIG_HOME')),
            "{}/.config/mpd/mpd.conf".format(os.getenv('HOME')),
            "/home/{}/.config/mpd/mpd.conf".format(os.getenv('USER')),
            "/home/{}/.config/mpd/mpd.conf".format(os.getlogin())
        )

        for path in path_list:
            if os.path.isfile(path):
                return path

    @property
    def mpd_conf_data(self):

        data = dict()
        path = self.mpd_conf_path

        if path is None:
            sys.exit("error: mpd.conf not found.")

        if path is not None:
            for line in open(path, 'r'):
                line = line.strip()
                if not line.startswith('#') and line != "":
                    line_arr = line.split()
                    if len(line_arr) == 2:
                        field = line_arr[0]
                        value = line_arr[1].strip('\"').strip('\'')
                        if field == "music_directory":
                            data['directory'] = os.path.expanduser(value)
                        elif field == "bind_to_address" and re.match(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', value):
                            data['host'] = value
                        elif field == "port":
                            data['port'] = int(value)
                        elif field == "password":
                            data['password'] = value

        if 'host' not in data:
            data['host'] = '127.0.0.1'
        if 'port' not in data:
            data['port'] = 6600
        if 'password' not in data:
            data['password'] = None

        return data

    @property
    def config_path(self):

        filename = 'config.ini'

        path_list = (
            "{}/nowplaying/{}".format(os.getenv('XDG_CONFIG_HOME'), filename),
            "{}/.config/nowplaying/{}".format(os.getenv('HOME'), filename),
            "/home/{}/.config/nowplaying/{}".format(os.getlogin(), filename)
        )

        for path in path_list:
            if os.path.isfile(path):
                return path

    @property
    def config_data(self):

        def _section_defaults(section):

            new_section_dict = dict()

            for field in self._expected_data[section]:

                field_name = field['name']
                field_default = field['default']

                new_section_dict[field_name] = field_default

            return new_section_dict

        def _all_defaults():

            new_dict = dict()

            for section in self._expected_data:
                new_dict[section] = _section_defaults(section)

            return new_dict

        config_path = self.config_path

        if config_path is None:
            return _all_defaults()
        else:

            config = configparser.ConfigParser()
            config.read(config_path)
            new_dict = dict()

            for section in self._expected_data:

                if section not in config:

                    new_dict[section] = _section_defaults(section)

                else:

                    new_section_dict = dict()

                    for field in self._expected_data[section]:

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
                new_dict['mpd']['directory'] = self.mpd_conf_data['directory']

            if new_dict['notify']['default_image'] is None or not os.path.isfile(new_dict['notify']['default_image']):
                new_dict['notify']['default_image'] = None

            if 'client_id' in new_dict['spotify'] and 'client_secret' in new_dict['spotify']:
                token = self._get_spotify_token(new_dict['spotify']['client_id'], new_dict['spotify']['client_secret'])
                if token is not None:
                    new_dict['spotify']['token'] = token

            return new_dict

    def _get_spotify_token(self, client_id=None, client_secret=None):
        """
        Request API token from Spotify.\n
        If no valid token, None is returned.\n
        Args:
        - client_id (str)
        - client_secret (str)
        """

        if client_id is None or client_secret is None:
            return None

        try:
            auth_response = requests.post('https://accounts.spotify.com/api/token', {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret
            })
            auth_response_data = auth_response.json()
        except requests.exceptions.ConnectionError:
            print("error: failed to connect to spotify for authorization.")
        except json.decoder.JSONDecodeError:
            print("error: failed to read valid response from spotify.")
        else:
            if 'access_token' in auth_response_data:
                access_token = auth_response_data['access_token']
                if access_token is not None:
                    return access_token
            else:
                print("error: spotify did not return a valid token.")


def cancel_process(client=None):

    sys.stdout.write('\b\b\r')

    if client is not None:
        client.close()

    sys.exit(0)


def get_arguments():

    parser = argparse.ArgumentParser(prog=PROG, usage="%(prog)s [options]", description="Send notification for current MPD track.", prefix_chars='-')
    parser.add_argument("--once", "-o", action="store_true", default=False, help="Send one notification and exit")

    return parser.parse_args()


def get_client():

    host, port, password = settings['mpd']['host'], settings['mpd']['port'], settings['mpd']['password']

    obj = mpd.MPDClient()

    obj.timeout = 10

    if password:
        obj.password(password)

    try:
        obj.connect(host, port)
    except ConnectionRefusedError:
        sys.exit(f"error: could not connect to {host}:{str(port)}")
    except Exception:
        sys.exit(f"error: timed out connecting to {host}:{str(port)}")

    return obj


def get_notify_message(props):

    message = None

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

    return message


def get_notification(message, pixbuf):

    if message is not None:

        set = settings['notify']

        notify2.init(PROG)

        if pixbuf is None:
            obj = notify2.Notification(PROG, message, icon='library-music')
        else:
            obj = notify2.Notification(PROG, message)
            obj.set_icon_from_pixbuf(pixbuf)

        obj.set_hint('desktop-entry', PROG)

        if set['id'] is not None:
            obj.id = set['id']

        if set['timeout'] is not None:
            obj.set_timeout(set['timeout'])

        if set['urgency'] is not None:
            obj.set_urgency(set['urgency'])

        return obj


def notify_user(client):

    if client.currentsong() and 'file' in client.currentsong():
        song = SongInfo(client.currentsong())
        message = get_notify_message(song.props)
        nobject = get_notification(message, song.props['pixbuf'])

        if nobject is not None and client.currentsong()['id'] == song.id:
            print(song)
            nobject.show()


def notify_on_event(client):

    prev_id = client.currentsong()['id']

    while client.idle('player'):

        if client.status()['state'] == 'play' and id != prev_id:
            notify_user(client)
            prev_id = client.currentsong()['id']


def main():

    client = None

    signal.signal(signal.SIGINT, lambda x, y: cancel_process(client))
    signal.signal(signal.SIGTERM, lambda x, y: cancel_process(client))

    global settings
    settings = Settings().config_data

    client = get_client()

    arguments = get_arguments()

    if arguments.once:
        notify_user(client)
    else:
        notify_on_event(client)

    client.close()
    client.disconnect()


if __name__ == "__main__":
    main()

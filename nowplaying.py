#!/usr/bin/python

import argparse
import configparser
import json
import mimetypes
import os.path
import re
import signal
import sys

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

    def get_props(self, mpd_dict):

        def _clean_album(album):

            regex = re.compile(r'\s?(\(|\[)[^\)]*(version|edition|deluxe|release|remaster|remastered)(\)|\])$', flags=re.IGNORECASE)
            return regex.sub('', album)

        def _clean_date(date):

            return dateutil.parser.parse(date).year

        props = dict()

        if 'title' in mpd_dict:
            props['title'] = mpd_dict['title']
            print(f"props['title'] = mpd_dict['title'] = {mpd_dict['title']}")
        if 'artist' in mpd_dict:
            props['artist'] = mpd_dict['artist']
            print(f"props['artist'] = mpd_dict['artist'] = {mpd_dict['artist']}")
        if 'album' in mpd_dict:
            props['album'] = mpd_dict['album']
            print(f"props['album'] = mpd_dict['album'] = {mpd_dict['album']}")
        if 'date' in mpd_dict:
            props['date'] = mpd_dict['date']
            print(f"props['date'] = mpd_dict['date'] = {mpd_dict['date']}")

        if props.keys() < {'title', 'artist', 'album'}:

            filename_dict = self.get_filename_dict()

            if 'title' not in props and 'title' in filename_dict:
                props['title'] = filename_dict['title']
                print(f"props['title'] = filename_dict['title'] = {filename_dict['title']}")
            if 'artist' not in props and 'artist' in filename_dict:
                props['artist'] = filename_dict['artist']
                print(f"props['artist'] = filename_dict['artist'] = {filename_dict['artist']}")
            if 'album' not in props and 'album' in filename_dict:
                props['album'] = filename_dict['album']
                print(f"props['album'] = filename_dict['album'] = {filename_dict['album']}")

        if self.mimetype in ('audio/mpeg', 'audio/mp4', 'audio/x-flac'):

            pixbuf = self.get_pixbuf_from_embedded()

            if pixbuf is not None:
                props['pixbuf'] = pixbuf
                print("props['pixbuf'] = data")

        if 'pixbuf' not in props:

            pixbuf = self.get_pixbuf_from_path()

            if pixbuf is not None:
                props['pixbuf'] = pixbuf
                print("props['pixbuf'] = path")

        if settings['spotify']['token'] is not None and ('album' not in props or 'pixbuf' not in props):

            if 'artist' in props and 'album' in props:
                api_dict = self.get_api_album(props['artist'], props['album'])
                print(f"api_dict = self.get_api_album('{props['artist']}', '{props['album']}')")
            elif 'artist' in props and 'title' in props:
                api_dict = self.get_api_track(props['artist'], props['title'])
                print(f"api_dict = self.get_api_track('{props['artist']}', '{props['title']}')")
            else:
                api_dict = None

            if api_dict and api_dict.keys() >= {'artist', 'album', 'date', 'pixbuf'}:

                props['artist'] = api_dict['artist']
                print(f"props['artist'] = api_dict['artist'] = {api_dict['artist']}")
                props['album'] = api_dict['album']
                print(f"props['album'] = api_dict['album'] = {api_dict['album']}")
                props['date'] = api_dict['date']
                print(f"props['date'] = api_dict['date'] = {api_dict['date']}")
                props['pixbuf'] = api_dict['pixbuf']
                print(f"props['pixbuf'] = api_dict['pixbuf'] = {api_dict['pixbuf']}")

        if 'album' in props:
            props['album'] = _clean_album(props['album'])
            print(f"post clean album = {props['album']}")

        if 'date' in props:
            props['date'] = _clean_date(props['date'])
            print(f"post clean date = {props['date']}")

        if 'pixbuf' not in props:
            if settings['notify']['default_image'] is not None:
                props['pixbuf'] = settings['notify']['default_image']
                print("props['pixbuf'] = settings['notify']['default_image']")
            else:
                props['pixbuf'] = None
                print("props['pixbuf'] = None")

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

    def get_pixbuf_from_embedded(self):

        if self.mimetype in ('audio/mpeg', 'audio/x-flac', 'audio/mp4'):

            file = mutagen.File(self.path)

            image_types = [3, 2, 1, 0, 18]

            if self.mimetype == 'audio/mpeg':  # mp3
                for type in image_types:
                    for tag in file.tags.values():
                        if tag.FrameID == 'APIC' and int(tag.type) == type:
                            input_stream = Gio.MemoryInputStream.new_from_data(tag.data, None)
                            return Pixbuf.new_from_stream(input_stream, None)
            elif self.mimetype == 'audio/x-flac':  # flac
                for type in image_types:
                    for tag in file.pictures:
                        if tag.type == type:
                            input_stream = Gio.MemoryInputStream.new_from_data(tag.data, None)
                            return Pixbuf.new_from_stream(input_stream, None)
            elif self.mimetype == 'audio/mp4':  # m4a
                if 'covr' in file.tags.keys():
                    input_stream = Gio.MemoryInputStream.new_from_data(file.tags['covr'][0], None)
                    return Pixbuf.new_from_stream(input_stream, None)

    def get_pixbuf_from_path(self):

        filenames = [
            'cover', 'Cover', 'front', 'Front',
            'folder', 'Folder', 'thumb', 'Thumb',
            'album', 'Album', 'albumart', 'AlbumArt',
            'albumartsmall', 'AlbumArtSmall'
        ]

        extensions = [
            'png', 'jpg', 'jpeg', 'gif',
            'bmp', 'tif', 'tiff', 'svg'
        ]

        folder = os.path.dirname(self.path)

        while folder != settings['mpd']['directory']:

            for name in filenames:
                for ext in extensions:
                    path = '{}/{}.{}'.format(folder, name, ext)
                    if os.path.isfile(path):
                        return Pixbuf.new_from_file(path)

            folder = os.path.abspath(os.path.join(folder, os.pardir))

    def query_api(self, artist=None, album=None, track=None):

        headers = {'Authorization': 'Bearer {}'.format(settings['spotify']['token'])}

        if None not in (artist, album):
            params = {'type': 'album', 'offset': 0, 'limit': 10}
            url = "https://api.spotify.com/v1/search?q=artist:{} AND album:{}".format(artist, album)
        elif None not in (artist, track):
            params = {'type': 'track', 'offset': 0, 'limit': 10}
            url = "https://api.spotify.com/v1/search?q=artist:{} AND track:{}".format(artist, track)
        else:
            url, params = None, None

        if None not in (url, params):

            try:
                api_response = requests.get(url, headers=headers, params=params)
            except requests.exceptions.ConnectionError:
                print("error: api connection failed.")
                return None

            if api_response.status_code != 200:
                print("error: api response invalid.")
                return None

            api_data = api_response.json()

            if album is not None:

                if api_data['albums']['total'] == 0:
                    print("warning: no api results for artist:{}, album:{}.".format(artist, album))
                    return None

                return api_data['albums']['items']

            elif track is not None:

                if api_data['tracks']['total'] == 0:
                    print("warning: no api results for artist:{}, album:{}.".format(artist, album))
                    return None

                return api_data['tracks']['items']

    def get_pixbuf_from_url(self, url):

        try:
            response = requests.get(url)
        except requests.exceptions.ConnectionError:
            print("error: album art api connection failed.")
        else:

            if response.status_code != 200:
                print("error: album art api response invalid.")
                return None

            input_stream = Gio.MemoryInputStream.new_from_data(response.content, None)
            return Pixbuf.new_from_stream(input_stream, None)

    def get_api_album(self, artist, album):

        api_albums = self.query_api(artist=artist, album=album)

        if api_albums is None:
            return None

        bad_patterns = re.compile(r'best of|greatest hits|collection|b-sides|classics|live', flags=re.IGNORECASE)
        selected_index = 0
        for index in range(len(api_albums)):
            album = api_albums[index]['name']
            if not bad_patterns.search(album):
                selected_index = index
                break

        selected_album = api_albums[selected_index]

        artist = selected_album['artists'][0]['name']
        album = selected_album['name']
        date = selected_album['release_date']
        image = selected_album['images'][0]['url']

        pixbuf = self.get_pixbuf_from_url(image)

        return {'artist': artist, 'album': album, 'date': date, 'pixbuf': pixbuf}

    def get_api_track(self, artist, track):

        api_tracks = self.query_api(artist=artist, track=track)

        if api_tracks is None:
            return None

        bad_patterns = re.compile(r'best of|greatest hits|collection|b-sides|classics|live', flags=re.IGNORECASE)
        selected_index = 0
        for index in range(len(api_tracks)):
            album = api_tracks[index]['album']['name']
            if not bad_patterns.search(album):
                selected_index = index
                break

        selected_track = api_tracks[selected_index]

        title = selected_track['name']
        artist = selected_track['artists'][0]['name']
        album = selected_track['album']['name']
        date = selected_track['album']['release_date']
        image = selected_track['album']['images'][0]['url']

        pixbuf = self.get_pixbuf_from_url(image)

        return {'title': title, 'artist': artist, 'album': album, 'date': date, 'pixbuf': pixbuf}


def get_settings():

    def get_mpdconf_path():

        path_list = []

        if 'XDG_CONFIG_HOME' in os.environ:
            path = "{}/mpd/mpd.conf".format(os.environ['XDG_CONFIG_HOME'])
            path_list.append(path)

        if 'HOME' in os.environ:
            path = "{}/.config/mpd/mpd.conf".format(os.environ['HOME'])
            if path not in path_list:
                path_list.append(path)

        if 'USER' in os.environ:
            path = "/home/{}/.config/mpd/mpd.conf".format(os.environ['USER'])
            if path not in path_list:
                path_list.append(path)
        else:
            path = "/home/{}/.config/mpd/mpd.conf".format(os.getlogin())
            if path not in path_list:
                path_list.append(path)

        for path in path_list:
            if os.path.isfile(path):
                return path

    def get_config_path():

        filename = 'config.ini'

        path_list = []

        if 'XDG_CONFIG_HOME' in os.environ:
            path = "{}/nowplaying/{}".format(os.environ['XDG_CONFIG_HOME'], filename)
            path_list.append(path)

        if 'HOME' in os.environ:
            path = "{}/.config/nowplaying/{}".format(os.environ['HOME'], filename)
            if path not in path_list:
                path_list.append(path)

        if 'USER' in os.environ:
            path = "/home/{}/.config/nowplaying/{}".format(os.environ['USER'], filename)
            if path not in path_list:
                path_list.append(path)
        else:
            path = "/home/{}/.config/nowplaying/{}".format(os.getlogin(), filename)
            if path not in path_list:
                path_list.append(path)

        for path in path_list:
            if os.path.isfile(path):
                return path

    def get_mpdconf_data():

        path = get_mpdconf_path()

        data = dict()

        if path is not None:
            for line in open(path, 'r'):
                line = line.strip()
                if not line.startswith('#') and line != '':
                    line_arr = line.split()
                    if len(line_arr) == 2:
                        field = line_arr[0]
                        value = line_arr[1].strip('\"').strip('\'')
                        if field == "music_directory" and os.path.isdir(os.path.expanduser(value)):
                            data['directory'] = os.path.expanduser(value)
                        elif field == "bind_to_address" and re.match(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$', value):
                            data['host'] = value
                        elif field == "port":
                            data['port'] = int(value)
                        elif field == "password":
                            data['password'] = value

        return data

    def get_spotify_token(client_id, client_secret):

        params = {
            'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret
        }

        try:
            response = requests.post('https://accounts.spotify.com/api/token', params)
            response_data = response.json()
        except requests.exceptions.ConnectionError:
            print("error: Could not connect to Spotify API for authorization token.")
        except json.decoder.JSONDecodeError:
            print("error: Spotify API did not return valid data for authorization token.")
        else:

            if 'access_token' not in response_data or response_data['access_token'] is None:
                print("error: Spotify API did not return a valid authorization token.")
            else:
                return response_data['access_token']

    # declare empty dictionary for data
    data = {
        'mpd': {
            'directory': None,
            'host': None,
            'port': None,
            'password': None
        },
        'notify': {
            'default_image': None,
            'id': None,
            'timeout': None,
            'urgency': None
        },
        'spotify': {
            'client_id': None,
            'client_secret': None,
            'token': None
        }
    }

    # append mpd.conf data
    mpdconf_data = get_mpdconf_data()
    for key, value in mpdconf_data.items():
        data['mpd'][key] = value

    # append config.ini data
    config_path = get_config_path()

    if config_path is not None:

        config = configparser.ConfigParser()
        config.read(config_path)

        for section in config.sections():
            for key, value in config.items(section):
                # if section and key are a valid field and value is not blank
                if section in data and key in data[section] and value != '':
                    if key in ('port', 'id', 'timeout', 'urgency'):
                        try:
                            data[section][key] = int(value)
                        except ValueError:
                            pass
                    elif section == 'mpd' and key == 'directory' and os.path.isdir(value):
                        data[section][key] = value
                    elif section == 'notify' and key == 'default_image' and os.path.isfile(value):
                        data[section][key] = Pixbuf.new_from_file(value)
                    else:
                        data[section][key] = value

    # append spotify authorization token to data
    if data['spotify']['client_id'] is not None and data['spotify']['client_secret'] is not None:
        data['spotify']['token'] = get_spotify_token(data['spotify']['client_id'], data['spotify']['client_secret'])

    return data


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
            nobject.show()


def notify_on_event(client):

    prev_songid = None
    prev_state = None

    while client.idle('player'):

        songid = client.currentsong()['id']
        state = client.status()['state']

        # if state changes to play or new track starts playing
        if state == 'play' and (prev_state != 'play' or prev_songid != songid):
            notify_user(client)

        prev_songid = songid
        prev_state = state


def main():

    client = None

    signal.signal(signal.SIGINT, lambda x, y: cancel_process(client))
    signal.signal(signal.SIGTERM, lambda x, y: cancel_process(client))

    global settings
    settings = get_settings()

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

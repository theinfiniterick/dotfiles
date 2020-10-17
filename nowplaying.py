#!/usr/bin/python

import argparse
import configparser
import dateutil.parser
import mpd
import mutagen
import notify2
import os.path
import re
import requests
import signal
import sys

import gi.repository
from gi.repository import Gio
gi.require_version("GdkPixbuf", "2.0")
from gi.repository.GdkPixbuf import Pixbuf

PROG = "nowplaying"


class SongInfo:

    def __init__(self, mpd_dict):

        self.id = mpd_dict['id']
        self.path = os.path.join(cfg['mpd']['directory'], mpd_dict['file'])
        self.filename = os.path.basename(self.path)

        self.props = self.get_props(mpd_dict)

    def __repr__(self):
        return "SongInfo('{}')".format(self.filename)

    def get_props(self, mpd_dict):

        props = dict()

        # append data from mpd
        if 'title' in mpd_dict:
            props['title'] = mpd_dict['title']
        if 'artist' in mpd_dict:
            props['artist'] = mpd_dict['artist']
        if 'album' in mpd_dict:
            props['album'] = mpd_dict['album']
        if 'date' in mpd_dict:
            props['date'] = mpd_dict['date']

        # append data from filename
        if props.keys() < {'title', 'artist', 'album'}:
            filename_dict = self.get_filename_dict()
            if 'title' not in props and 'title' in filename_dict:
                props['title'] = filename_dict['title']
            if 'artist' not in props and 'artist' in filename_dict:
                props['artist'] = filename_dict['artist']
            if 'album' not in props and 'album' in filename_dict:
                props['album'] = filename_dict['album']
                if 'date' in props:
                    del props['date']

        # append pixbuf from embedded data or local image file
        pixbuf = self.get_pixbuf_from_embedded()
        if pixbuf is not None:
            props['pixbuf'] = pixbuf
        else:
            pixbuf = self.get_pixbuf_from_file()
            if pixbuf is not None:
                props['pixbuf'] = pixbuf

        # append data and pixbuf from the spotify api
        if not props.keys() > {'album', 'pixbuf'} and 'artist' in props and cfg['spotify']['token'] is not None:

            api_dict = None

            if 'album' in props:
                api_dict = self.get_api_data(artist=props['artist'], album=props['album'])
            elif 'title' in props:
                api_dict = self.get_api_data(artist=props['artist'], track=props['title'])

            if api_dict is not None:
                props['artist'] = api_dict['artist']
                props['album'] = api_dict['album']
                props['date'] = api_dict['date']
                props['pixbuf'] = api_dict['pixbuf']

        # remove unwanted substrings from album
        if 'album' in props:

            regex_list = [
                r'\s?(\(|\[)(.*)?(Edition|Extended|Expanded|Remaster|Remastered|Deluxe|Special|Bonus|Box Set|Distribution)(.*)?(\)|\])$',
                r'\s?(\(|\[)(Live|Bootleg|Demo|Music From The Motion Picture Soundtrack)(\)|\])$',
                r'(:\s+|\s+-\s+|\(|\[)(.*)?(Edition|Remaster|Anniversary|Box Set)(\)|\])?$'
            ]

            regex = re.compile(r'\s?(\(|\[)(.*)?(Edition|Extended|Expanded|Remaster|Remastered|Deluxe|Special|Bonus|Box Set|Distribution)(.*)?(\)|\])$|\s?(\(|\[)(Live|Bootleg|Demo|Music From The Motion Picture Soundtrack)(\)|\])$|(:\s+|\s+-\s+|\(|\[)(.*)?(Edition|Remaster|Anniversary|Box Set)(\)|\])?$')
            props['album'] = regex.sub('', props['album'])

        # trim date string down to year
        if 'date' in props:
            try:
                props['date'] = dateutil.parser.parse(props['date']).year
            except dateutil.parser._parser.ParserError:
                pass

        return props

    def get_filename_dict(self):

        string = os.path.splitext(self.filename)[0]
        regex = re.compile(r'\s+-\s+|(?<=^\d{1})\.\s+|(?<=^\d{2})\.\s+|(?<=\s{1}\d{1})\.\s+|(?<=\s{1}\d{2})\.\s+')

        values = [value.strip() for value in regex.split(string)]

        assigned = dict()

        for value in values:
            if re.match(r'^\d{1,2}$', value):
                assigned['track'] = value
                values.remove(value)
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

        file = mutagen.File(self.path)
        data = None

        if file.tags is not None:
            if file.mime[0] == 'audio/mp3':  # mp3
                for tag in file.tags.values():
                    if tag.FrameID == 'APIC' and int(tag.type) == 3:
                        data = tag.data
                        break
            elif file.mime[0] == 'audio/flac':  # flac
                for tag in file.pictures:
                    if tag.type == 3:
                        data = tag.data
                        break
            elif file.mime[0] == 'audio/mp4':  # m4a
                if 'covr' in file.tags.keys():
                    data = file.tags['covr'][0]

        if data is not None:
            try:
                print("info: embedded image found.")
                input_stream = Gio.MemoryInputStream.new_from_data(data, None)
                return Pixbuf.new_from_stream(input_stream, None)
            except TypeError:
                print("warning: embedded image not valid.")

    def get_pixbuf_from_file(self):

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

        folder_pattern = re.compile(r'^{}\/.*$'.format(cfg['mpd']['directory']))

        folder = os.path.dirname(self.path)
        searched = 0

        while folder_pattern.match(folder) and searched <= 2:
            for name in filenames:
                for ext in extensions:
                    path = '{}/{}.{}'.format(folder, name, ext)
                    if os.path.isfile(path):
                        print("info: image file '{}'".format(path))
                        try:
                            return Pixbuf.new_from_file(path)
                        except gi.repository.GLib.Error:
                            print("warning: image file not valid.")

            folder = os.path.abspath(os.path.join(folder, os.pardir))
            searched += 1

    def get_api_data(self, artist=None, album=None, track=None):

        def query_api(artist, album=None, track=None):

            headers = {'Authorization': 'Bearer {}'.format(cfg['spotify']['token'])}

            if album is not None:

                type = 'album'
                params = {'type': type, 'offset': 0, 'limit': 20}
                query_artist = re.sub(r'\'|\s+\(?(feat|ft|with)\.?\s+.*\)?$', '', artist)
                query_album = re.sub('\'', '', album)
                query = "artist:{} AND album:{}".format(query_artist, query_album)

            elif track is not None:

                type = 'track'
                params = {'type': type, 'offset': 0, 'limit': 20}
                query_artist = re.sub(r'\'|\s+\(?(feat|ft|with)\.?\s+.*\)?$', '', artist)
                query_track = re.sub(r'\'|!|\s+\(?(feat|ft|with)\.?\s+.*\)?$|\s?\(Alt\. Version\)$', '', track)
                query = "artist:{} AND track:{}".format(query_artist, query_track)

            else:
                return

            url = "https://api.spotify.com/v1/search?q={}".format(requests.utils.quote(query))

            try:
                response = requests.get(url, headers=headers, params=params)
            except requests.exceptions.ConnectionError:
                print("warning: api connection failed.")
                return

            if response.status_code == 401:
                print("warning: api authorization failed.")
                return 401
            elif response.status_code != 200:
                print("warning: api response invalid, status code {}.".format(response.status_code))
                return

            response_data = response.json()

            if type == 'album' and response_data['albums']['total'] == 0:
                print("warning: no api results for artist:{}, album:{}.".format(artist, album))
                return
            elif type == 'track' and response_data['tracks']['total'] == 0:
                print(url)
                print("warning: no api results for artist:{}, track:{}.".format(artist, track))
                return

            return response_data['{}s'.format(type)]['items']

        def get_pixbuf_from_url(url):

            try:
                response = requests.get(url)
            except requests.exceptions.ConnectionError:
                print("warning: album art api connection failed.")
                return

            if response.status_code != 200:
                print("warning: album art api response invalid.")
                return

            try:
                input_stream = Gio.MemoryInputStream.new_from_data(response.content, None)
                return Pixbuf.new_from_stream(input_stream, None)
            except TypeError:
                print("warning: spotify image data not valid.")

        if artist is not None and album is not None:
            type = 'album'
            api_data = query_api(artist=artist, album=album)
        elif artist is not None and track is not None:
            type = 'track'
            api_data = query_api(artist=artist, track=track)
        else:
            return

        if api_data == 401:

            global cfg
            cfg['spotify']['token'] = get_spotify_token(cfg['spotify']['client_id'], cfg['spotify']['client_secret'])

            if type == 'album':
                api_data = query_api(artist=artist, album=album)
            if type == 'track':
                api_data = query_api(artist=artist, track=track)

            if api_data == 401:
                cfg['spotify']['client_id'] = None
                cfg['spotify']['client_secret'] = None
                cfg['spotify']['token'] = None
                api_data = None

        if api_data is None:
            return

        bad_patterns = re.compile(r'^the karaoke channel -\s?|^karaoke -\s?|^live in|best of|live anthology|^hits|hits$|^rhino hi-five:|greatest hits|ultimate hits|super hits|collection|b-sides|singles|classics|essential|live$|tribute|\'?80s|\'?90s|(\s|^)?\'?00s|80\'s|90\'s|00\'s', flags=re.IGNORECASE)
        selected_index = 0

        for index in range(len(api_data)):

            if type == 'album':
                album_type = api_data[index]['type']
                album = api_data[index]['name']
            elif type == 'track':
                album_type = api_data[index]['album']['type']
                album = api_data[index]['album']['name']

            if not bad_patterns.search(album) and album_type == "album":
                selected_index = index
                break
            else:
                print("skipping:", album)

        if len(api_data[selected_index]['artists']) > 1:
            # artist = api_data[selected_index]['artists'][0]['name'] + " & " + api_data[selected_index]['artists'][1]['name']
            pass
        else:
            artist = api_data[selected_index]['artists'][0]['name']

        if type == 'album':
            selected_record = api_data[selected_index]
        elif type == 'track':
            selected_record = api_data[selected_index]['album']

        album = selected_record['name']
        date = selected_record['release_date']
        image = selected_record['images'][0]['url']

        pixbuf = get_pixbuf_from_url(image)

        return {'artist': artist, 'album': album, 'date': date, 'pixbuf': pixbuf}


def get_spotify_token(client_id, client_secret):

    params = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}

    try:
        response = requests.post('https://accounts.spotify.com/api/token', params)
    except requests.exceptions.ConnectionError:
        print("warning: Could not connect to Spotify API for authorization token.")
        return

    if response.status_code != 200:
        print("warning: api auth response invalid, status code {}.".format(response.status_code))
        return

    response_data = response.json()

    if 'access_token' not in response_data or response_data['access_token'] is None:
        print("warning: Spotify API did not return a valid authorization token.")
        return

    return response_data['access_token']


def get_config():

    def get_mpdconf_data():

        data = dict()
        path = os.path.join(os.getenv('XDG_CONFIG_HOME', os.path.expanduser("~/.config")), 'mpd/mpd.conf')
        if os.path.isfile(path):
            data = dict()
            if path is not None:
                for line in open(path, 'r'):
                    line = line.strip()
                    if not line.startswith('#') and ' ' in line:
                        key, value = line.split(maxsplit=1)
                        value = value.strip('\"').strip('\'')
                        if key == 'music_directory' and os.path.isdir(os.path.expanduser(value)):
                            data['directory'] = os.path.expanduser(value)
                        elif key == 'bind_to_address' and re.match(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$', value):
                            data['host'] = value
                        elif key == 'port':
                            try:
                                data['port'] = int(value)
                            except ValueError:
                                print("warning: failed to convert value '{}' to integer for port in mpd.conf.".format(value))
                        elif key == 'password':
                            data['password'] = value

                        if data.keys() >= {'directory', 'host', 'port', 'password'}:
                            break

            return data

    def get_config_data():

        fields = {
            'mpd': ['directory', 'host', 'port', 'password'],
            'spotify': ['client_id', 'client_secret'],
            'notify': ['default_image', 'id', 'timeout', 'urgency']
        }

        data = dict()
        config_path = os.path.join(os.getenv('XDG_CONFIG_HOME', os.path.expanduser("~/.config")), 'nowplaying/config.ini')
        if os.path.isfile(config_path):
            config = configparser.ConfigParser()
            config.read(config_path)
            for section in config.sections():
                data[section] = dict()
                if section in fields:
                    for key, value in config.items(section):
                        if value != '' and key in fields[section]:
                            if section == 'mpd' and key == 'directory' and os.path.isdir(value):
                                data[section][key] = value
                            elif section == 'notify' and key == 'default_image' and os.path.isfile(value):
                                try:
                                    data[section]['default_image'] = value
                                    data[section]['default_pixbuf'] = Pixbuf.new_from_file(value)
                                except gi.repository.GLib.Error:
                                    print("warning: failed to create pixbuf from default image '{}'.".format(value))
                            elif section == 'notify' and key == 'urgency':
                                if value in ('0', 'low'):
                                    data[section][key] = notify2.URGENCY_LOW
                                elif value in ('1', 'normal'):
                                    data[section][key] = notify2.URGENCY_NORMAL
                                elif value in ('2', 'critical'):
                                    data[section][key] = notify2.URGENCY_CRITICAL
                            elif key in ('port', 'id', 'timeout'):
                                try:
                                    data[section][key] = int(value)
                                except ValueError:
                                    print("warning: failed to convert field cfg['{}']['{}'] value '{}' to integer.".format(section, key, value))
                            else:
                                data[section][key] = value

                    if data[section] == dict():
                        del data[section]

        return data

    # create empty dictionary for config data
    merged_data = {
        'mpd': {'directory': None, 'host': None, 'port': None, 'password': None},
        'notify': {'default_image': None, 'default_pixbuf': None, 'id': None, 'timeout': None, 'urgency': None},
        'spotify': {'client_id': None, 'client_secret': None, 'token': None}
    }

    # append mpd.conf data to dictionary
    mpdconf_data = get_mpdconf_data()
    if mpdconf_data is not None and bool(mpdconf_data):
        for key, value in mpdconf_data.items():
            merged_data['mpd'][key] = value

    # append config.ini data to dictionary
    config_data = get_config_data()
    if config_data is not None and bool(config_data):
        for section in config_data.keys():
            if section in merged_data:
                for key, value in config_data[section].items():
                    if key in merged_data[section]:
                        merged_data[section][key] = value

    # check dictionary for necessary mpd data
    if merged_data['mpd']['directory'] is None:
        sys.exit("error: no valid mpd directory specified.")
    if merged_data['mpd']['host'] is None:
        sys.exit("error: no valid mpd host specified.")
    if merged_data['mpd']['port'] is None:
        sys.exit("error: no valid mpd port specified.")

    # append spotify authorization token to data
    if merged_data['spotify']['client_id'] is not None and merged_data['spotify']['client_secret'] is not None:
        merged_data['spotify']['token'] = get_spotify_token(merged_data['spotify']['client_id'], merged_data['spotify']['client_secret'])
        print("info: spotify token '{}'".format(merged_data['spotify']['token']))
    else:
        print("warning: no spotify token.")

    return merged_data


def cancel_process(client=None, nobj=None):

    sys.stdout.write('\b\b\r')

    print("Quitting..")

    if client is not None:
        client.close()

    if nobj is not None:
        nobj.close()

    sys.exit(0)


def get_arguments():

    parser = argparse.ArgumentParser(prog=PROG, usage="%(prog)s [options]", description="Send notifications when MPD track changes.", prefix_chars='-')
    parser.add_argument("-n", "--now", action="store_true", default=False, help="Send a notification for current track immediately and exit.")

    return parser.parse_args()


def get_client():

    host, port, password = list(cfg['mpd'].values())[1:4]

    obj = mpd.MPDClient()

    obj.timeout = 10

    if password is not None:
        obj.password('password')

    try:
        obj.connect(host, port)
    except ConnectionRefusedError:
        sys.exit(f"error: could not connect to MPD at {host}, port {str(port)}.")
    except OSError:
        sys.exit(f"error: connection attempt to MPD at {host}, port {str(port)} timed out after {obj.timeout} second(s).")

    return obj


def get_notification():

    try:
        notify2.init(PROG)
    except Exception:
        sys.exit("error: cannot create notification.")

    obj = notify2.Notification(PROG, "Starting MPD Notifications..")

    obj.set_hint('desktop-entry', PROG)

    if cfg['notify']['default_pixbuf'] is not None:
        obj.set_icon_from_pixbuf(cfg['notify']['default_pixbuf'])

    id, timeout, urgency = list(cfg['notify'].values())[2:]

    if id is not None:
        obj.id = id

    if timeout is not None:
        obj.set_timeout(timeout)

    if urgency is not None:
        obj.set_urgency(urgency)

    obj.show()

    if 'icon_data' in obj.hints:
        del obj.hints['icon_data']

    return obj


def get_notify_message(props):

    message = None

    if 'title' in props:

        if len(props['title']) > 30:
            size = 'small'
        else:
            size = 'medium'

        message = "<span size='{}'><b>{}</b></span>".format(size, props['title'])

        if 'album' in props:

            if 'date' in props:
                line_length = len("on {} ({})".format(props['album'], props['date']))
            else:
                line_length = len("on {}".format(props['album']))

            if line_length > 30:
                size = 'small'
            else:
                size = 'medium'

            if 'date' in props:
                message += "\n<span size='x-small'>on </span><span size='{}'><b>{}</b> (<b>{}</b></span>)".format(size, props['album'], props['date'])
            else:
                message += "\n<span size='x-small'>on </span><span size='{}'><b>{}</b></span>".format(size, props['album'])

        if 'artist' in props:

            line_length = len("by {}".format(props['artist']))

            if line_length > 30:
                size = 'small'
            else:
                size = 'medium'

            message += "\n<span size='x-small'>by </span><span size='{}'><b>{}</b></span>".format(size, props['artist'])

    return message


def notify_user(client, nobj):

    # gather notification data
    song = SongInfo(client.currentsong())
    message = get_notify_message(song.props)

    # update notification message
    nobj.update(PROG, message)

    # update notification icon
    if 'pixbuf' in song.props:
        nobj.set_icon_from_pixbuf(song.props['pixbuf'])
    elif cfg['notify']['default_pixbuf'] is not None:
        nobj.set_icon_from_pixbuf(cfg['notify']['default_pixbuf'])
    elif 'icon_data' in nobj.hints:
        del nobj.hints['icon_data']

    # if song has not changed, show notification
    if client.currentsong()['id'] == song.id:
        nobj.show()


def notify_on_event(client, nobj):

    prev_songid, prev_state = None, None

    while client.idle('player'):

        songid, state = client.currentsong()['id'], client.status()['state']

        if state == 'play' and (prev_state != 'play' or prev_songid != songid):
            notify_user(client, nobj)

        prev_songid, prev_state = songid, state


def main():

    client, nobj = None, None

    signal.signal(signal.SIGINT, lambda x, y: cancel_process(client, nobj))
    signal.signal(signal.SIGTERM, lambda x, y: cancel_process(client, nobj))

    args = get_arguments()

    global cfg
    cfg = get_config()

    client = get_client()
    nobj = get_notification()

    if args.now:
        notify_user(client, nobj)
        client.close()
    else:
        notify_on_event(client, nobj)

    client.disconnect()


if __name__ == "__main__":
    main()

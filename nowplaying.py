#!/usr/bin/python

"""
TODO: get_image_data - add code for wma, wav, ogg
TODO: get_image_path - folder_name_patterns - perfect patterns for numbers as digits and strings
TODO: get_image_path - _get_folder_image - add all valid cover art filenames
"""

import argparse
import os.path
import re
import signal
import sys
import urllib.request
from re import match

import dbus
import gi.repository
import notify2
import requests
from gi.repository import Gio
from mpd import MPDClient as MPDClient
from mutagen import File as MutagenFile

gi.require_version("GdkPixbuf", "2.0")
from pprint import pprint

from gi.repository.GdkPixbuf import Pixbuf

PROG = 'nowplaying'
MPD_SETTINGS = {'host': 'localhost', 'port': 6600,
                'password': None, 'timeout': None, 'idletimeout': None}
NOTIFY_SETTINGS = {'default_image': '/home/user/images/icon/pacman/red.png',
                   'id': 999999, 'timeout': 1500, 'urgency': 0}


def get_image_data(path=None):
    """
    Retreive embedded image data from audio file.\n
    Supports: mp3, m4a, flac (wma, ogg, wav).\n
    If no image, None is returned.\n
    Args:
    - path (string)
    """

    file = MutagenFile(path)

    # if a valid file with valid tags was found, proceed
    if file and file.tags and len(file.tags.values()) > 0:

        # declare acceptable values for embedded image tag.type
        types = [
            3,  # Cover (front)
            2,  # Other file icon
            1,  # 32x32 pixel PNG file icon
            0,  # Other
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


def get_image_path(path=None):
    """
    Locate path of local album cover image in matching folders.\n
    If no image, None is returned.\n
    Args:
    - path (string)
    """

    def _get_folder_image(folder):
        """
        Locate album cover image in specified folder.\n
        If no image, None is returned.\n
        Args:
        - folder (string)
        """

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
        os.path.basename(os.path.dirname(path)),
        os.path.splitext(path)[-1].lstrip('.')
    ]

    folder_path = os.path.dirname(path)
    folder_name = os.path.basename(folder_path)

    while re.match("|".join(folder_name_patterns), folder_name.lower()):

        image_path = _get_folder_image(folder_path)

        if image_path:
            return image_path

        folder_path = os.path.abspath(os.path.join(folder_path, os.pardir))
        folder_name = os.path.basename(folder_path)


def get_filename_dict(path=None):
    """
    Get dictionary of track data parsed from filename in specified path.\n
    Dictionary elements returned are title, album, artist and track.\n
    Args:
    - path (string)
    """

    def _get_split_filename(filename):
        """
        Split filename string into a list of track properties.\n
        Args:
        - filename (string)
        """

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
        chunks = re.split(r'\s+-\s+', string)

        # replace protected patterns with original values
        cleaned_chunks = []
        for chunk in chunks:
            for i in range(len(ignore_patterns)):
                chunk = chunk.replace(
                    ignore_patterns[i]['replace'], ignore_patterns[i]['initial'])
            cleaned_chunks.append(chunk.strip())

        return cleaned_chunks

    filename = os.path.basename(path)

    chunks = _get_split_filename(filename)
    assigned = dict()

    # search for track number and add it to dict
    for chunk in chunks:
        if re.match(r'^\d{1,2}$', chunk):
            assigned['track'] = chunk
            chunks.remove(chunk)
            break

    # if more than three values in list, delete all buy last three values
    if len(chunks) > 3:
        del chunks[:2]

    if len(chunks) == 3:
        assigned['artist'], assigned['album'], assigned['title'] = chunks[0], chunks[1], chunks[2]
    elif len(chunks) == 2:
        assigned['artist'], assigned['title'] = chunks[0], chunks[1]
    elif len(chunks) == 1:
        assigned['title'] = chunks[0]

    return assigned


def _album_contains_bad_substrings(album=None):
    """
    Returns True if album name contains unwanted substrings.\n
    Args:
    - name (string)
    """

    unwanted_substrings = ('best of', 'greatest hits', 'collection', 'b-sides', 'classics')

    return any([substring in album.lower() for substring in unwanted_substrings])


def get_spotify_access_token():
    """
    Get auth token for Spotify API.\n
    If no token, None is returned.
    """

    access_token = None

    auth_response = requests.post('https://accounts.spotify.com/api/token', {
        'grant_type': 'client_credentials',
        'client_id': '3ad71cf0ae544e7e935927e5d9a5cbad',
        'client_secret': '862905d9380645a9ba29789308d795d5',
    })

    auth_response_data = auth_response.json()
    access_token = auth_response_data['access_token']

    if access_token:
        return access_token


def api_album_data(artist=None, album=None, token=None):
    """
    Request album data from Spotify API and compile results as a dictionary.\n
    If no records found, None is returned.\n
    Args:
    - artist (string)
    - album (string)
    - token (string)
    """

    if not token:
        token = get_spotify_access_token()

    headers = {'Authorization': f'Bearer {token}'}
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

        # get the index for the first acceptable record
        for index in range(len(album_records)):
            record = album_records[index]
            if record.keys() >= {'album_type', 'artists', 'name', 'release_date', 'images'}:
                album = record['name']
                type = record['album_type']
                if type == "album" and not _album_contains_bad_substrings(album):
                    record_index = index
                    break

        # if no index was selected, validate the first record and set selected index to 0
        if not isinstance(record_index, int):
            record = album_records[0]
            if record.keys() >= {'album_type', 'artists', 'name', 'release_date', 'images'}:
                record_index = 0

        # if a record index was selected, return the values for that record
        if isinstance(record_index, int):
            record = album_records[record_index]
            artist = record['artists'][0]['name']
            album = record['name']
            date = record['release_date']
            image = record['images'][0]['url']
            return {'artist': artist, 'album': album, 'date': date, 'image_url': image}


def api_track_data(artist=None, track=None, token=None):
    """
    Request track data from Spotify API and compile results as a dictionary.\n
    If no records found, None is returned.\n
    Args:
    - artist (string)
    - track (string)
    - token (string)
    """

    if not token:
        token = get_spotify_access_token()

    headers = {'Authorization': f'Bearer {token}'}
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

        # get the index for the first acceptable record
        for index in range(len(track_records)):
            record = track_records[index]
            if record['album'].keys() >= {'type', 'name', 'release_date', 'images'}:
                type = record['album']['type']
                album = record['album']['name']
                if type == "album" and not _album_contains_bad_substrings(album):
                    record_index = index
                    break

        # if no index was selected, validate the first record and set selected index to 0
        if not isinstance(record_index, int):
            record = track_records[0]
            if record['album'].keys() >= {'type', 'name', 'release_date', 'images', 'artists'}:
                record_index = 0

        # if a record index was selected, return the values for that record
        if isinstance(record_index, int):
            record = track_records[record_index]
            title = record['name']
            artist = record['artists'][0]['name']
            album = record['album']['name']
            date = record['album']['release_date']
            image = record['album']['images'][0]['url']
            return {'title': title, 'artist': artist, 'album': album, 'date': date, 'image_url': image}


def get_track_info(mpd_dict, path, token):
    """
    Compile track info from all sources into a dictionary.\n
    Dictionary elements are: title, artist, album, date, image_data, image_path and image_url.\n
    Args:
    - mpd_dict (dict)
    - path (string)
    - token (string)
    """

    def _get_clean_album_string(album):
        """
        Remove unwanted substrings from album string.\n
        Args:
        - album (string)
        """

        return re.sub(r'\s?(\(|\[)[^\)]*(edition|release|remaster|remastered)(\)|\])$', '', album, flags=re.IGNORECASE).strip()

    def _get_clean_date_string(date):
        """
        Trim date string to a four digit year.\n
        Args:
        - date (string)
        """

        # if string begins with year, return first four characters
        if date and re.match(r'^19\d{2}\D?.*$|^20\d{2}\D?.*$', date):
            return date[0:4]
        # else if string ends with year, return last four characters
        elif date and re.match(r'|^.*\D19\d{2}$|^.*\D20\d{2}$', date):
            return date[-4:]
        else:
            return date

    props = dict()

    # append data from mpd to props
    if 'title' in mpd_dict:
        props['title'] = mpd_dict['title']
    if 'artist' in mpd_dict:
        props['artist'] = mpd_dict['artist']
    if 'album' in mpd_dict:
        props['album'] = mpd_dict['album']
    if 'date' in mpd_dict:
        props['date'] = mpd_dict['date']

    # if title, artist or album missing from props, append missing data from filename
    if 'title' not in props or 'artist' not in props or 'album' not in props:

        filename_dict = get_filename_dict(path)

        if 'title' not in props and 'title' in filename_dict:
            props['title'] = filename_dict['title']
        if 'artist' not in props and 'artist' in filename_dict:
            props['artist'] = filename_dict['artist']
        if 'album' not in props and 'album' in filename_dict:
            props['album'] = filename_dict['album']

    # append embedded image data to props
    props['image_data'] = get_image_data(path)

    if not props['image_data']:
        del props['image_data']

    # if image data not in props, append image path
    if 'image_data' not in props:

        props['image_path'] = get_image_path(path)

        if not props['image_path']:
            del props['image_path']

    # if album or image data and path missing from props
    if 'album' not in props or ('image_data' not in props and 'image_path' not in props):

        if 'artist' in props and 'album' in props:
            api_dict = api_album_data(artist=props['artist'], album=props['album'], token=token)
        elif 'artist' in props and 'title' in props:
            api_dict = api_track_data(artist=props['artist'], track=props['title'], token=token)
        else:
            api_dict = None

        # if api returned results, append missing data to props
        if api_dict and api_dict.keys() >= {'artist', 'title', 'album', 'date', 'image_url'}:

            print("api_dict:")
            pprint(api_dict)

            # clear incomplete image fields from props
            if 'image_data' in props:
                del props['image_data']
            if 'image_path' in props:
                del props['image_path']

            # append api results to props
            if 'title' in api_dict:
                props['title'] = api_dict['title']
            props['artist'] = api_dict['artist']
            props['album'] = api_dict['album']
            props['date'] = api_dict['date']
            props['image_url'] = api_dict['image_url']

    # clean album name of unwanted substrings
    if 'album' in props:
        props['album'] = _get_clean_album_string(props['album'])

    # reduce date string to year, if possible
    if 'date' in props:
        props['date'] = _get_clean_date_string(props['date'])

    print("props:")
    pprint(props)

    return props


def send_notification(prog, notify_settings, props):
    """
    Send a notification containing track info and an album cover image.\n
    Args:
    - prog (string)
    - notify_settings (tuple)
    - props (dictionary)
    """

    def _get_notification_message(props):
        """
        Compile track info into a notification string.\n
        If no track info, returns None.
        Args:
        - props (dictionary)
        """

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

    def _get_pixbuf_from_image(props, default_image=None):
        """
        Create a pixbuf from image data, image path or image url.\n
        If no image, None is returned.\n
        Args:
        - props (dictionary)
        - default_image (string)
        """

        if 'image_data' in props:
            try:
                input_stream = Gio.MemoryInputStream.new_from_data(
                    props['image_data'], None)
                return Pixbuf.new_from_stream(input_stream, None)
            except Exception:
                return None

        if 'image_path' in props:
            try:
                return Pixbuf.new_from_file(props['image_path'])
            except Exception:
                return None

        if 'image_url' in props:
            try:
                response = urllib.request.urlopen(props['image_url'])
                input_stream = Gio.MemoryInputStream.new_from_data(
                    response.read(), None)
                return Pixbuf.new_from_stream(input_stream, None)
            except Exception:
                return None

        if default_image and os.path.exists(default_image):
            try:
                return Pixbuf.new_from_file(default_image)
            except Exception:
                return None

    notify_message = _get_notification_message(props)

    if notify_message:

        try:
            notify2.init(prog)
            n = notify2.Notification(prog, notify_message)
        except dbus.exceptions.DBusException:
            print("error: daemon not found.")
            sys.exit(0)

        if bool(notify_settings['id']):
            n.id = notify_settings['id']

            n.set_hint('desktop-entry', prog)
            n.set_timeout(notify_settings['timeout'])
            n.set_urgency(notify_settings['urgency'])

            pixbuf = _get_pixbuf_from_image(props, notify_settings['default_image'])

            if bool(pixbuf):
                n.set_icon_from_pixbuf(pixbuf)

                try:
                    n.show()
                except Exception:
                    print("error: failed to send notification.")


def get_arguments(prog=PROG):
    """
    Get command line arguments object.\n
    Args:
    - prog (string)
    """

    parser = argparse.ArgumentParser(
        prog=prog, usage="%(prog)s [options]", description="Send notification for current MPD track.", prefix_chars='-')
    parser.add_argument("--once", "-o", action="store_true",
                        default=False, help="Send one notification and exit")

    return parser.parse_args()


def open_mpd_connection(mpd_settings=MPD_SETTINGS):
    """
    Connect to an MPD server socket.\n
    If no socket, None is returned.\n
    Args:
    - mpd_settings (tuple)
    """

    client = MPDClient()

    if mpd_settings['timeout']:
        client.timeout = mpd_settings['timeout']

    if mpd_settings['idletimeout']:
        client.idletimeout = mpd_settings['idleidletimeout']

    if mpd_settings['password']:
        client.password(mpd_settings['password'])

    try:
        client.connect(mpd_settings['host'], mpd_settings['port'])
    except ConnectionRefusedError:
        sys.exit(
            f"error: could not connect to {mpd_settings['host']}:{str(mpd_settings['port'])}")

    return client


def get_music_directory():
    """
    Parse the path to the MPD music directory from mpd.conf.\n
    If no directory found, None is returned.
    """

    paths = (
        "{}/mpd/mpd.conf".format(os.getenv('XDG_CONFIG_HOME')),
        "{}/.config/mpd/mpd.conf".format(os.getenv('HOME')),
        "/home/{}/.config/mpd/mpd.conf".format(os.getenv('USER')),
        "/home/{}/.config/mpd/mpd.conf".format(os.getlogin())
    )

    for path in paths:
        if os.path.isfile(path):
            for line in open(path, 'r'):
                if match(r'^music_directory\s+\".*\"$', line):
                    return os.path.expanduser(line.strip().split()[-1].strip('\"'))
                elif match(r'^music_directory\s+\'.*\'$', line):
                    return os.path.expanduser(line.strip().split()[-1].strip("\'"))


def notify_now(client, music_directory, token=None, prog=PROG, notify_settings=NOTIFY_SETTINGS):
    """
    Gather track info and send a notification.\n
    None is returned.\n
    Args:
    - client (object)
    - music_directory (string)
    - token (string)
    - prog (string)
    - notify_settings (tuple)
    """

    if bool(client.currentsong()) and 'file' in client.currentsong() and 'state' in client.status() and client.status()['state'] in ("play", "pause", "stop"):

        path = os.path.join(music_directory, client.currentsong()['file'])

        props = get_track_info(client.currentsong(), path, token)

        if props and path == os.path.join(music_directory, client.currentsong()['file']):
            send_notification(prog, notify_settings, props)


def notify_on_change(client, music_directory, token=None, prog=PROG, notify_settings=NOTIFY_SETTINGS):
    """
    Monitor MPD socket and send track notifications when a new track starts or current track changes.\n
    None is returned.\n
    Args:
    - client (object)
    - music_directory (string)
    - token (string)
    - prog (string)
    - notify_settings (tuple)
    """

    def _interrupt_signal(client):
        """
        Close MPD socket and exit with success when interrupt signal is received.
        """

        sys.stdout.write('\b\b\r')

        if client:
            client.close()

        sys.exit(0)

    signal.signal(signal.SIGINT, lambda x, y: _interrupt_signal(client))

    while client.idle('player'):

        if client.status()['state'] == 'play':

            notify_now(client, music_directory, token, prog, notify_settings)


def main(prog=PROG, mpd_settings=MPD_SETTINGS, notify_settings=NOTIFY_SETTINGS):

    token = get_spotify_access_token()

    music_directory = get_music_directory()

    client = open_mpd_connection(mpd_settings)

    arguments = get_arguments(prog)

    if arguments.once:
        notify_now(client, music_directory, token, prog, notify_settings)
    else:
        notify_on_change(client, music_directory, token, prog, notify_settings)

    client.close()
    client.disconnect()


if __name__ == "__main__":
    main()

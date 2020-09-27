#!/usr/bin/python

import argparse
import dateutil.parser
import dbus
import logging
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
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio
from gi.repository.GdkPixbuf import Pixbuf


PROG = "nowplaying"
LASTFM_API_KEY = "11353ee2e14240f46be72d71726f3f79"
DEFAULT_IMAGE_PATH = '/home/user/images/icon/pacman/red.png'

MPD_BIND_ADDRESS = "127.0.0.1"
MPD_BIND_PORT = 6600
MPD_PASSWORD = None
MPD_TIMEOUT = None
MPD_IDLE_TIMEOUT = None

NOTIFY_ID = 999999
NOTIFY_TIMEOUT = 1500
NOTIFY_URGENCY = 0


class SongInfo:

    def __init__(self, mpd_dict=None, api='lastfm', api_key=None, music_directory=None):

        os.system('clear')

        self.id = self.path = self.folder = self.filename = self.title = self.artist = \
            self.album = self.date = self.image_data = self.image_path = self.image_url = None

        self.api = api
        self.api_key = api_key
        self.music_directory = music_directory

        self.append_mpd_data(mpd_dict)

        if None in (self.title, self.artist, self.album):
            self.append_filename_data()

        self.image_data = self.get_embedded_image_data()

        if not self.image_data:
            self.image_path = self.get_local_image_path()

        if None in (self.title, self.artist, self.album) or (not self.image_data and not self.image_path):
            self.append_data_from_api()

    def _clean_date_string(self, date):

        if re.match(r'^19\d{2}\D?.*$|^20\d{2}\D?.*$|^.*\D19\d{2}$|^.*\D20\d{2}$', date):
            return dateutil.parser.parse(date).year
        else:
            return date

    def append_mpd_data(self, mpd_dict):

        self.id = mpd_dict['id']
        self.path = os.path.join(self.music_directory, mpd_dict['file'])
        self.folder = os.path.dirname(self.path)
        self.filename = os.path.basename(self.path)
        self.extension = self.filename.split('.')[-1]

        if 'title' in mpd_dict:
            logging.info(f"self.title = mpd_dict['title'] = {mpd_dict['title']}")
            self.title = mpd_dict['title']

        if 'album' in mpd_dict:
            logging.info(f"self.album = mpd_dict['album'] = {mpd_dict['album']}")
            self.album = mpd_dict['album']

        if 'artist' in mpd_dict:
            logging.info(f"self.artist = mpd_dict['artist'] = {mpd_dict['artist']}")
            self.artist = mpd_dict['artist']

        if 'date' in mpd_dict:
            logging.info(f"self.date = self.trim_date(mpd_dict['date']) = {self._clean_date_string(mpd_dict['date'])}")
            self.date = self._clean_date_string(mpd_dict['date'])

    def _split_filename(self):

        # strip extension from filename
        string = os.path.splitext(self.filename)[0]

        # declare patterns to be ignored while spliting the filename into sections
        ignore_patterns = [
            {'initial_value': 'Mr. ', 'replace_value': '((MISTERDOT))'},
            {'initial_value': 'Mrs. ', 'replace_value': '((MISSESDOT))'},
            {'initial_value': 'Dr. ', 'replace_value': '((DOCTORDOT))'},
            {'initial_value': 'Jr. ', 'replace_value': '((JUNIORDOT))'},
            {'initial_value': 'Sr. ', 'replace_value': '((SENIORDOT))'},
            {'initial_value': 'Vol. ', 'replace_value': '((VOLDOT))'},
            {'initial_value': 'Ep. ', 'replace_value': '((EPDOT))'}
        ]

        # replace all patterns to be ignored in string with replacement patterns that will not cause a split
        for i in range(len(ignore_patterns)):
            string = string.replace(ignore_patterns[i]['initial_value'], ignore_patterns[i]['replace_value'])

        # split sections into list
        string_list = re.split('\\s?\\.\\s+|\\s?-\\s+|\\s+-\\s?', string)

        # replace all replacement patterns in chunks with original patterns
        cleaned_string_list = []
        for var in string_list:
            for i in range(len(ignore_patterns)):
                var = var.replace(ignore_patterns[i]['replace_value'], ignore_patterns[i]['initial_value'])
            cleaned_string_list.append(var.strip())

        return cleaned_string_list

    def _get_data_from_filename(self):

        unassigned_values = self._split_filename()
        unassigned_fields = ['artist', 'album', 'title']
        found_data = {}

        # if track in unassigned_values then check all values for a track number and assign it
        for val in unassigned_values:
            if re.match(r'^\d{1,2}$', val):
                unassigned_values.remove(val)
                break

        if 'album' in unassigned_fields and len(unassigned_fields) > len(unassigned_values):
            unassigned_fields.remove('album')

        elif len(unassigned_values) > len(unassigned_fields):

            # while more unassigned_fields than unassigned_values remove first item in unassigned_fields
            while len(unassigned_values) > len(unassigned_fields):
                del unassigned_values[0]

        # assign remaining unassigned_values to remaining unassigned_fields
        for i in range(len(unassigned_values) - 1, -1, -1):
            found_data[unassigned_fields[-1]] = unassigned_values[-1]
            unassigned_fields.remove(unassigned_fields[-1])
            unassigned_values.remove(unassigned_values[-1])

        return found_data

    def append_filename_data(self):

        filename_dict = self._get_data_from_filename()

        if not self.title and 'title' in filename_dict:
            logging.info(f"self.title = filename_dict['title'] = {filename_dict['title']}")
            self.title = filename_dict['title']

        if not self.artist and 'artist' in filename_dict:
            logging.info(f"self.artist = filename_dict['artist'] = {filename_dict['artist']}")
            self.artist = filename_dict['artist']

        if not self.album and 'album' in filename_dict:
            logging.info(f"self.album = filename_dict['album'] = {filename_dict['album']}")
            self.album = filename_dict['album']
            self.date = None

    # ADD ALL IMAGE FORMATS AND HANDLE ALL IMAGE TAG TYPES
    def get_embedded_image_data(self):

        file = mutagen.File(self.path)

        self.mimetype = file.mime[0]

        if file and len(file.tags.values()) > 0:

            if self.mimetype == "audio/mp4":

                if 'covr' in file.tags.keys():
                    logging.info(f"self.image_data = file.tags['covr'][0]")
                    return file.tags['covr'][0]

            elif self.mimetype == "audio/mp3":

                for tag in file.tags.values():
                    if tag.FrameID == 'APIC' and tag.type == 3:
                        logging.info(f"self.image_data = tag.data")
                        return tag.data

                for tag in file.tags.values():
                    if tag.FrameID == 'APIC' and tag.type == 0:
                        logging.info(f"self.image_data = tag.data")
                        return tag.data

            elif self.mimetype == "audio/flac":

                for tag in file.pictures:
                    if tag.type == 3:
                        logging.info(f"self.image_data = tag.data")
                        return tag.data

    def _get_folder_image(self, folder):

        filenames = ["cover", "Cover", "front", "Front", "folder", "Folder", "thumb", "Thumb", "album", "Album", "albumart", "AlbumArt", "albumartsmall", "AlbumArtSmall"]
        extensions = ["png", "jpg", "jpeg", "gif", "svg", "bmp", "tif", "tiff"]

        # check for the existence of a file in current folder that macthes a combination of filenames and extensions
        for name in filenames:
            for ext in extensions:
                path = folder + '/' + name + '.' + ext
                logging.debug(f"look for image = {path}")
                if os.path.exists(path):
                    return path

    def get_local_image_path(self):

        matching_folder_names = [r'^disc\s?\d+.*$', r'^cd\s?\d+.*$', r'^dvd\s?\d+.*$', r'^set\s?\d+.*$']

        # if self.extension exists then append it to matching_folder_names
        if self.extension:
            matching_folder_names.append(self.extension.lower())

        # if self.artist exists then append it to matching_folder_names
        if self.artist:
            matching_folder_names.append(self.artist.replace("/", "_").lower())

        # if self.album exists then append it to matching_folder_names
        if self.album:
            matching_folder_names.append(r'^.*' + self.album.replace("/", "_").lower() + '$')

        # set initial value of current folder to the directory of the audio file
        current_folder = self.folder
        current_folder_name = os.path.basename(current_folder)

        # append initial folder to matching_folder_names
        if current_folder_name not in matching_folder_names:
            matching_folder_names.append(os.path.basename(current_folder))

        logging.debug("\n" + str(matching_folder_names) + "\n")

        # while current_folder_name matches a folder in matching_folder_names and current folder is not "/" or self.music_directory
        while re.match("|".join(matching_folder_names), current_folder_name.lower()) and current_folder not in ("/", self.music_directory):

            # check current_folder for image
            # print(f"check folder = {current_folder}")
            image_path = self._get_folder_image(current_folder)

            # if an image_path was found then return it
            if image_path:
                logging.info(f"self.image_path = self.get_local_image_path() = {image_path}")
                return image_path

            # set current_folder to its parent folder
            current_folder = os.path.abspath(os.path.join(current_folder, os.pardir))
            current_folder_name = os.path.basename(current_folder)

    def _query_api(self, payload):

        headers = {'user-agent': 'Dataquest'}

        if self.api == "lastfm":
            payload['api_key'] = self.api_key
            payload['format'] = 'json'
            url = "http://ws.audioscrobbler.com/2.0/"
        elif self.api == "deezer":
            url = "http://api.deezer.com/search/autocomplete"

        try:
            response = requests.get(url, headers=headers, params=payload)
            return response.json()
        except requests.exceptions.ConnectionError:
            return None

    def _dict_keys_exist(self, element, *keys):

        if not isinstance(element, dict):
            raise AttributeError('keys_exists() expects dict as first argument.')

        if len(keys) == 0:
            raise AttributeError('keys_exists() expects at least two arguments, one given.')

        for key in keys:
            try:
                element = element[key]
            except KeyError:
                return False

        return True

    def _clean_album_name_string(self, name):

        # remove unwanted strings from album name
        album_remove_strings = [
            r'\(\d{4}\sRemaster\)',
            r'\[\d{4}\sRemaster\]',
            r'\(\d{4}\sRemastered\)',
            r'\[\d{4}\sRemastered\]',
            r'\(Deluxe Edition\)',
            r'\[Deluxe Edition\]',
            r'\(Special Edition\)',
            r'\[Special Edition\]',
            r'\(Remaster\)',
            r'\[Remaster\]',
            r'\(Remastered\)'
            r'\[Remastered\]'
        ]

        for val in album_remove_strings:
            name = re.sub(val, "", name).strip()

        return name

    def _request_album_data(self):

        if self.api == "lastfm":

            api_payload = {'method': 'album.getInfo', 'artist': self.artist, 'album': self.album}
            results = self._query_api(api_payload)

            if "error" in results:
                return {"found": False}

            expected_keys = ['album', 'image', 2, '#text']
            if self._dict_keys_exist(results, *expected_keys) and results['album']['image'][2]['#text'] != "":
                return {'found': True, 'image_url': results['album']['image'][2]['#text']}

        elif self.api == "deezer":

            api_payload = {'q': self.artist + "%20" + self.album}
            print("api_payload = " + api_payload['q'])
            results = self.query_api(api_payload)

            if len(results['tracks']['data']) == 0:
                return {'found': False}

            expected_keys = ['albums', 'data', 0, 'cover_medium']
            if self._dict_keys_exist(results, *expected_keys) and results['albums']['data'][0]['cover_medium'] != "":

                print("image = " + results['albums']['data'][0]['cover_medium'])
                return {'found': True, 'image_url': results['albums']['data'][0]['cover_medium']}

    def _request_track_data(self):

        album = image_url = track = None

        if self.api == "lastfm":

            api_payload = {'method': 'track.getInfo', 'artist': self.artist, 'track': self.title}
            results = self._query_api(api_payload)

            if "error" in results or "track" not in results or "album" not in results["track"]:
                logging.info("===== NOT FOUND ===== self._request_track_data ===== NOT FOUND =====")
                return {"found": False}

            expected_keys = ['track', 'album', 'title']
            if self._dict_keys_exist(results, *expected_keys) and results['track']['album']['title'] != "":
                album = results['track']['album']['title']

            expected_keys = ['track', 'album', 'image', 2, '#text']
            if self._dict_keys_exist(results, *expected_keys) and results['track']['album']['image'][2]['#text'] != "":
                image_url = results['track']['album']['image'][2]['#text']

        elif self.api == "deezer":

            api_payload = {'q': self.artist + "%20" + self.title}
            results = self._query_api(api_payload)

            if "tracks" not in results or "data" not in results["tracks"] or len(results['tracks']['data']) == 0:
                logging.info("===== NOT FOUND ===== self._request_track_data ===== NOT FOUND =====")
                return {'found': False}

            # locate album_index for first album name not containing an unwanted substring
            album_index = 0  # set default value in case no album_index is chosen
            unwanted_substrings = ["best of", "greatest hits", "collection", "b-sides"]
            for index in range(0, len(results['tracks']['data'])):
                string = results['tracks']['data'][index]['album']['title']
                if not any([substring in string.lower() for substring in unwanted_substrings]):
                    album_index = index
                    break

            expected_keys = ['tracks', 'data', album_index, 'album', 'title']
            if self._dict_keys_exist(results, *expected_keys) and results['tracks']['data'][album_index]['album']['title'] != "":
                album = results['tracks']['data'][album_index]['album']['title']
                album = self._clean_album_name_string(album)

            expected_keys = ['tracks', 'data', album_index, 'album', 'cover_medium']
            if self._dict_keys_exist(results, *expected_keys) and results['tracks']['data'][album_index]['album']['cover_medium'] != "":
                image_url = results['tracks']['data'][album_index]['album']['cover_medium']

        return {'found': True, 'album': album, 'image_url': image_url}

    def append_data_from_api(self):

        if self.api == "lastfm" and not self.api_key:
            return

        if self.album and self.artist and not self.image_data and not self.image_path:

            request_dict = self._request_album_data()

            if request_dict['found']:
                self.image_url = request_dict['image_url']

        elif self.title and self.artist and (not self.album or (not self.image_data and not self.image_path and not self.image_url)):

            request_dict = self._request_track_data()

            if request_dict['found']:

                if bool(request_dict['album']):
                    logging.info(f"self.album = request_dict['album'] = {request_dict['album']}")
                    self.album = request_dict['album']

                if bool(request_dict['image_url']):
                    logging.info(f"self.image_url = request_dict['image_url'] = {request_dict['image_url']}")
                    self.image_url = request_dict['image_url']


def get_mpd_config_path():

    if bool(os.getenv("XDG_CONFIG_HOME")):
        return "{}/mpd/mpd.conf".format(os.getenv("XDG_CONFIG_HOME"))
    elif bool(os.getenv("HOME")):
        return "{}/.config/mpd/mpd.conf".format(os.getenv("HOME"))
    elif bool(os.getlogin()):
        return "/home/{}/.config/mpd/mpd.conf".format(os.getlogin())


def get_music_directory():

    path = get_mpd_config_path()

    for line in open(path, "r"):
        if re.match(r'music_directory.*$', line):
            line_list = line.strip().split()
            if len(line_list) == 2:
                return os.path.expanduser(line_list[-1].strip("\""))


def get_arguments():

    parser = argparse.ArgumentParser(prog=PROG, usage="%(prog)s [options]", description="Send notification from current MPD track.", prefix_chars='-')
    parser.add_argument("--api", "-a", type=str, default="lastfm", help="Specify an api")
    parser.add_argument("--once", "-o", action="store_true", default=False, help="Send one notification and exit")

    return parser.parse_args()


def mpd_open_connection(address, port, password=None, timeout=None, idle_timeout=None):

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


def interrupt_signal(client=None):

    # hide output
    sys.stdout.write('\b\b\r')

    # if client connection is open then close it
    if client:
        client.close()

    # exit successfully
    sys.exit(0)


def get_notification_message(song):

    message = ""

    if song.title:
        message += f"<span size='large'><b>{song.title}</b></span>"

    if song.album and song.date:
        message += f"\n<span size='small'> on</span> <b>{song.album}</b> (<b>{song.date}</b>)"
    elif song.album:
        message += f"\n<span size='small'> on</span> <b>{song.album}</b>"

    if song.artist:
        message += f"\n<span size='small'> by</span> <b>{song.artist}</b>"

    return message


def generate_pixbuf_from_image(song):

    if DEFAULT_IMAGE_PATH and not song.image_data and not song.image_path and not song.image_url:
        song.image_path = DEFAULT_IMAGE_PATH

    if song.image_data:

        input_stream = Gio.MemoryInputStream.new_from_data(song.image_data, None)
        return Pixbuf.new_from_stream(input_stream, None)

    elif song.image_path:

        return Pixbuf.new_from_file(song.image_path)

    elif song.image_url:

        try:
            response = urllib.request.urlopen(song.image_url)
        except urllib.error.HTTPError:
            pass
        else:
            input_stream = Gio.MemoryInputStream.new_from_data(response.read(), None)
            return Pixbuf.new_from_stream(input_stream, None)


def send_notification(song):

    notify_message = get_notification_message(song)

    notify2.init(PROG)
    n = notify2.Notification(PROG, notify_message)

    if bool(NOTIFY_ID):
        n.id = NOTIFY_ID

    n.set_hint('desktop-entry', PROG)
    n.set_urgency(NOTIFY_URGENCY)
    n.set_timeout(NOTIFY_TIMEOUT)

    pixbuf = generate_pixbuf_from_image(song)

    if bool(pixbuf):
        n.set_icon_from_pixbuf(pixbuf)

    try:
        n.show()
    except dbus.exceptions.DBusException:
        print("dbus failed to send")


def main():

    mpd_music_directory = get_music_directory()

    logging.basicConfig(level=logging.INFO, format='%(levelname)-5s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    # get command line arguments
    arguments = get_arguments()

    # open mpd client connection
    client = mpd_open_connection(MPD_BIND_ADDRESS, MPD_BIND_PORT, MPD_PASSWORD, MPD_TIMEOUT, MPD_IDLE_TIMEOUT)

    # define function for interrupt signal
    signal.signal(signal.SIGINT, lambda x, y: interrupt_signal(client))

    # run once argument passed then send notification
    if arguments.once:

        # if current song and state are found send notification
        if bool(client.currentsong()) and client.status()['state'] in ("play", "pause", "stop"):

            song = SongInfo(client.currentsong(), arguments.api, LASTFM_API_KEY, mpd_music_directory)

            if song.id == client.currentsong()['id']:
                send_notification(song)

    # else begin monitoring and send notification on play
    else:

        while client.idle("player"):

            # if current song is found and state is play send notification
            if bool(client.currentsong()) and client.status()['state'] == "play":

                song = SongInfo(client.currentsong(), arguments.api, LASTFM_API_KEY, mpd_music_directory)

                if song.id == client.currentsong()['id']:
                    send_notification(song)

    # close mpd connection
    client.close()
    client.disconnect()


if __name__ == "__main__":
    main()

import asyncio
import os
import pickle
import logging
import subprocess
from dataclasses import dataclass, field
from typing import List, Callable, Optional
from yandex_music.exceptions import YandexMusicError
from yandex_music.client import Client

from player import Player


def delay_thread_safe(coroutine, loop):
    fut = asyncio.run_coroutine_threadsafe(coroutine, loop)
    return fut.result()


@dataclass
class Track:
    id: int
    name: str

    downloads: List[Callable[[str], str]]
    filename: str = None

    likes: set = field(default_factory=set)
    dislikes: set = field(default_factory=set)


def get_track(track_id: int) -> Optional[Track]:
    music_client = Client()
    download_infos = music_client.tracks_download_info(track_id, get_direct_links=True)
    download_infos = sorted(download_infos, key=lambda i: i['bitrate_in_kbps'], reverse=True)
    downloads = [info.download for info in download_infos]

    track_info = music_client.tracks(track_id)[0]
    if not track_info['available']:
        return None

    artists = ','.join(artist['name'] for artist in track_info['artists'])
    title = track_info["title"]
    name = f'{artists} - {title}'

    return Track(id=track_id, name=name, downloads=downloads)


class PlaylistManager:
    def __init__(self, loop, max_dislikes: int = 2, max_likes: int = 2, say_names: bool = False):
        self.max_dislikes = max_dislikes
        self.max_likes = max_likes
        self.say_names = say_names
        self.loop = loop

        self.player = Player()
        self.logging = logging.getLogger(__name__)

        self.playlist: List[Track] = []
        self.current_track: Optional[Track] = None

        self._skip = False
        self._playlist_file = 'playlist.pickle'

        self.load_playlist()

    async def rotate_tracks(self):
        self.logging.debug('begin rotate tracks')

        self.player.volume = 50

        while True:
            try:
                await self._preload()
                if self._skip or self.player.position == -1 or self.player.position > 0.997:
                    self._skip = False

                    if self.player.is_playing:
                        self.player.stop()

                    filename = await self.get_next_track_filename()

                    self.logging.info(f'play: {self.current_track.name}')

                    self.player.open(filename)

                    await asyncio.sleep(1.5)

                    if self.say_names:
                        await self.say(f'[[volm 0.65]] {self.current_track.name}', decrease=0.6)

                    self.save_playlist()

                await asyncio.sleep(1)
            except Exception as e:
                import traceback;
                traceback.print_exc()
                self.logging.error(e)

    async def get_next_track_filename(self) -> str:
        if self.current_track is not None:
            if os.path.isfile(self.current_track.filename):
                os.remove(self.current_track.filename)

        self.current_track = None

        filename = None
        while not filename:
            if len(self.playlist) == 0:
                self.logging.debug('waiting for a track ...')
                await asyncio.sleep(1)
                continue

            track = self.playlist.pop(0)

            filename = await self._download_track(track)

            self.current_track = track

        return filename

    async def _preload(self):
        try:
            track = self.playlist[0]
        except IndexError:
            return

        if track.filename and os.path.isfile(track.filename):
            return

        self.logging.debug(f'preload: {track.name}')

        await self._download_track(track)

    async def _download_track(self, track) -> Optional[str]:
        if track.filename is not None and os.path.isfile(track.filename):
            return track.filename

        filename = os.path.join('./temp/', track.name + '.mp3')
        for attempt, download in enumerate(track.downloads):
            try:
                self.logging.debug(f'download {attempt}: {track.name}')
                download(filename)
                self.logging.debug(f'download {attempt}: {track.name} saved to {filename}')
                break
            except YandexMusicError:
                continue
        else:
            self.logging.debug(f'skip: {track.name}')
            await self.remove_track(track.id)
            return None

        track.filename = filename

        return filename

    async def say(self, text, decrease=0.7):
        # voice = random.choice(['Milena', 'Yuri'])
        voice = 'Milena'

        volume = self.player.volume
        self.player.volume = volume * decrease

        self.logging.info(f'say: {text}')

        subprocess.run(['say', f'-v{voice}', text])

        self.player.volume = volume

    async def add_track(self, track: Track) -> int:
        self.playlist.append(track)
        position = len(self.playlist)

        self.logging.info(f'add: {track.name} at {position}')

        self.save_playlist()
        return position

    async def get_tracks(self, track_id: int) -> List[Track]:
        tracks = []
        if self.current_track and self.current_track.id == track_id:
            tracks.append(self.current_track)
        return tracks + [track for track in self.playlist if track.id == track_id]

    async def remove_track(self, track_id: int):
        if self.current_track is not None and self.current_track.id == track_id:
            self._skip = True

        self.logging.info(f'remove: {track_id}')

        self.playlist = [track for track in self.playlist if track.id != track_id]

        self.save_playlist()

    async def like(self, sender_id, track_id: int = None):
        if self.current_track:
            track_id = track_id or self.current_track.id

        if not track_id:
            self.logging.info(f'like: {sender_id} to {track_id}: Track id is null.')
            return

        tracks = await self.get_tracks(track_id)
        for track in tracks:
            track.likes.add(sender_id)
            try:
                track.dislikes.remove(sender_id)
            except KeyError:
                pass

        if tracks:
            track = tracks[0]
            try:
                position = self.playlist.index(track)
                if position > 0 and len(track.likes) >= int(self.max_likes):
                    self.playlist[position], self.playlist[position - 1] = (
                        self.playlist[position - 1], self.playlist[position]
                    )
                    track.likes = set()
            except ValueError:
                pass

        self.logging.info(f'like: {sender_id} to {track_id} up to {len(tracks)} tracks')

    async def dislike(self, sender_id, track_id: int = None):
        if self.current_track is not None:
            track_id = track_id or self.current_track.id

        if not track_id:
            self.logging.info(f'dislike: {sender_id} to {track_id}: Track id is null.')
            return

        tracks = await self.get_tracks(track_id)
        for track in tracks:
            track.dislikes.add(sender_id)
            try:
                track.likes.remove(sender_id)
            except KeyError:
                pass

            if len(track.dislikes) >= int(self.max_dislikes):
                await self.remove_track(track_id)

        self.logging.info(f'dislike: {sender_id} to {track_id} up to {len(tracks)} tracks')

    def save_playlist(self):
        self.logging.debug(f'save playlist')

        with open(self._playlist_file, 'wb') as f:
            pickle.dump(self.playlist, f)

    def load_playlist(self):
        if not os.path.exists(self._playlist_file):
            return

        self.logging.debug(f'load playlist')

        with open(self._playlist_file, 'rb') as f:
            playlist = pickle.load(f)

        for track in playlist:
            track.filename = None

        self.playlist = playlist

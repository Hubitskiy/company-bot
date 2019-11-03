import vlc
import os


class Player:
    def __init__(self):
        self.player = vlc.MediaPlayer()

    def open(self, filename):
        if not os.path.isfile(filename):
            print('is not a file', filename)
            return

        media = self.player.get_instance().media_new(filename)

        self.player.set_media(media)

        self.play()

    @property
    def volume(self):
        return self.player.audio_get_volume()

    @volume.setter
    def volume(self, value: int = None):
        if value is None:
            value = 100 if self.volume == 0 else 0

        value = max(0, min(100, int(value)))
        self.player.audio_set_volume(value)

    @property
    def is_playing(self) -> bool:
        return self.player.is_playing()

    @property
    def position(self) -> int:
        return self.player.get_position()

    def stop(self):
        self.player.stop()

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

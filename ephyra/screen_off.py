"""Pause a video when the phone's screen turns off, unless the owner keeps
it playing (Preferences → Playback; docs/player-controls.md)."""
import logging

log = logging.getLogger("ephyra.screen_off")


class ScreenOffPause:
    """Watches the application's `screensaver-active` (GTK tracks it only
    with `register-session`: from org.gnome.ScreenSaver, in the Flatpak
    from the Inhibit portal's monitor) and calls `pause()` when it turns
    on and `keep_playing()` answers False."""

    def __init__(self, app, keep_playing, pause):
        self._app = app
        self._keep_playing = keep_playing
        self._pause = pause
        self._handler = app.connect("notify::screensaver-active", self._changed)

    def _changed(self, app, pspec):
        active = app.props.screensaver_active
        log.debug("screen saver active: %s", active)
        if active and not self._keep_playing():
            self._pause()

    def stop(self):
        if self._handler:
            self._app.disconnect(self._handler)
            self._handler = 0

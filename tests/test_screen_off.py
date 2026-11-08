"""The player pauses a video when the screen turns off, unless the
preference keeps it playing (ephyra/screen_off.py)."""
from gi.repository import GObject

from ephyra.screen_off import ScreenOffPause


class FakeApp(GObject.Object):
    """Stands in for Gtk.Application, whose `screensaver-active` only GTK
    can set."""
    screensaver_active = GObject.Property(type=bool, default=False)


def test_pauses_when_the_screen_turns_off_unless_kept_playing():
    app = FakeApp()
    keep = [False]
    paused = []
    watch = ScreenOffPause(app, lambda: keep[0], lambda: paused.append(1))
    app.props.screensaver_active = True
    assert paused == [1]
    app.props.screensaver_active = False     # on again: no play, no pause
    assert paused == [1]
    keep[0] = True
    app.props.screensaver_active = True
    assert paused == [1]
    app.props.screensaver_active = False
    keep[0] = False
    watch.stop()
    app.props.screensaver_active = True
    assert paused == [1]

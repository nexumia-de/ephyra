"""What the player offers near the end and in marked segments: the Skip
Intro / Skip Credits button and the up-next card with its countdown, in
the bottom right corner over the video (docs/player-controls.md)."""
import logging

from gi.repository import Gtk

from ephyra import segments
from ephyra.upnext import UpNextCard

log = logging.getLogger("ephyra.skipper")

# Above the controls while they show, near the edge otherwise; the same
# heights as the subtitles.
MARGIN = {False: 24, True: 104}
WIDE = 480    # px from which the up-next card shows the episode's still


class Skipper:
    """`seek(seconds)` jumps inside the playing item, `play_next()` starts
    `next_episode`, `width()` is the player's width. The player calls
    update() on every position change and tick() once a second while it
    plays."""

    def __init__(self, images_, seek, play_next, width):
        self._seek = seek
        self._play_next = play_next
        self._width = width
        self.segments = []
        self.next_episode = None
        self.cancelled = False    # Cancel on the card: no next episode this time
        self.auto_next = True     # off: no card, the player closes at the end
        self.segment = None       # the one the button would skip

        self.button = Gtk.Button(label="")
        self.button.add_css_class("pill")
        self.button.add_css_class("suggested-action")
        self.button.connect("clicked", lambda *_: self.skip())
        self.skip_revealer = Gtk.Revealer(
            child=self.button, reveal_child=False, can_target=False,
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            halign=Gtk.Align.END, valign=Gtk.Align.END,
            margin_start=12, margin_end=12)
        self.card = UpNextCard(images_)
        self.card.connect("play", lambda *_: self._play_next())
        self.card.connect("cancel", lambda *_: self.cancel())
        self.set_controls_visible(False)

    @property
    def overlays(self):
        return (self.skip_revealer, self.card)

    # --- what the server knows -----------------------------------------

    def load(self, call, jellyfin, item, done=None):
        """Fetch the segments and, for an episode, the next one, in a
        worker. Missing data counts as none: the player plays on."""
        item_id = item["Id"]

        def fetch():
            found = segments.parse(_quiet(jellyfin.media_segments, item_id))
            following = None
            if item.get("Type") == "Episode":
                following = _quiet(jellyfin.next_episode, item)
            return found, following

        def arrived(result, error):
            if error is not None or result is None:
                log.info("segments and next episode: %s", error)
                result = ([], None)
            self.segments, self.next_episode = result
            log.debug("segments %s, next episode %s", self.segments,
                      (self.next_episode or {}).get("Id"))
            if done:
                done()
        call(fetch, arrived)

    # --- state ---------------------------------------------------------

    def up_next_due(self, position, duration):
        if self.next_episode is None or not self.auto_next:
            return False
        start = segments.up_next_from(self.segments, duration)
        return start is not None and position >= start

    def update(self, position, duration):
        """Show the button or the card that fits `position`."""
        due = self.up_next_due(position, duration)
        # The still only where it fits beside the buttons (not at 360 px).
        self.card.art.set_visible(self._width() >= WIDE)
        if due and not self.cancelled:
            if not self.card.shown:
                self.card.offer(self.next_episode)
        else:
            if not due:
                # Seeked back before the credits: offer it again later.
                self.cancelled = False
            self.card.withdraw()
        segment = None if self.card.shown else segments.at(self.segments, position)
        self.segment = segment
        if segment is not None:
            self.button.set_label(segments.SKIP_LABELS[segment.kind])
            self.button.update_property([Gtk.AccessibleProperty.LABEL],
                                        [segments.SKIP_LABELS[segment.kind]])
        self.skip_revealer.set_can_target(segment is not None)
        self.skip_revealer.set_reveal_child(segment is not None)

    def tick(self):
        """One second of playing: the card counts down."""
        self.card.count_down()

    def wants_next(self):
        """At the end of the item: go on to the next episode?"""
        return (self.next_episode is not None and self.auto_next
                and not self.cancelled)

    def skip(self):
        if self.segment is not None:
            self._seek(self.segment.end)

    def cancel(self):
        self.cancelled = True
        self.card.withdraw()

    def set_controls_visible(self, visible):
        for widget in self.overlays:
            widget.set_margin_bottom(MARGIN[visible])

    def hide(self):
        self.card.withdraw()
        self.skip_revealer.set_can_target(False)
        self.skip_revealer.set_reveal_child(False)


def _quiet(fn, *args):
    """An extra the player can do without: errors are logged, not raised."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - network, server, anything
        log.info("%s: %s", fn.__name__, e)
        return None

"""The player: GStreamer plays the local proxy URL (docs/playback.md);
touch controls over the video (docs/player-controls.md), progress
reported to the server."""
import logging
from datetime import datetime

from gi.repository import Adw, Gdk, GLib, Gtk

from phosh_toolkit import route
from phosh_toolkit.media import Media

from ephyra import images, playback, text, widgets
from ephyra.rotator import Rotator
from ephyra.screen_off import ScreenOffPause
from ephyra.sessions import Sessions
from ephyra.skipper import Skipper
from ephyra.subtitle_view import SubtitleView
from ephyra.taps import SeekBubbles, tap_action, tap_zone  # noqa: F401 (tests)
from ephyra.track_sheet import TrackSheet

log = logging.getLogger("ephyra.player")

REPORT_EVERY = 10      # seconds between progress reports
HIDE_AFTER = 3         # seconds until the controls hide while playing
SKIP_BACK, SKIP_FORWARD = 10, 30


class PlayerPage(Adw.NavigationPage):
    def __init__(self, window, item, start=0, force_transcode=False,
                 rotated=False, rotation_fullscreen=False):
        """`rotated`, `rotation_fullscreen`: carried over from the
        episode before, so the next one plays turned as it was."""
        super().__init__(title=item.get("Name", ""), tag="player")
        self.window = window
        self.conn = window.connection
        self.item = item
        self.start = start
        self.force_transcode = force_transcode
        self.stream = None
        self.media = None
        self.started = False
        self.stopped = False
        self._seeking = False
        self._timers = []
        self._hide_timeout = 0
        self._single_tap = 0
        self._rotation_fullscreen = rotation_fullscreen
        self._keep_window = False   # handing over to the next episode
        self._inhibit = 0
        self._media_handlers = []
        # Track choice: None lets the server pick from the user's
        # language settings, subtitle -1 is off.
        self.audio_index = None
        self.subtitle_index = None
        self.is_video = item.get("MediaType") != "Audio"
        self.proxy = window.proxy
        # The server side of the streams: at most one per player, stopped
        # when replaced or left (docs/playback.md).
        self.sessions = Sessions(self.conn.jellyfin, self.conn.call)

        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,
                                   hexpand=True, vexpand=True)
        self.picture.add_css_class("ephyra-video")
        self.stack = Gtk.Stack()
        self.stack.add_named(self._loading(), "loading")
        overlay = Gtk.Overlay(child=self.picture)
        overlay.add_overlay(self._waiting())
        # Subtitles are drawn here, not by GStreamer (docs/playback.md).
        self.subtitle_view = SubtitleView(
            self.conn.call, self.conn.jellyfin,
            lambda: self.media.position_now() if self.media else None,
            window.toast)
        self.subtitle_label = self.subtitle_view.label
        overlay.add_overlay(self.subtitle_label)
        self.seek_bubbles = SeekBubbles()
        self.bubbles = self.seek_bubbles.bubbles
        for bubble in self.seek_bubbles.overlays:
            overlay.add_overlay(bubble)
        self.transport = self._transport()
        if self.is_video:
            # Phone players put the big buttons in the middle of the video.
            self.center = Gtk.Revealer(child=self.transport, reveal_child=True,
                                       transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                       halign=Gtk.Align.CENTER,
                                       valign=Gtk.Align.CENTER)
            overlay.add_overlay(self.center)
        else:
            self.center = None
        # Skip Intro / Credits and the next episode, bottom right.
        self.skipper = Skipper(window.images, self.seek_to, self.play_next,
                               lambda: self.overlay.get_width())
        self.skipper.auto_next = self.conn.account.auto_next
        for widget in self.skipper.overlays:
            overlay.add_overlay(widget)
        self.sheet = TrackSheet(self.close_tracks)
        overlay.add_overlay(self.sheet)
        self.overlay = overlay
        self.stack.add_named(overlay, "video")

        self.view = Adw.ToolbarView(content=self.stack,
                                    extend_content_to_top_edge=True,
                                    extend_content_to_bottom_edge=True,
                                    top_bar_style=Adw.ToolbarStyle.FLAT,
                                    bottom_bar_style=Adw.ToolbarStyle.FLAT)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=item.get("Name", ""),
            subtitle=text.title(item) if item.get("Type") == "Episode" else ""))
        header.add_css_class("osd")
        self.fullscreen_button = Gtk.Button(icon_name="view-fullscreen-symbolic",
                                            tooltip_text="Fullscreen")
        self.fullscreen_button.update_property([Gtk.AccessibleProperty.LABEL],
                                               ["Fullscreen"])
        self.fullscreen_button.connect("clicked", lambda *_: self.toggle_fullscreen())
        header.pack_end(self.fullscreen_button)
        self.next_button = Gtk.Button(icon_name="media-skip-forward-symbolic",
                                      tooltip_text="Next Episode", visible=False)
        self.next_button.update_property([Gtk.AccessibleProperty.LABEL],
                                         ["Next Episode"])
        self.next_button.connect("clicked", lambda *_: self.play_next())
        header.pack_end(self.next_button)
        self.rotate_button = Gtk.Button(icon_name="object-rotate-left-symbolic",
                                        visible=self.is_video)
        self.rotate_button.connect("clicked", lambda *_: self.toggle_rotation())
        header.pack_end(self.rotate_button)
        self.tracks_button = Gtk.Button(icon_name="media-view-subtitles-symbolic",
                                        tooltip_text="Audio and Subtitles",
                                        visible=False)
        self.tracks_button.update_property([Gtk.AccessibleProperty.LABEL],
                                           ["Audio and Subtitles"])
        self.tracks_button.connect("clicked", lambda *_: self.open_tracks())
        header.pack_end(self.tracks_button)
        self.view.add_top_bar(header)
        self.view.add_bottom_bar(self._controls())
        self.rotator = Rotator(self.view)
        self.rotator.props.rotated = rotated
        self.rotator.connect("notify::portrait", self._on_portrait)
        self._update_rotate_button()
        self.set_child(self.rotator)

        # On the overlay, not the picture: taps on the buttons above the
        # video stay with the buttons.
        click = Gtk.GestureClick()
        click.connect("released", self._on_tap)
        overlay.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._show_controls())
        self.view.add_controller(motion)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("hidden", self._on_hidden)
        self.screen_off = ScreenOffPause(
            window.get_application(),
            lambda: not self.is_video or self.conn.account.play_screen_off,
            self._pause_for_screen_off)
        self._fullscreen_handler = window.connect("notify::fullscreened",
                                                  self._on_fullscreened)
        self.prepare()

    # --- widgets -----------------------------------------------------

    def _loading(self):
        page = widgets.loading_page()
        page.set_title(self.item.get("Name", ""))
        return page

    def _waiting(self):
        """Spinner while GStreamer starts the stream; for a converted one
        also why it takes long, so nobody taps again (each new request
        would be one more conversion on the server)."""
        self.converting = Gtk.Label(label="Converting on the server\u2026",
                                    wrap=True, justify=Gtk.Justification.CENTER)
        self.converting.add_css_class("heading")
        self.waiting = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                               halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                               can_target=False, visible=False)
        self.waiting.add_css_class("osd")
        self.waiting.add_css_class("ephyra-waiting")
        self.waiting.append(widgets.spinner())
        self.waiting.append(self.converting)
        return self.waiting

    def _controls(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                      margin_start=6, margin_end=6, margin_bottom=6)
        bar.add_css_class("osd")
        bar.add_css_class("toolbar")
        self.scale = Gtk.Scale(adjustment=Gtk.Adjustment(upper=1,
                                                         step_increment=10),
                               draw_value=False, hexpand=True)
        self.scale.update_property([Gtk.AccessibleProperty.LABEL], ["Position"])
        self.scale.connect("change-value", self._on_scale)
        bar.append(self.scale)
        row = Gtk.CenterBox()
        self.position_label = Gtk.Label(label="0:00")
        self.position_label.add_css_class("numeric")
        self.duration_label = Gtk.Label(label="")
        self.duration_label.add_css_class("numeric")
        # "Ends at 22:14", next to the duration, as Jellyfin's player has it.
        self.ends_label = Gtk.Label(label="", visible=False)
        self.ends_label.add_css_class("numeric")
        self.ends_label.add_css_class("dimmed")
        self.ends_label.add_css_class("dim-label")
        end = Gtk.Box(spacing=12)
        end.append(self.ends_label)
        end.append(self.duration_label)
        row.set_start_widget(self.position_label)
        if not self.is_video:
            row.set_center_widget(self.transport)
        else:
            # The same setting as in the preferences, at hand while
            # watching; in the bar, as the header is full at 360 px.
            self.auto_next_button = Gtk.ToggleButton(
                icon_name="media-playlist-consecutive-symbolic",
                tooltip_text="Play Next Episode Automatically",
                active=self.conn.account.auto_next, visible=False)
            self.auto_next_button.add_css_class("flat")
            self.auto_next_button.update_property(
                [Gtk.AccessibleProperty.LABEL],
                ["Play Next Episode Automatically"])
            self.auto_next_button.connect("toggled", self._on_auto_next)
            row.set_center_widget(self.auto_next_button)
        row.set_end_widget(end)
        bar.append(row)
        return bar

    def _transport(self):
        """Back, play/pause, forward: large round buttons over the video,
        small flat ones in the bar for audio."""
        buttons = Gtk.Box(spacing=24 if self.is_video else 6)
        self.play_button = self._button("media-playback-start-symbolic", "Play",
                                        self.toggle_play)
        self.play_button.add_css_class("circular")
        buttons.append(self._button("media-seek-backward-symbolic",
                                    f"Back {SKIP_BACK} Seconds",
                                    lambda: self.skip(-SKIP_BACK)))
        buttons.append(self.play_button)
        buttons.append(self._button("media-seek-forward-symbolic",
                                    f"Forward {SKIP_FORWARD} Seconds",
                                    lambda: self.skip(SKIP_FORWARD)))
        if self.is_video:
            buttons.add_css_class("ephyra-transport")
            for button in (buttons.get_first_child(), buttons.get_last_child()):
                button.remove_css_class("flat")
                button.add_css_class("circular")
                button.add_css_class("osd")
                button.set_valign(Gtk.Align.CENTER)
            self.play_button.remove_css_class("flat")
            self.play_button.add_css_class("osd")
            self.play_button.add_css_class("ephyra-play")
        return buttons

    def _tracks(self):
        if not self.stream or not self.is_video:
            return [], []
        return (playback.audio_tracks(self.stream.source),
                playback.subtitle_tracks(self.stream.source))

    def _update_tracks_button(self):
        audio, subtitles = self._tracks()
        self.tracks_button.set_visible(len(audio) > 1 or bool(subtitles))

    def open_tracks(self):
        audio, subtitles = self._tracks()
        groups = []
        if len(audio) > 1:
            groups.append(("Audio", audio, self.stream.audio_index,
                           self.choose_audio))
        if subtitles:
            current = self.stream.subtitle_index
            if current is None or current < 0:
                current = -1
            groups.append(("Subtitles", [(-1, "Off")] + subtitles, current,
                           self.choose_subtitle))
        self._hide_controls()
        # Side by side when there is room (landscape), stacked otherwise.
        self.sheet.open(groups, self.overlay.get_width() >= 600)

    def close_tracks(self):
        self.sheet.close()
        self._show_controls()

    def choose_audio(self, index):
        stream = self.stream
        if stream is None or index == stream.audio_index:
            return
        self.audio_index = index
        self.close_tracks()
        if stream.method != playback.TRANSCODE:
            # The file has every track: switch inside GStreamer.
            stream.audio_index = index
            if self.media:
                self.media.select_audio(stream.audio_position)
            self._report("Progress")
        else:
            # A converted stream carries one audio track: ask again.
            self._reload()

    def choose_subtitle(self, index):
        stream = self.stream
        if stream is None:
            return
        current = stream.subtitle_index if stream.subtitle_index is not None else -1
        if index == current:
            return
        self.subtitle_index = index
        burned = playback.subtitle_method(stream.source, current) == "Encode"
        wanted = playback.subtitle_method(stream.source, index)
        log.debug("subtitle %s -> %s (%s, burned now %s)", current, index,
                  wanted, burned)
        # The sheet covers the bottom of the video, where the subtitle
        # shows: close it on a choice.
        self.close_tracks()
        if burned or wanted == "Encode":
            # Burned into the picture by the server, or no longer.
            self._reload()
        else:
            stream.subtitle_index = index
            self.subtitle_view.load(self.stream)
            self._report("Progress")

    def _button(self, icon, label, callback):
        button = Gtk.Button(icon_name=icon, tooltip_text=label)
        button.add_css_class("flat")
        button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        button.connect("clicked", lambda *_: callback())
        return button

    # --- start -------------------------------------------------------

    def bitrate(self):
        account = self.conn.account
        return (account.quality_home if self.conn.state == route.LOCAL
                else account.quality_away)

    def prepare(self, replace=None):
        """Ask the server for a stream. `replace`: what _end_stream()
        returned for the stream being left, stopped on the server first."""
        # The track indexes count only with their media source.
        source = replace[0].media_source_id if replace else None
        self.sessions.open(self._on_stream, self.item, self.bitrate(),
                           audio=self.audio_index, subtitle=self.subtitle_index,
                           force=self.force_transcode, replace=replace,
                           source=source)

    def _on_stream(self, stream, error):
        if error is not None:
            self._fail(str(error), getattr(error, "details", ""))
            return
        self.stream = stream
        self.audio_index = stream.audio_index
        self.subtitle_index = stream.subtitle_index
        log.info("%s %s", stream.method, stream.path)
        for track in stream.source.get("MediaStreams") or []:
            if track.get("Type") == "Subtitle":
                # Never the DeliveryUrl itself: it carries the token.
                log.debug("subtitle track %s: %s, external file %s, text %s, "
                          "delivery %s, url %s, url elsewhere %s",
                          track.get("Index"), track.get("Codec"),
                          track.get("IsExternal"), track.get("IsTextSubtitleStream"),
                          track.get("DeliveryMethod"), bool(track.get("DeliveryUrl")),
                          track.get("IsExternalUrl"))
        log.debug("chosen: audio %s, subtitle %s", stream.audio_index,
                  stream.subtitle_index)
        if self.item.get("MediaType") == "Audio" and not self._timers:
            self._show_cover()
        self._start_media()
        self.subtitle_view.load(self.stream)
        self._update_tracks_button()
        if not self._timers:
            self._timers.append(GLib.timeout_add_seconds(REPORT_EVERY,
                                                         self._report_progress))
            self._timers.append(GLib.timeout_add_seconds(1, self._tick))
            if self.is_video:
                self.skipper.load(self.conn.call, self.conn.jellyfin, self.item,
                                  self._on_extras)
        if not self._inhibit:
            self._inhibit = self.window.get_application().inhibit(
                self.window, Gtk.ApplicationInhibitFlags.IDLE |
                Gtk.ApplicationInhibitFlags.SUSPEND, "Playing media")
        self._show_controls()

    def _start_media(self):
        stream = self.stream
        url = self.proxy.url(stream.path)
        # Not Gtk.MediaFile: GTK 4.20 reads http:// through GIO, which
        # the Flatpak can't (phosh_toolkit.media).
        self.media = Media(url, video=self.item.get("MediaType") != "Audio",
                           audio_position=stream.audio_position)
        self._media_handlers = [
            self.media.connect(f"notify::{prop}", self._on_media)
            for prop in ("timestamp", "duration", "playing", "error", "prepared",
                         "ended")]
        if self.item.get("MediaType") != "Audio":
            self.picture.set_paintable(self.media.paintable)
        self.stack.set_visible_child_name("video")
        self.converting.set_visible(stream.method == playback.TRANSCODE)
        self.waiting.set_visible(True)
        self.media.play()

    def _reload(self):
        """Ask the server again (other audio in a converted stream, burned
        subtitles on or off) and go on from the current position."""
        if self.started:
            self.start = self.position()
        replace = self._end_stream()
        self.stack.set_visible_child_name("loading")
        self.prepare(replace)

    def _show_cover(self):
        art = widgets.Artwork(1)
        art.show(self.window.images, images.primary(self.item), 360,
                 widgets.icon_for(self.item))
        art.set_halign(Gtk.Align.CENTER)
        art.set_valign(Gtk.Align.CENTER)
        art.set_size_request(240, -1)
        overlay = self.stack.get_child_by_name("video")
        overlay.add_overlay(art)

    def _fail(self, message, details=""):
        """Error page; `details` (file and server answer, see
        playback.describe) is selectable so it can be copied into an
        issue."""
        page = Adw.StatusPage(icon_name="dialog-error-symbolic",
                              title="Can\u2019t Play This", description=message)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        if not self.force_transcode:
            button = Gtk.Button(label="Convert on the Server",
                                halign=Gtk.Align.CENTER)
            button.add_css_class("pill")
            button.add_css_class("suggested-action")
            button.connect("clicked", lambda *_: self._retry_transcoded())
            box.append(button)
        if details:
            label = Gtk.Label(label=details, wrap=True, selectable=True,
                              justify=Gtk.Justification.CENTER)
            label.add_css_class("caption")
            label.add_css_class("dimmed")
            label.add_css_class("dim-label")
            box.append(label)
            log.warning("playback details: %s", details)
        page.set_child(box)
        old = self.stack.get_child_by_name("error")
        if old:
            self.stack.remove(old)
        self.stack.add_named(page, "error")
        self.stack.set_visible_child_name("error")
        self.view.set_reveal_top_bars(True)
        self.view.set_reveal_bottom_bars(False)
        if self.center is not None:
            self.center.set_reveal_child(False)
        self.skipper.hide()

    def _retry_transcoded(self):
        replace = self._end_stream()
        self.force_transcode = True
        self.stack.set_visible_child_name("loading")
        self.view.set_reveal_bottom_bars(True)
        self.prepare(replace)

    # --- media state ---------------------------------------------------

    def position(self):
        return self.media.get_timestamp() / 1_000_000 if self.media else 0

    def duration(self):
        if self.media and self.media.get_duration() > 0:
            return self.media.get_duration() / 1_000_000
        return self.stream.duration if self.stream else 0

    def _on_media(self, media, pspec):
        name = pspec.name
        if name == "error" and media.get_error():
            message = media.get_error()
            log.warning("playback: %s", message)
            # GStreamer's message is long and technical: it goes into the
            # copyable details line, the page says what to do.
            details = f"{self.stream.method} · {self.stream.details}" \
                if self.stream else ""
            details = f"{details} · GStreamer: {gst_reason(message)}"
            # Nothing plays any more: end the server's side now, not only
            # when the page is left.
            self._stop_stream()
            self._fail("This phone can\u2019t play the file as it is. The "
                       "server can convert it to a format the phone plays.",
                       details)
            return
        if name == "prepared" and media.is_prepared():
            self.waiting.set_visible(False)
            if self.start > 1:
                media.seek(int(self.start * 1_000_000))
            if not self.started:
                self._report("")
                self.started = True
        if name in ("timestamp", "duration", "prepared"):
            duration = self.duration()
            if duration:
                self.scale.get_adjustment().set_upper(duration)
                self.duration_label.set_label(text.clock(duration))
            if not self._seeking:
                self.scale.set_value(self.position())
            self.position_label.set_label(text.clock(self.position()))
            self._update_ends()
            if self.is_video and self.started:
                self.skipper.update(self.position(), duration)
        if name in ("playing", "prepared"):
            playing = media.get_playing()
            self.play_button.set_icon_name("media-playback-pause-symbolic"
                                           if playing else
                                           "media-playback-start-symbolic")
            label = "Pause" if playing else "Play"
            self.play_button.set_tooltip_text(label)
            self.play_button.update_property([Gtk.AccessibleProperty.LABEL], [label])
            if self.started:
                self._report("Progress")
            self._show_controls()
        if name == "ended" and media.get_ended():
            if self.skipper.wants_next():
                self.play_next()
            else:
                self.window.nav.pop()

    def _update_ends(self):
        duration = self.duration()
        ends = text.ends_after(datetime.now(), duration - self.position()) \
            if duration else ""
        self.ends_label.set_label(ends)
        self.ends_label.set_visible(bool(ends))

    def _tick(self):
        """Once a second: the end time moves on while paused, the up-next
        card counts down while playing."""
        if self.stopped:
            return GLib.SOURCE_REMOVE
        if self.started and self.media is not None:
            self._update_ends()
            if self.media.get_playing():
                self.skipper.tick()
        return GLib.SOURCE_CONTINUE

    def _on_extras(self):
        """Segments and the next episode arrived."""
        if self.stopped:
            return
        has_next = self.skipper.next_episode is not None
        self.next_button.set_visible(has_next)
        if self.is_video:
            self.auto_next_button.set_visible(has_next)
        if self.started:
            self.skipper.update(self.position(), self.duration())

    # --- next episode ----------------------------------------------------

    def play_next(self):
        """Replace this player by one for the next episode, turned and
        fullscreen as this one."""
        episode = self.skipper.next_episode
        if episode is None or self.stopped:
            return
        # Turning is for a portrait window only (the button shows only
        # then); a player made turned in a landscape one kept re-laying
        # itself out and starved the main loop (tests/test_ui.py).
        rotated = self.rotator.props.rotated and self.rotator.props.portrait
        rotation_fullscreen = self._rotation_fullscreen and rotated
        self._keep_window = True
        self._on_hidden()
        self.window.play_instead(self, episode, rotated=rotated,
                                 rotation_fullscreen=rotation_fullscreen)

    def _on_auto_next(self, button):
        on = button.get_active()
        account = self.conn.account
        if on != account.auto_next:
            account.auto_next = on
            self.conn.save()
            self.window.toast("Autoplay on" if on else "Autoplay off")
        self.skipper.auto_next = on
        if self.started:
            self.skipper.update(self.position(), self.duration())
        self._show_controls()

    def _pause_for_screen_off(self):
        if self.media and self.media.get_playing():
            log.info("screen off: pausing")
            self.media.set_playing(False)

    # --- controls ------------------------------------------------------

    def toggle_play(self):
        if self.media:
            self.media.set_playing(not self.media.get_playing())

    def seek_to(self, seconds):
        if self.media and self.media.is_seekable():
            target = min(max(0, seconds), self.duration() or 1e9)
            self.media.seek(int(target * 1_000_000))
        self._show_controls()

    def skip(self, seconds, show=True):
        if self.media and self.media.is_seekable():
            target = min(max(0, self.position() + seconds), self.duration() or 1e9)
            self.media.seek(int(target * 1_000_000))
        if show:
            self._show_controls()

    def _on_scale(self, scale, scroll, value):
        if self.media and self.media.is_seekable():
            self.media.seek(int(max(0, value) * 1_000_000))
        self._show_controls()
        return False

    def toggle_fullscreen(self):
        if self.window.is_fullscreen():
            self.window.unfullscreen()
        else:
            self.window.fullscreen()

    def _on_fullscreened(self, *_):
        full = self.window.is_fullscreen()
        icon = "view-restore-symbolic" if full else "view-fullscreen-symbolic"
        label = "Leave Fullscreen" if full else "Fullscreen"
        self.fullscreen_button.set_icon_name(icon)
        self.fullscreen_button.set_tooltip_text(label)
        self.fullscreen_button.update_property([Gtk.AccessibleProperty.LABEL],
                                               [label])

    def toggle_rotation(self):
        """Turn the player sideways in a portrait window, and back. Turning
        also goes fullscreen, like a phone app switching to landscape."""
        rotated = not self.rotator.props.rotated
        self.rotator.props.rotated = rotated
        if rotated and not self.window.is_fullscreen():
            self._rotation_fullscreen = True
            self.window.fullscreen()
        elif not rotated and self._rotation_fullscreen:
            self._rotation_fullscreen = False
            if self.window.is_fullscreen():
                self.window.unfullscreen()
        self._update_rotate_button()
        self._show_controls()

    def _on_portrait(self, *_):
        # The display itself turned to landscape (auto-rotate): undo ours.
        if not self.rotator.props.portrait and self.rotator.props.rotated:
            self.toggle_rotation()
        self._update_rotate_button()

    def _update_rotate_button(self):
        rotated = self.rotator.props.rotated
        label = "Rotate Back" if rotated else "Rotate to Landscape"
        self.rotate_button.set_icon_name("object-rotate-right-symbolic" if rotated
                                         else "object-rotate-left-symbolic")
        self.rotate_button.set_tooltip_text(label)
        self.rotate_button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        self.rotate_button.set_visible(self.is_video and
                                       (rotated or self.rotator.props.portrait))

    def _on_tap(self, gesture, n, x, y):
        if self.sheet.is_open:
            # A tap beside the open track sheet closes it.
            if not self.sheet.holds(self.overlay.pick(x, y, Gtk.PickFlags.DEFAULT)):
                self.close_tracks()
            return
        device = gesture.get_current_event_device()
        touch = (device is not None and
                 device.get_source() == Gdk.InputSource.TOUCHSCREEN)
        self.tap(n, tap_zone(x, self.overlay.get_width()), touch)

    def tap(self, n, zone, touch):
        """A tap or click on the video, `n` counting quick repeats."""
        if self._single_tap:
            GLib.source_remove(self._single_tap)
            self._single_tap = 0
        action = tap_action(n, zone, touch)
        if action == "wait":
            # Might become a double tap; act once the double-tap time passed.
            delay = Gtk.Settings.get_default().props.gtk_double_click_time
            self._single_tap = GLib.timeout_add(delay, self._on_single_tap, touch)
        elif action in ("back", "forward"):
            self._double_tap_seek(action)
        elif action == "fullscreen":
            self.toggle_fullscreen()
        elif action == "controls":
            self._toggle_controls()

    def _on_single_tap(self, touch):
        self._single_tap = 0
        if touch:
            self._toggle_controls()
        else:
            self.toggle_play()
            self._show_controls()
        return GLib.SOURCE_REMOVE

    def _toggle_controls(self):
        if self.view.get_reveal_bottom_bars():
            self._hide_controls()
        else:
            self._show_controls()

    def _double_tap_seek(self, side):
        seconds = SKIP_BACK if side == "back" else SKIP_FORWARD
        if not (self.media and self.media.is_seekable()):
            return
        self.skip(-seconds if side == "back" else seconds, show=False)
        # The bubble takes the place of the controls, as in phone players.
        self._hide_controls()
        self.seek_bubbles.show(side, seconds)

    def _show_controls(self):
        if self.sheet.is_open:
            # The bars are drawn over the video, so they would cover the
            # open track sheet: they stay hidden until it closes, as in
            # phone players (docs/player-controls.md).
            return
        visible = self.stack.get_visible_child_name() != "error"
        self.view.set_reveal_top_bars(True)
        self.view.set_reveal_bottom_bars(visible)
        if self.center is not None:
            # Nothing to play or skip yet while the stream starts; the
            # buttons would also cover the waiting message.
            self.center.set_reveal_child(visible and not self.waiting.get_visible())
        self.subtitle_view.set_controls_visible(visible)
        self.skipper.set_controls_visible(visible)
        self.set_cursor(None)
        if self._hide_timeout:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add_seconds(HIDE_AFTER, self._autohide)

    def _autohide(self):
        self._hide_timeout = 0
        if (self.media and self.media.get_playing()
                and self.item.get("MediaType") == "Video"):
            self._hide_controls()
        return GLib.SOURCE_REMOVE

    def _hide_controls(self):
        self.view.set_reveal_top_bars(False)
        self.view.set_reveal_bottom_bars(False)
        if self.center is not None:
            self.center.set_reveal_child(False)
        self.subtitle_view.set_controls_visible(False)
        self.skipper.set_controls_visible(False)
        self.set_cursor(Gdk.Cursor.new_from_name("none"))

    def _on_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_space:
            self.toggle_play()
        elif keyval == Gdk.KEY_Left:
            self.skip(-SKIP_BACK)
        elif keyval == Gdk.KEY_Right:
            self.skip(SKIP_FORWARD)
        elif keyval in (Gdk.KEY_f, Gdk.KEY_F11):
            self.toggle_fullscreen()
        elif keyval == Gdk.KEY_Escape and self.sheet.is_open:
            self.close_tracks()
        elif keyval == Gdk.KEY_Escape and self.window.is_fullscreen():
            self.toggle_fullscreen()
        else:
            return False
        return True

    # --- reporting -----------------------------------------------------

    def _report(self, event):
        if not self.stream:
            return
        payload = self.stream.report(self.position(),
                                     paused=not (self.media and self.media.get_playing()),
                                     event=event)
        self.conn.call(self.conn.jellyfin.report, _ignore, event, payload)

    def _report_progress(self):
        if self.started and not self.stopped:
            self._report("Progress")
        return GLib.SOURCE_CONTINUE

    def _stop_media(self):
        """Stop GStreamer; the server's side is _end_stream's job."""
        self.waiting.set_visible(False)
        if self.media:
            for handler in self._media_handlers:
                self.media.disconnect(handler)
            self._media_handlers = []
            self.media.stop()
            self.media = None
        self.picture.set_paintable(None)

    def _end_stream(self):
        """Leave the current stream: stop GStreamer and return what the
        server must stop, (stream, position, failed), or None. Also before
        `prepared`: a converted stream's ffmpeg runs on the server from
        the first segment request, and an HLS request given up while
        ffmpeg starts never lets the server's own kill timer start
        (docs/playback.md)."""
        stream, started = self.stream, self.started
        position = self.position() if started else self.start
        self._stop_media()
        self.stream = None
        self.started = False
        self.tracks_button.set_visible(False)
        return (stream, position, not started) if stream else None

    def _stop_stream(self):
        replace = self._end_stream()
        if replace is not None:
            self.sessions.stop(*replace)

    def _on_hidden(self, *_):
        if self.stopped:
            return
        self.stopped = True
        for timer in self._timers:
            GLib.source_remove(timer)
        for source in (self._hide_timeout, self._single_tap):
            if source:
                GLib.source_remove(source)
        self._hide_timeout = self._single_tap = 0
        self.seek_bubbles.stop()
        self.subtitle_view.stop()
        self.screen_off.stop()
        if self._inhibit:
            self.window.get_application().uninhibit(self._inhibit)
        self.window.disconnect(self._fullscreen_handler)
        if self.window.is_fullscreen() and not self._keep_window:
            self.window.unfullscreen()
        # Answers still on the way are stopped when they arrive.
        self.sessions.close()
        self._stop_stream()
        self.window.after_playback(self.item)


def gst_reason(message):
    """The readable part of a GStreamer error ("Could not determine type
    of stream."), without element paths and source locations."""
    text = message.split("\n")[0]
    if text.startswith("Error from element") and ": " in text:
        text = text.split(": ", 1)[1]
    for cut in (" ../", " /Gst"):
        index = text.find(cut)
        if index > 0:
            text = text[:index]
    return text.strip() or message[:120]


def _ignore(result, error):
    if error is not None:
        log.info("report: %s", error)


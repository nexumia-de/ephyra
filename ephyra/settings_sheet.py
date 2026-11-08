"""The Playback Settings sheet that slides up inside the player: switches
such as autoplay, then the audio and subtitle tracks
(docs/player-controls.md#playback-settings)."""
from gi.repository import Adw, Gtk


class SettingsSheet(Gtk.Revealer):
    """A sheet inside the player, not a popover: popovers are own surfaces
    and would not turn with the rotated player. `on_close()` is called
    by its close button."""

    def __init__(self, on_close):
        # can_target only while open: closed, the revealer still covers the
        # whole video and took the taps meant for the buttons in the middle
        # (found on the phone, 2026-11-04).
        super().__init__(reveal_child=False, valign=Gtk.Align.FILL,
                         transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
                         margin_top=48, can_target=False)
        self.switches = Adw.PreferencesGroup(visible=False)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.append(self.switches)
        content.append(self.list)
        scrolled = Gtk.ScrolledWindow(child=content,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True)
        title = Gtk.Label(label="Playback Settings", hexpand=True, xalign=0)
        title.add_css_class("heading")
        close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close")
        close.update_property([Gtk.AccessibleProperty.LABEL], ["Close"])
        close.add_css_class("flat")
        close.add_css_class("circular")
        close.connect("clicked", lambda *_: on_close())
        top = Gtk.Box(spacing=6)
        top.append(title)
        top.append(close)
        # Filling the overlay, so a long list scrolls instead of running
        # past the edge (the overlay gives an END child its natural height).
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                           valign=Gtk.Align.END)
        self.box.add_css_class("ephyra-sheet")
        self.box.append(top)
        self.box.append(scrolled)
        self.set_child(Adw.Clamp(child=self.box, maximum_size=760))
        self._switch_rows = []

    @property
    def is_open(self):
        return self.get_reveal_child()

    def holds(self, widget):
        """Whether `widget` (from a pick) is part of the sheet itself."""
        return widget is not None and (widget is self.box or
                                       widget.is_ancestor(self.box))

    def open(self, groups, wide, switches=()):
        """`switches`: (title, active, callback(active)), on top across the
        whole width. `groups`: (title, [(index, label)], current,
        callback); side by side when `wide` (landscape), stacked
        otherwise."""
        while child := self.list.get_first_child():
            self.list.remove(child)
        for row in self._switch_rows:
            self.switches.remove(row)
        self._switch_rows = []
        for title, active, callback in switches:
            row = Adw.SwitchRow(title=title, active=active)
            row.connect("notify::active", lambda r, _p, c=callback:
                        c(r.get_active()))
            self.switches.add(row)
            self._switch_rows.append(row)
        self.switches.set_visible(bool(self._switch_rows))
        self.list.set_visible(bool(groups))
        self.list.set_orientation(Gtk.Orientation.HORIZONTAL if wide
                                  else Gtk.Orientation.VERTICAL)
        self.list.set_homogeneous(wide)
        for group in groups:
            self.list.append(_group(*group))
        self.set_can_target(True)
        self.set_reveal_child(True)

    def close(self):
        self.set_can_target(False)
        self.set_reveal_child(False)


def _group(title, tracks, current, callback):
    group = Adw.PreferencesGroup(title=title)
    first = None
    for index, label in tracks:
        check = Gtk.CheckButton(active=index == current, valign=Gtk.Align.CENTER)
        if first is None:
            first = check
        else:
            check.set_group(first)
        check.connect("toggled", lambda b, i=index:
                      b.get_active() and callback(i))
        row = Adw.ActionRow(title=label, activatable_widget=check)
        row.set_title_lines(2)
        row.add_prefix(check)
        group.add(row)
    return group

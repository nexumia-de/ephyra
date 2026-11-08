"""Preferences: connection (the setup form), playback quality per route,
playback behaviour and the account."""
from gi.repository import Adw, GLib, Gtk
from phosh_toolkit.style import style_row

from ephyra import settings
from ephyra.setup import connection_form


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__(title="Preferences")
        self.window = window
        conn = window.connection
        account = conn.account

        connection_page = Adw.PreferencesPage(
            title="Connection", icon_name="network-server-symbolic")
        self.form = connection_form(window, account, toast=self.toast)
        for group in self.form.groups:
            connection_page.add(group)
        actions = Adw.PreferencesGroup()
        self.save = Gtk.Button(label="Save and Reconnect",
                               halign=Gtk.Align.CENTER)
        self.save.add_css_class("pill")
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", self._on_save)
        actions.add(self.save)
        connection_page.add(actions)
        self.add(connection_page)

        general_page = Adw.PreferencesPage(
            title="General", icon_name="preferences-system-symbolic")
        appearance = Adw.PreferencesGroup(title="Appearance")
        self.style_row = style_row(account.style, self._on_style)
        appearance.add(self.style_row)
        general_page.add(appearance)
        quality = Adw.PreferencesGroup(
            title="Streaming Quality",
            description="Above this bitrate the server converts videos. "
                        "Original plays the file as it is when the phone "
                        "can decode it.")
        names = Gtk.StringList.new([name for _, name in settings.QUALITIES])
        for attr, title in (("quality_home", "At Home"),
                            ("quality_away", "Away")):
            row = Adw.ComboRow(title=title, model=names)
            values = [value for value, _ in settings.QUALITIES]
            current = getattr(account, attr)
            row.set_selected(values.index(current) if current in values else 0)
            row.connect("notify::selected", self._on_quality, attr, values)
            quality.add(row)
        general_page.add(quality)
        playing = Adw.PreferencesGroup(title="Playback")
        self.auto_next_row = Adw.SwitchRow(
            title="Play Next Episode Automatically",
            subtitle="Count down at the credits, then start the next episode",
            active=account.auto_next)
        self.auto_next_row.connect("notify::active", self._on_switch, "auto_next")
        playing.add(self.auto_next_row)
        self.screen_off_row = Adw.SwitchRow(
            title="Keep Playing With Screen Off",
            subtitle="Otherwise videos pause when the screen turns off",
            active=account.play_screen_off)
        self.screen_off_row.connect("notify::active", self._on_switch,
                                    "play_screen_off")
        playing.add(self.screen_off_row)
        general_page.add(playing)
        # General first: style and quality change more often than the
        # connection.
        self.remove(connection_page)
        self.add(general_page)
        self.add(connection_page)

        account_group = Adw.PreferencesGroup(title="Account")
        user = Adw.ActionRow(
            title=GLib.markup_escape_text(account.user_name or "Not signed in"),
            subtitle=GLib.markup_escape_text(account.server_name or ""))
        user.add_prefix(Gtk.Image(icon_name="avatar-default-symbolic"))
        sign_out = Gtk.Button(label="Sign Out", valign=Gtk.Align.CENTER)
        sign_out.add_css_class("destructive-action")
        sign_out.connect("clicked", self._on_sign_out)
        user.add_suffix(sign_out)
        account_group.add(user)
        connection_page.add(account_group)

    def toast(self, message):
        self.add_toast(Adw.Toast(title=GLib.markup_escape_text(message)))

    def _on_style(self, style):
        self.window.connection.account.style = style
        self.window.connection.save()

    def _on_quality(self, row, pspec, attr, values):
        setattr(self.window.connection.account, attr, values[row.get_selected()])
        self.window.connection.save()

    def _on_switch(self, row, pspec, attr):
        setattr(self.window.connection.account, attr, row.get_active())
        self.window.connection.save()

    def _on_save(self, *_):
        conn = self.window.connection

        def done(answers, http):
            self.save.set_sensitive(True)
            if answers is None:
                return
            ids = {a["Id"] for a in answers.values() if isinstance(a, dict)}
            if conn.account.server_id and conn.account.server_id not in ids:
                self.toast("That is a different server. Sign out first to "
                           "use it.")
                return
            self.form.apply(conn.account)
            conn.save()
            conn.load_certificate()
            conn.jellyfin.base_url = ""
            conn.resolve()
            self.toast("Saved")

        if self.form.check(done):
            self.save.set_sensitive(False)

    def _on_sign_out(self, *_):
        dialog = Adw.AlertDialog(
            heading="Sign Out?",
            body="Home Cinema forgets your access token. The server address and "
                 "certificate stay.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("sign-out", "Sign Out")
        dialog.set_response_appearance("sign-out",
                                       Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_sign_out_response)
        dialog.present(self)

    def _on_sign_out_response(self, dialog, response):
        if response != "sign-out":
            return
        self.window.connection.sign_out()
        self.close()
        self.window.show_setup()


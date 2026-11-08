import logging
import os
import tempfile
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from ephyra import (APP_ID, NAME, NIGHTLY, REPO_URL, SUPPORT_URL,  # noqa: E402
                    VERSION_LABEL)

log = logging.getLogger("ephyra")


def demo_connection():
    """EPHYRA_DEMO=<dir>: signed in to the recorded demo library served
    by ephyra.demo, with nothing stored on disk or in the keyring (store
    screenshots, docs/release-channels.md)."""
    os.environ["EPHYRA_KEYRING"] = "memory"
    from ephyra import connection, keyring, settings
    from ephyra.demo import TOKEN, DemoServer
    server = DemoServer(os.environ["EPHYRA_DEMO"]).start()
    store = settings.Store(Path(tempfile.mkdtemp(prefix="ephyra-demo-")) / "account.json")
    account = store.load()
    library = server.library
    account.remote_url = server.url
    account.server_id = library["server"]["Id"]
    account.server_name = library["server"]["ServerName"]
    account.user_id = library["user"]["Id"]
    account.user_name = library["user"]["Name"]
    store.save(account)
    keyring.store(keyring.TOKEN, TOKEN)
    conn = connection.Connection(store, watch=False)
    conn.demo_server = server
    return conn


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         # GTK tracks `screensaver-active` only then: the
                         # player pauses videos when the screen goes off.
                         register_session=True)
        self.connection = None
        for name, callback in (("about", self._on_about),
                               ("preferences", self._on_preferences),
                               ("search", self._on_search),
                               ("quit", lambda *_: self.quit())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        # app.show-view(n): Home (0) or the n-th library; Ctrl+1…9. An app
        # action so screenshots can open it over D-Bus.
        view = Gio.SimpleAction.new("show-view", GLib.VariantType("i"))
        view.connect("activate", self._on_show_view)
        self.add_action(view)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.preferences", ["<Control>comma"])
        self.set_accels_for_action("app.search", ["<Control>f"])
        for n in range(10):
            self.set_accels_for_action(f"app.show-view({n})",
                                       [f"<Control>{(n + 1) % 10}"])

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Running from the source tree: the app icon is not installed.
        icons = Path(__file__).resolve().parent.parent / "data" / "icons"
        if icons.is_dir():
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()) \
                .add_search_path(str(icons))
        if os.environ.get("EPHYRA_DEMO"):
            self.connection = demo_connection()
        else:
            from ephyra.connection import Connection
            self.connection = Connection()
        self.apply_style(self.connection.account.style)

    def apply_style(self, style):
        """Follow the system, or the light or dark style chosen in the
        preferences (docs/design.md)."""
        from phosh_toolkit import style as styles
        styles.apply(style)

    def do_activate(self):
        from ephyra.window import Window
        window = self.props.active_window
        if window is None:
            window = Window(self, self.connection)
            if os.environ.get("EPHYRA_DEMO"):
                window.maximize()
            if NIGHTLY:
                # libadwaita's striped header bar for development builds.
                window.add_css_class("devel")
        window.present()

    def _on_show_view(self, action, index):
        if self.props.active_window:
            self.props.active_window.show_view(index.unpack())

    def _on_search(self, *_):
        if self.props.active_window:
            self.props.active_window.show_search()

    def _on_preferences(self, *_):
        window = self.props.active_window
        if window and window.connection.signed_in:
            from ephyra.preferences import PreferencesDialog
            PreferencesDialog(window).present(window)

    def _on_about(self, *_):
        dialog = Adw.AboutDialog(
            application_name=NAME,
            application_icon=APP_ID,
            version=VERSION_LABEL,
            developer_name="suitably",
            website=REPO_URL,
            issue_url=f"{REPO_URL}/issues",
            license_type=Gtk.License.AGPL_3_0,
            comments="Watch your Jellyfin library on a Phosh phone. Not "
                     "affiliated with the Jellyfin project.",
        )
        dialog.add_link("Support Development", SUPPORT_URL)
        dialog.present(self.props.active_window)


def main(argv):
    # EPHYRA_DEBUG=1 logs routes, requests and playback.
    logging.basicConfig(format="ephyra: %(name)s: %(message)s")
    if os.environ.get("EPHYRA_DEBUG"):
        logging.getLogger("ephyra").setLevel(logging.DEBUG)
    return Application().run(argv)

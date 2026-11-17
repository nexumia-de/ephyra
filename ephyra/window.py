from gi.repository import Adw, GLib, Gtk
from phosh_toolkit import proxy_login
from phosh_toolkit.proxy import MediaProxy

from ephyra import NAME, text
from ephyra import connection as connection_module
from ephyra.browse import MainPage, SearchPage
from ephyra.detail import DetailPage
from ephyra.images import Images
from ephyra.player import PlayerPage
from ephyra.setup import SetupPage


class Window(Adw.ApplicationWindow):
    def __init__(self, app, connection):
        super().__init__(application=app, default_width=1000,
                         default_height=700, title=NAME)
        # Breakpoints need a minimum size (phosh-toolkit adaptive rules).
        self.set_size_request(360, 294)
        self.app_name = NAME
        self.app_icon = app.get_application_id()
        self.connection = connection
        self.images = Images(connection)
        self.proxy = MediaProxy(connection.forward)
        # A video playing when the route changes (Wi-Fi gone) moves to the
        # new address (phosh-toolkit docs/shared-connection.md).
        self.proxy.follow(connection)
        self.main = None
        self.nav = Adw.NavigationView()
        self.toasts = Adw.ToastOverlay(child=self.nav)
        self.set_content(self.toasts)

        breakpoint = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 600sp"))
        breakpoint.connect("apply", lambda *_: self._collapse(True))
        breakpoint.connect("unapply", lambda *_: self._collapse(False))
        self.add_breakpoint(breakpoint)
        self._collapsed = False

        connection.connect("signed-out", self._on_signed_out)
        connection.connect("proxy-login", self._on_proxy_login)
        if connection.signed_in:
            self.show_library()
            connection.resolve()
        else:
            self.show_setup()
        self.connect("close-request", lambda *_: self.proxy.stop())

    def _collapse(self, collapsed):
        self._collapsed = collapsed
        if self.main:
            self.main.split.set_collapsed(collapsed)

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(message)))

    # --- pages -------------------------------------------------------

    def show_setup(self):
        self.main = None
        self.nav.replace([SetupPage(self)])

    def show_library(self):
        self.main = MainPage(self)
        self.main.split.set_collapsed(self._collapsed)
        self.nav.replace([self.main])

    def show_view(self, index):
        """Home (0) or the n-th library of the sidebar."""
        if not self.main:
            return
        self.nav.pop_to_page(self.main)
        keys = ["home"] + [v["Id"] for v in self.main.views]
        if 0 <= index < len(keys):
            self.main.show(keys[index])
            self.main.split.set_show_content(True)

    def show_search(self):
        if self.main and not isinstance(self.nav.get_visible_page(), SearchPage):
            self.nav.push(SearchPage(self))

    def show_item(self, item):
        if item.get("Type") == "CollectionFolder" and self.main:
            self.nav.pop_to_page(self.main)
            self.main.show(item["Id"])
            self.main.split.set_show_content(True)
            return
        self.nav.push(DetailPage(self, item))

    def play(self, item, start=0):
        if item.get("MediaType") not in ("Video", "Audio"):
            self.show_item(item)
            return
        self.nav.push(PlayerPage(self, item, start))

    def play_instead(self, page, item, **carry):
        """The next episode in place of the player `page`, without an
        animation: back from it still leads to the page before. `carry`:
        the rotation of the player before (PlayerPage)."""
        stack = self.nav.get_navigation_stack()
        pages = [stack.get_item(i) for i in range(stack.get_n_items())]
        pages = [p for p in pages if p is not page]
        pages.append(PlayerPage(self, item, text.resume_seconds(item), **carry))
        self.nav.replace(pages)

    def after_playback(self, item):
        """Positions and played marks changed: reload the pages that show
        them, once the player is gone."""
        def refresh():
            stack = self.nav.get_navigation_stack()
            for i in range(stack.get_n_items()):
                page = stack.get_item(i)
                if isinstance(page, DetailPage):
                    page.refresh()
            if self.main:
                self.main.refresh()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(500, refresh)

    def _on_proxy_login(self, connection, url):
        """The reverse proxy in front of the server wants its own login
        (again): show its page (docs/connection.md)."""
        if connection.signed_in:
            proxy_login.sign_in(self.nav, connection, connection.jellyfin.http,
                                connection.proxy_cookies,
                                connection_module.probe_through, url,
                                certificate_hosts_extra=connection.account
                                .certificate_hosts)

    def _on_signed_out(self, *_):
        self.show_setup()
        self.toast("The server signed you out. Please sign in again.")

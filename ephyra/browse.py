"""The library: a sidebar with Home and the user's libraries, the home
sections, library grids and search."""
import logging

from gi.repository import Adw, Gio, Gtk, Pango

from phosh_toolkit import route

from ephyra import NAME, widgets
from ephyra.connection import CONNECTING, OFFLINE
from ephyra.library import LibraryView, SortActions, sort_menu

log = logging.getLogger("ephyra.browse")


def state_text(conn):
    return {route.LOCAL: "Home network", route.REMOTE: "Remote",
            CONNECTING: "Connecting…", OFFLINE: "Offline"}[conn.state]


class MainPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title=window.app_name, tag="library")
        self.window = window
        self.conn = window.connection
        self.views = []
        self.content_pages = {}
        # One /UserViews request at a time: the first route found during
        # sign-in used to send a second one (#21).
        self._views_pending = False

        # Sidebar
        self.sidebar_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.sidebar_list.add_css_class("navigation-sidebar")
        self.sidebar_list.connect("row-activated", self._on_row)
        self.sidebar_title = Adw.WindowTitle(title=window.app_name)
        header = Adw.HeaderBar(title_widget=self.sidebar_title)
        menu = Gio.Menu()
        menu.append("_Preferences", "app.preferences")
        menu.append(f"_About {NAME}", "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",
                                       menu_model=menu, primary=True,
                                       tooltip_text="Main Menu"))
        sidebar_view = Adw.ToolbarView()
        sidebar_view.add_top_bar(header)
        sidebar_view.set_content(Gtk.ScrolledWindow(
            child=self.sidebar_list, hscrollbar_policy=Gtk.PolicyType.NEVER))
        sidebar = Adw.NavigationPage(title=window.app_name, child=sidebar_view,
                                     tag="sidebar")

        # Content
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.banner = Adw.Banner(button_label="Retry")
        self.banner.connect("button-clicked", lambda *_: self.conn.resolve())
        search = Gtk.Button(icon_name="system-search-symbolic",
                            tooltip_text="Search")
        search.update_property([Gtk.AccessibleProperty.LABEL], ["Search"])
        search.set_action_name("app.search")
        # Sort order and filters of the library on screen (library.py).
        self.sort_actions = SortActions(self.conn, self._on_sort_changed)
        self.insert_action_group("library", self.sort_actions)
        self.sort_button = Gtk.MenuButton(
            icon_name="view-sort-descending-symbolic", menu_model=sort_menu(),
            tooltip_text="Sort and Filter", visible=False)
        self.sort_button.update_property([Gtk.AccessibleProperty.LABEL],
                                         ["Sort and Filter"])
        self.content_header = Adw.HeaderBar()
        self.content_header.pack_end(search)
        self.content_header.pack_end(self.sort_button)
        content_view = Adw.ToolbarView()
        content_view.add_top_bar(self.content_header)
        content_view.add_top_bar(self.banner)
        content_view.set_content(self.stack)
        self.content = Adw.NavigationPage(title="Home", child=content_view,
                                          tag="content")

        self.split = Adw.NavigationSplitView(sidebar=sidebar,
                                             content=self.content,
                                             show_content=True)
        self.set_child(self.split)
        self._state_handler = self.conn.connect("state-changed", self._on_state)
        self._on_state()
        self.reload()

    def close(self):
        """Replaced (signed out): no more requests for this page. It used
        to load the libraries again on the next route change and sign out
        a second time (#21)."""
        if self._state_handler:
            self.conn.disconnect(self._state_handler)
            self._state_handler = 0

    # --- sidebar -------------------------------------------------------

    def reload(self):
        """Fetch the libraries, then show Home."""
        if self._views_pending:
            return
        self._views_pending = True
        self.conn.call(self.conn.jellyfin.views, self._on_views)

    def _on_views(self, views, error):
        self._views_pending = False
        if error is not None:
            self._show_error(error, self.reload)
            return
        self.views = views or []
        while row := self.sidebar_list.get_row_at_index(0):
            self.sidebar_list.remove(row)
        self._add_row("go-home-symbolic", "Home", "home")
        for view in self.views:
            self._add_row(widgets.icon_for(view), view["Name"], view["Id"])
        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))
        self.show("home")

    def _add_row(self, icon, title, key):
        box = Gtk.Box(spacing=12)
        box.append(Gtk.Image(icon_name=icon))
        box.append(Gtk.Label(label=title, xalign=0,
                             ellipsize=Pango.EllipsizeMode.END))
        row = Gtk.ListBoxRow(child=box)
        row.key = key
        self.sidebar_list.append(row)

    def _on_row(self, listbox, row):
        self.show(row.key)
        self.split.set_show_content(True)

    def show(self, key):
        """Show "home" or a library by id."""
        for i, view in enumerate([None] + self.views):
            row = self.sidebar_list.get_row_at_index(i)
            if row and row.key == key:
                self.sidebar_list.select_row(row)
        if key not in self.content_pages:
            if key == "home":
                page = HomeView(self.window, self)
            else:
                view = next(v for v in self.views if v["Id"] == key)
                page = LibraryView(self.window, view)
            self.content_pages[key] = page
            self.stack.add_named(page, key)
        self.stack.set_visible_child_name(key)
        self.sort_button.set_visible(key != "home")
        if key != "home":
            self.sort_actions.show(key)
        title = "Home" if key == "home" else next(
            v["Name"] for v in self.views if v["Id"] == key)
        self.content.set_title(title)

    def _on_sort_changed(self, key):
        page = self.content_pages.get(key)
        if page is not None:
            page.reload()

    def refresh(self):
        """After playback: reload what shows progress."""
        for key, page in list(self.content_pages.items()):
            if key == "home":
                page.load()

    def _show_error(self, error, retry):
        page = widgets.error_page("Can't Reach the Server", str(error), retry)
        old = self.stack.get_child_by_name("error")
        if old:
            self.stack.remove(old)
        self.stack.add_named(page, "error")
        self.stack.set_visible_child_name("error")

    def _on_state(self, *_):
        server = self.conn.account.server_name or "Jellyfin"
        self.sidebar_title.set_subtitle(f"{server} · {state_text(self.conn)}")
        if self.conn.state == OFFLINE:
            self.banner.set_title("Can't reach the server")
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)
            if self.conn.state != CONNECTING and not self.views:
                self.reload()


class HomeView(Gtk.Stack):
    """Continue Watching, Next Up and the newest items of each library."""

    def __init__(self, window, main):
        super().__init__(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.window, self.main = window, main
        self.add_named(widgets.loading_page(), "loading")
        self._requests = 0
        self.load()

    def load(self):
        jellyfin = self.window.connection.jellyfin
        views = self.main.views
        self._requests += 1
        request = self._requests
        log.debug("home: request %d for %d libraries", request, len(views))

        def fetch():
            sections = [("Continue Watching", jellyfin.resume(), "landscape", None),
                        ("Next Up", jellyfin.next_up(), "landscape", None)]
            for view in views:
                if view.get("CollectionType") in ("movies", "tvshows", "music"):
                    sections.append((f"Latest {view['Name']}",
                                     jellyfin.latest(view["Id"]), "poster",
                                     view["Id"]))
            return sections

        self.window.connection.call(
            fetch, lambda sections, error: self._on_loaded(sections, error,
                                                           request))

    def _on_loaded(self, sections, error, request=0):
        log.debug("home: answer %d: %s", request,
                  "error" if error is not None else f"{len(sections)} sections")
        for name in ("content", "error"):
            old = self.get_child_by_name(name)
            if old:
                self.remove(old)
        if error is not None:
            self.add_named(widgets.error_page("Can't Load Home", str(error),
                                              self.load), "error")
            self.set_visible_child_name("error")
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30,
                      margin_top=18, margin_bottom=24, margin_start=12,
                      margin_end=12)
        shown = 0
        for title, items, shape, view_id in sections:
            if not items:
                continue
            shown += 1
            flow = widgets.card_box(self.window.images, items,
                                    self.window.show_item, shape)
            action = (lambda v=view_id: self.main.show(v)) if view_id else None
            box.append(widgets.section(title, flow, action))
        if not shown:
            page = Adw.StatusPage(icon_name="folder-videos-symbolic",
                                  title="Nothing Here Yet",
                                  description="Add media to your Jellyfin "
                                              "libraries to see it here")
            self.add_named(page, "content")
        else:
            clamp = Adw.Clamp(maximum_size=1400, child=box)
            self.add_named(Gtk.ScrolledWindow(
                child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER), "content")
        self.set_visible_child_name("content")


class SearchPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Search", tag="search")
        self.window = window
        self.entry = Gtk.SearchEntry(hexpand=True,
                                     placeholder_text="Movies, shows, music…")
        self.entry.connect("search-changed", self._on_changed)
        self.entry.connect("activate", self._on_changed)
        header = Adw.HeaderBar(title_widget=Adw.Clamp(maximum_size=400,
                                                      child=self.entry))
        self.store = Gio.ListStore.new(widgets.Item)
        self.stack = Gtk.Stack()
        self.stack.add_named(Adw.StatusPage(
            icon_name="system-search-symbolic", title="Search Your Library"),
            "start")
        self.stack.add_named(Adw.StatusPage(
            icon_name="system-search-symbolic", title="No Results",
            description="Try a different search"), "empty")
        self.stack.add_named(widgets.loading_page(), "loading")
        grid = widgets.CardGrid(window.images, self.store, window.show_item)
        self.stack.add_named(Gtk.ScrolledWindow(
            child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER), "results")
        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(header)
        self.set_child(view)
        self.connect("shown", lambda *_: self.entry.grab_focus())
        self._generation = 0

    def _on_changed(self, *_):
        term = self.entry.get_text().strip()
        self._generation += 1
        if len(term) < 2:
            self.stack.set_visible_child_name("start")
            return
        self.stack.set_visible_child_name("loading")
        generation = self._generation
        jellyfin = self.window.connection.jellyfin

        def search():
            return jellyfin.items(
                search=term, recursive=True, limit=60,
                types="Movie,Series,Episode,MusicAlbum,Audio,BoxSet")

        def done(result, error):
            if generation != self._generation:
                return
            if error is not None:
                self.window.toast(str(error))
                self.stack.set_visible_child_name("start")
                return
            self.store.remove_all()
            for data in result.get("Items", []):
                self.store.append(widgets.Item(data))
            self.stack.set_visible_child_name(
                "results" if self.store.get_n_items() else "empty")

        self.window.connection.call(search, done)

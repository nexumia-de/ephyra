"""A library grid, a page at a time, with its sort order and filters kept
per library in the account file (docs/design.md, "Libraries")."""
from gi.repository import Adw, Gio, GLib, Gtk

from ephyra import widgets

# Item types a library grid lists, by the library's collection type.
LIBRARY_TYPES = {"movies": "Movie", "tvshows": "Series",
                 "music": "MusicAlbum", "boxsets": "BoxSet"}
PAGE = 60

# Jellyfin's ItemSortBy values with the menu label and the order a new
# choice starts with: names A to Z, the newest and best rated first.
SORTS = (("SortName", "Name", "Ascending"),
         ("DateCreated", "Date Added", "Descending"),
         ("PremiereDate", "Release Date", "Descending"),
         ("CommunityRating", "Rating", "Descending"))
# Jellyfin's ItemFilter values with the menu label.
FILTERS = (("IsUnplayed", "Unplayed"), ("IsFavorite", "Favorites"))
DEFAULT = {"sort": "SortName", "order": "Ascending", "filters": []}


def options(account, view_id):
    """The sort order and filters of a library; unknown values from an
    older or edited account file fall back to the defaults."""
    stored = account.library_options.get(view_id) or {}
    sort = stored.get("sort")
    if sort not in {s for s, _, _ in SORTS}:
        sort = DEFAULT["sort"]
    order = stored.get("order")
    if order not in ("Ascending", "Descending"):
        order = next(o for s, _, o in SORTS if s == sort)
    known = {f for f, _ in FILTERS}
    filters = [f for f in stored.get("filters") or [] if f in known]
    return {"sort": sort, "order": order, "filters": filters}


def query(opts):
    """sortBy, sortOrder and filters for GET /Items. SortName second keeps
    items with the same date or rating in a stable order; the one sortOrder
    applies to both (RequestHelpers.GetOrderBy)."""
    sort = opts["sort"]
    if sort != "SortName":
        sort += ",SortName"
    return sort, opts["order"], ",".join(opts["filters"]) or None


def sort_menu():
    menu = Gio.Menu()
    sorts = Gio.Menu()
    for value, label, _ in SORTS:
        sorts.append(label, f"library.sort::{value}")
    menu.append_section("Sort By", sorts)
    order = Gio.Menu()
    order.append("Ascending", "library.order::Ascending")
    order.append("Descending", "library.order::Descending")
    menu.append_section(None, order)
    show = Gio.Menu()
    for value, label in FILTERS:
        show.append(label, f"library.{value}")
    menu.append_section("Show Only", show)
    return menu


class SortActions(Gio.SimpleActionGroup):
    """library.sort, library.order and one toggle per filter, for the
    library on screen (`view_id`). Changes are saved and reload it."""

    def __init__(self, conn, on_changed):
        super().__init__()
        self.conn, self.on_changed = conn, on_changed
        self.view_id = None
        self._setting = False
        string = GLib.VariantType("s")
        for name in ("sort", "order"):
            action = Gio.SimpleAction.new_stateful(name, string,
                                                   GLib.Variant("s", ""))
            action.connect("change-state", self._on_change)
            self.add_action(action)
        for value, _ in FILTERS:
            action = Gio.SimpleAction.new_stateful(value, None,
                                                   GLib.Variant("b", False))
            action.connect("change-state", self._on_change)
            self.add_action(action)

    def show(self, view_id):
        """Show the options of `view_id` in the menu."""
        self.view_id = view_id
        opts = options(self.conn.account, view_id)
        self._setting = True
        self.lookup_action("sort").set_state(GLib.Variant("s", opts["sort"]))
        self.lookup_action("order").set_state(GLib.Variant("s", opts["order"]))
        for value, _ in FILTERS:
            self.lookup_action(value).set_state(
                GLib.Variant("b", value in opts["filters"]))
        self._setting = False

    def _on_change(self, action, value):
        if self._setting or self.view_id is None:
            return
        opts = options(self.conn.account, self.view_id)
        name = action.get_name()
        if name == "sort":
            opts["sort"] = value.get_string()
            opts["order"] = next(o for s, _, o in SORTS if s == opts["sort"])
        elif name == "order":
            opts["order"] = value.get_string()
        else:
            filters = [f for f in opts["filters"] if f != name]
            if value.get_boolean():
                filters.append(name)
            opts["filters"] = [f for f, _ in FILTERS if f in filters]
        self.conn.account.library_options[self.view_id] = opts
        self.conn.save()
        self.show(self.view_id)
        self.on_changed(self.view_id)


class LibraryView(Gtk.Stack):
    """All items of a library, a page at a time, in its sort order."""

    def __init__(self, window, view):
        super().__init__(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.window, self.view = window, view
        self.store = Gio.ListStore.new(widgets.Item)
        self.total = None
        self.loading = False
        # Answers to an earlier sort order are dropped.
        self._generation = 0
        grid = widgets.CardGrid(window.images, self.store, window.show_item)
        self.scrolled = Gtk.ScrolledWindow(
            child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scrolled.connect("edge-reached", self._on_edge)
        self.add_named(widgets.loading_page(), "loading")
        self.add_named(self.scrolled, "content")
        self.load_more()

    def reload(self):
        """From the start, after the sort order or a filter changed."""
        self._generation += 1
        self.loading = False
        self.total = None
        self.store.remove_all()
        self.scrolled.get_vadjustment().set_value(0)
        self.set_visible_child_name("loading")
        self.load_more()

    def _on_edge(self, scrolled, position):
        if position == Gtk.PositionType.BOTTOM:
            self.load_more()

    def load_more(self):
        if self.loading or (self.total is not None
                            and self.store.get_n_items() >= self.total):
            return
        self.loading = True
        types = LIBRARY_TYPES.get(self.view.get("CollectionType"))
        sort, order, filters = query(
            options(self.window.connection.account, self.view["Id"]))
        jellyfin = self.window.connection.jellyfin
        generation = self._generation
        self.window.connection.call(
            lambda: jellyfin.items(self.view["Id"], self.store.get_n_items(),
                                   PAGE, types, bool(types), sort=sort,
                                   order=order, filters=filters),
            lambda result, error: self._on_loaded(generation, result, error))

    def _on_loaded(self, generation, result, error):
        if generation != self._generation:
            return
        self.loading = False
        if error is not None:
            if self.store.get_n_items():
                self.window.toast(str(error))
                return
            old = self.get_child_by_name("error")
            if old:
                self.remove(old)
            self.add_named(widgets.error_page("Can't Load the Library",
                                              str(error), self.load_more), "error")
            self.set_visible_child_name("error")
            return
        self.total = result.get("TotalRecordCount", 0)
        for data in result.get("Items", []):
            self.store.append(widgets.Item(data))
        if self.store.get_n_items():
            self.set_visible_child_name("content")
            return
        old = self.get_child_by_name("empty")
        if old:
            self.remove(old)
        filtered = options(self.window.connection.account,
                           self.view["Id"])["filters"]
        page = Adw.StatusPage(
            icon_name=widgets.icon_for(self.view),
            title="No Matching Items" if filtered else "Empty Library",
            description="Change the filters in the sort menu" if filtered
            else None)
        self.add_named(page, "empty")
        self.set_visible_child_name("empty")

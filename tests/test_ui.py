"""The whole flow through the real widgets against the demo server behind
mutual TLS: setup, sign in, home, a library, details, the player and the
preferences. Needs a display (CI runs pytest under xvfb-run)."""
import os
from pathlib import Path

import pytest

from conftest import P12_PASSWORD, owning_main_context, run_until

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    pytest.skip("needs a display", allow_module_level=True)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from phosh_toolkit import connection_form, router  # noqa: E402
from phosh_toolkit.http import Client  # noqa: E402

from ephyra import connection, settings, setup  # noqa: E402
from ephyra.demo import PASSWORD  # noqa: E402

CLIP = Path(__file__).resolve().parent / "data" / "media" / "clip.webm"
TRACKS = CLIP.with_name("tracks.mkv")


@pytest.fixture(scope="module")
def app():
    """One application for all tests: a second one with the same id can't
    register on the session bus."""
    from ephyra.main import Application
    application = Application()
    application.register(None)
    Adw.init()
    yield application


def visible(window):
    return window.nav.get_visible_page()


def test_setup_sign_in_browse_and_play(app, mtls_demo, pki, trust, monkeypatch):
    from ephyra.browse import MainPage
    from ephyra.detail import DetailPage
    from ephyra.player import PlayerPage
    from ephyra.preferences import PreferencesDialog
    from ephyra.window import Window

    def trusting_client(user_agent):
        client = Client(user_agent)
        client.tls_database = trust
        return client
    monkeypatch.setattr(connection_form, "Client", trusting_client)
    monkeypatch.setattr(router.network, "current_ssids", lambda: {"Home"})
    monkeypatch.setattr(connection_form.network, "current_ssids", lambda: {"Home"})

    conn = connection.Connection(watch=False)
    conn.jellyfin.http.tls_database = trust
    window = Window(app, conn)
    window.present()
    page = visible(window)
    assert isinstance(page, setup.SetupPage)

    # Without the certificate the server refuses, and the row is marked.
    page.form.remote.set_text(mtls_demo.url)
    page.form.local.set_text("http://127.0.0.1:9")
    page.form._add("Home")
    toasts = []
    monkeypatch.setattr(window, "toast", toasts.append)
    page.form.toast = window.toast
    page.button.emit("clicked")
    run_until(lambda: page.button.get_sensitive())
    assert "client certificate" in toasts[-1]
    assert page.form.cert_row.has_css_class("error")

    page.form.certificate_data = (pki / "client.p12").read_bytes()
    page.form.password.set_text(P12_PASSWORD)
    page.button.emit("clicked")
    run_until(lambda: isinstance(visible(window), setup.SignInPage))

    sign_in = visible(window)
    sign_in.user.set_text("robin")
    sign_in.password.set_text(PASSWORD)
    sign_in.button.emit("clicked")
    run_until(lambda: isinstance(visible(window), MainPage))

    account = settings.Store().load()
    assert account.signed_in and account.certificate
    assert account.home_networks == ["Home"]
    assert account.local_url == "http://127.0.0.1:9"
    assert settings.certificate_path().stat().st_mode & 0o777 == 0o600

    main = visible(window)
    run_until(lambda: main.views and "home" in main.content_pages
              and main.content_pages["home"].get_visible_child_name() == "content")
    # At "home" the local address is down, so the remote one is used.
    run_until(lambda: conn.state == "remote")

    window.show_view(1)
    movies = main.content_pages[main.views[0]["Id"]]
    run_until(lambda: movies.store.get_n_items() == 8)

    movie = movies.store.get_item(0).data
    window.show_item(movie)
    detail = visible(window)
    assert isinstance(detail, DetailPage)
    run_until(lambda: detail.stack.get_visible_child_name() == "content")

    with owning_main_context():
        # The demo "video" is not media: the player shows its error page and
        # offers server-side conversion.
        window.play(detail.item, 0)
        player = visible(window)
        assert isinstance(player, PlayerPage)
        run_until(lambda: player.stream is not None)
        assert player.stream.path.startswith(f"/Videos/{movie['Id']}/stream")
        run_until(lambda: player.stack.get_visible_child_name() == "error", 20)
        window.nav.pop()
        run_until(lambda: player.stopped)
        assert isinstance(visible(window), DetailPage)

        # A real clip: double tap seeks and shows the bubble, the rotate
        # button turns the player and goes fullscreen (docs/player-controls.md).
        mtls_demo.media = CLIP.read_bytes()
        window.play(detail.item, 2)
        player = visible(window)
        run_until(lambda: player.media is not None and player.media.is_seekable()
                  and player.position() >= 1.5, 20)
        player.media.pause()

        # A tap on a button in the middle reaches the button: nothing lies
        # on top of it, also not the closed audio and subtitle sheet.
        from gi.repository import Graphene

        def tapped(button):
            point = Graphene.Point()
            point.init(button.get_width() / 2, button.get_height() / 2)
            ok, at = button.compute_point(player.overlay, point)
            target = player.overlay.pick(at.x, at.y, Gtk.PickFlags.DEFAULT)
            return target is button or (target is not None
                                        and target.is_ancestor(button))
        buttons = list(player.transport)
        assert player.play_button in buttons and len(buttons) == 3
        run_until(lambda: all(b.get_mapped() and b.get_width() > 0 for b in buttons))
        assert all(tapped(b) for b in buttons)
        player.open_tracks()
        player.close_tracks()
        player._show_controls()
        run_until(lambda: not player.sheet.get_child_revealed())
        assert all(tapped(b) for b in buttons)

        player.tap(1, "back", True)
        player.tap(2, "back", True)
        assert player.bubbles["back"].get_reveal_child()
        assert player.bubbles["back"].label.get_label() == "10 s"
        run_until(lambda: player.position() < 1)
        player.tap(3, "back", True)
        assert player.bubbles["back"].label.get_label() == "20 s"
        assert not player.center.get_reveal_child()
        # Rotating asks for fullscreen; whether the window gets it is up to
        # the compositor (CI's Xvfb has no window manager, phoc grants it).
        requests = []
        with pytest.MonkeyPatch.context() as fake:
            fake.setattr(window, "fullscreen", lambda: requests.append("on"))
            fake.setattr(window, "unfullscreen", lambda: requests.append("off"))
            fake.setattr(window, "is_fullscreen", lambda: requests[-1:] == ["on"])
            player.toggle_rotation()
            assert player.rotator.props.rotated and requests == ["on"]
            player.toggle_rotation()
            assert not player.rotator.props.rotated and requests == ["on", "off"]
        window.nav.pop()
        run_until(lambda: player.stopped)

        # Audio and subtitles (docs/playback.md): German audio switches inside
        # GStreamer, the subtitle comes as SRT and Ephyra draws it.
        mtls_demo.media = TRACKS.read_bytes()
        mtls_demo.media_streams = [
            {"Index": 0, "Type": "Video", "Codec": "vp8"},
            {"Index": 1, "Type": "Audio", "Language": "eng", "DisplayTitle": "English"},
            {"Index": 2, "Type": "Audio", "Language": "ger", "DisplayTitle": "German"},
            {"Index": 3, "Type": "Subtitle", "Language": "eng", "DisplayTitle": "English"}]
        mtls_demo.subtitles = b"1\n00:00:00,000 --> 00:00:30,000\n<i>Hello</i>\n\n"
        window.play(detail.item, 0)
        player = visible(window)
        run_until(lambda: player.media is not None and player.media.is_prepared(), 20)
        assert player.tracks_button.get_visible()
        assert player.stream.audio_index == 1 and player.stream.subtitle_index == -1
        player.open_tracks()
        assert player.sheet.get_reveal_child()
        # The bars are drawn over the video: they stay hidden while the
        # sheet is open, also when playback events want to show them.
        player._show_controls()
        assert not player.view.get_reveal_bottom_bars()
        assert not player.view.get_reveal_top_bars()
        player.choose_audio(2)
        assert player.media.audio_position == 1
        media = player.media
        player.choose_subtitle(3)
        # No restart: the same pipeline plays on.
        assert player.media is media
        run_until(lambda: player.subtitle_label.get_visible(), 20)
        assert player.subtitle_label.get_label() == "<i>Hello</i>"
        assert any(path.endswith("/Subtitles/3/0/Stream.srt")
                   for _, path, _ in mtls_demo.requests)
        assert player.stream.report(0)["SubtitleStreamIndex"] == 3
        player.choose_subtitle(-1)
        run_until(lambda: not player.subtitle_label.get_visible())
        # A choice closes the sheet, and so does a tap beside it.
        assert not player.sheet.get_reveal_child()
        player.open_tracks()
        player._on_tap(None, 1, 1, 1)
        assert not player.sheet.get_reveal_child()
        window.nav.pop()
        run_until(lambda: player.stopped)
        mtls_demo.media_streams = []

    dialog = PreferencesDialog(window)
    dialog.present(window)
    assert dialog.form.remote.get_text() == mtls_demo.url
    # Style: follows the system until chosen, kept in the account file.
    manager = Adw.StyleManager.get_default()
    assert manager.get_color_scheme() == Adw.ColorScheme.DEFAULT
    dialog.style_row.set_selected(2)
    assert manager.get_color_scheme() == Adw.ColorScheme.FORCE_DARK
    assert settings.Store().load().style == "dark"
    dialog.style_row.set_selected(0)
    assert manager.get_color_scheme() == Adw.ColorScheme.DEFAULT
    dialog.close()
    window.destroy()


def test_server_rejecting_the_token_shows_setup(app, demo, monkeypatch):
    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "revoked")
    conn = connection.Connection(store, watch=False)
    window = Window(app, conn)
    window.present()
    run_until(lambda: isinstance(visible(window), setup.SetupPage))
    assert not conn.signed_in
    window.destroy()




def test_proxy_login_opens_the_login_page(app, demo, monkeypatch):
    """The router's "proxy-login" signal (the proxy's session ran out)
    opens the toolkit's login page; its cookies are loaded at start."""
    from phosh_toolkit import proxy_login
    from phosh_toolkit.http import origin

    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
    proxy_login.CookieJar(keyring.KEYRING).save({origin(demo.url): "s=1"})
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "t")
    conn = connection.Connection(store, watch=False)
    assert conn.jellyfin.http.cookies == {origin(demo.url): "s=1"}
    calls = []
    monkeypatch.setattr(proxy_login, "sign_in", lambda *a: calls.append(a))
    window = Window(app, conn)
    conn.emit("proxy-login", demo.url + "/login")
    assert calls and calls[0][0] is window.nav and calls[0][5] == demo.url + "/login"
    window.destroy()


def test_playing_video_follows_the_route(app, demo, monkeypatch):
    """When the route changes (Wi-Fi gone), the media proxy cuts the
    running stream so the player reconnects through the new address."""
    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "demo")
    conn = connection.Connection(store, watch=False)
    window = Window(app, conn)
    calls = []
    monkeypatch.setattr(window.proxy, "reroute", lambda: calls.append(1))
    conn.base_url = demo.url
    conn.emit("state-changed")
    assert calls == []          # the first route is no change
    conn.base_url = "http://127.0.0.1:9"
    conn.emit("state-changed")
    assert calls == [1]
    window.destroy()


def test_player_never_leaves_a_transcode_running(app, demo, monkeypatch):
    """Every stream the player chose is stopped on the server, also when
    the page is left before GStreamer had it prepared, on a reload and
    after an error; a converted one also with DELETE
    /Videos/ActiveEncodings (docs/playback.md). Seen on the owner's
    server: four ffmpeg jobs for one movie after slow starts."""
    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "demo-token")
    conn = connection.Connection(store, watch=False)
    conn.jellyfin.token = "demo-token"
    conn.jellyfin.user_id = account.user_id
    conn.base_url = conn.jellyfin.base_url = demo.url
    window = Window(app, conn)
    window.present()
    movie = next(i for i in demo.library["items"] if i["Type"] == "Movie")
    device = conn.jellyfin.device_id

    def stopped():
        return [(p["PlaySessionId"], p.get("Failed", False))
                for path, p in demo.reports if path.endswith("/Stopped")]

    with owning_main_context():
        # A converted stream whose ffmpeg starts slowly: left while loading.
        demo.transcode = True
        demo.hold.clear()
        window.play(movie, 0)
        player = visible(window)
        run_until(lambda: player.stream is not None)
        session = player.stream.play_session_id
        assert player.waiting.get_visible() and player.converting.get_visible()
        assert not player.started
        window.nav.pop()
        run_until(lambda: (device, session) in demo.stopped_encodings)
        assert stopped() == [(session, True)]

        # The page closes before the server's answer arrives: that stream
        # is stopped as soon as it comes, never played.
        window.play(movie, 0)
        player = visible(window)
        assert player.stream is None
        window.nav.pop()
        run_until(lambda: len(demo.stopped_encodings) == 2)
        assert player.stream is None and player.media is None
        assert demo.stopped_encodings[1] == (device, f"demo-session-{demo.sessions}")

        # Another audio track in a converted stream asks again: the old
        # stream is stopped first, and only the new one stays.
        demo.media_streams = [
            {"Index": 0, "Type": "Video", "Codec": "h264"},
            {"Index": 1, "Type": "Audio", "DisplayTitle": "English"},
            {"Index": 2, "Type": "Audio", "DisplayTitle": "German"}]
        window.play(movie, 0)
        player = visible(window)
        run_until(lambda: player.stream is not None)
        first = player.stream.play_session_id
        player.choose_audio(2)
        run_until(lambda: player.stream is not None
                  and player.stream.play_session_id != first)
        assert (device, first) in demo.stopped_encodings
        assert demo.playback_requests[-1]["AudioStreamIndex"] == 2
        # The server took the choice (it needs the MediaSourceId for it).
        assert player.stream.audio_index == 2 and player.audio_index == 2
        second = player.stream.play_session_id
        window.nav.pop()
        run_until(lambda: (device, second) in demo.stopped_encodings)
        demo.media_streams = []
        demo.hold.set()

        # The phone can't play the file: the error page already ends the
        # stream; Convert on the Server starts exactly one new one.
        demo.transcode = False
        demo.reports.clear()
        window.play(movie, 0)
        player = visible(window)
        run_until(lambda: player.stack.get_visible_child_name() == "error", 20)
        run_until(lambda: len(stopped()) == 1)
        direct = stopped()[0]
        assert direct[1] is True and player.stream is None
        encodings = len(demo.stopped_encodings)
        demo.hold.clear()
        player._retry_transcoded()
        run_until(lambda: player.stream is not None)
        assert player.stream.method == "Transcode"
        retried = player.stream.play_session_id
        assert len(demo.stopped_encodings) == encodings
        window.nav.pop()
        run_until(lambda: (device, retried) in demo.stopped_encodings)
        assert [s for s, _ in stopped()] == [direct[0], retried]
        demo.hold.set()
    window.destroy()


EPISODE = "770b908b6aad4ce9da249cbe6fd219cd"     # S1:E6
FOLLOWING = "290cd9a50691e695710c310a60ab9853"   # S2:E1


def _episode_window(app, demo, monkeypatch):
    """A signed-in phone-sized window and S1:E6, whose 30 s clip has an
    intro (0–10 s) and credits (24 s to the end)."""
    from ephyra import keyring
    from ephyra.window import Window
    monkeypatch.setattr(router.network, "current_ssids", lambda: None)
    store = settings.Store()
    account = store.load()
    account.remote_url = demo.url
    account.server_id = demo.library["server"]["Id"]
    account.user_id = demo.library["user"]["Id"]
    store.save(account)
    keyring.store(keyring.TOKEN, "demo-token")
    conn = connection.Connection(store, watch=False)
    conn.jellyfin.token = "demo-token"
    conn.jellyfin.user_id = account.user_id
    conn.base_url = conn.jellyfin.base_url = demo.url
    window = Window(app, conn)
    # A phone held upright: the player can turn itself sideways.
    window.set_default_size(360, 720)
    window.present()
    episode = demo.items[EPISODE]
    ticks = 10_000_000
    demo.segments[episode["Id"]] = [
        {"Type": "Intro", "StartTicks": 0, "EndTicks": 10 * ticks},
        {"Type": "Outro", "StartTicks": 24 * ticks, "EndTicks": 30 * ticks}]
    demo.media = TRACKS.read_bytes()
    return window, episode


def test_skip_intro_end_time_and_next_episode(app, demo, monkeypatch):
    """Skip Intro seeks to the end of the intro, the end time shows next
    to the duration, and at the credits the up-next card counts down to
    the next episode, which replaces the player and keeps it turned
    (docs/player-controls.md)."""
    from ephyra.player import PlayerPage
    from ephyra.upnext import COUNTDOWN
    window, episode = _episode_window(app, demo, monkeypatch)
    following = FOLLOWING

    with owning_main_context():
        window.play(episode, 0)
        player = visible(window)
        skipper = player.skipper
        run_until(lambda: player.started and skipper.next_episode is not None, 20)
        player.media.pause()
        assert skipper.next_episode["Id"] == following
        assert player.next_button.get_visible()
        run_until(lambda: skipper.skip_revealer.get_reveal_child())
        assert skipper.button.get_label() == "Skip Intro"
        assert player.ends_label.get_visible()
        assert player.ends_label.get_label().startswith("Ends at ")
        skipper.button.emit("clicked")
        run_until(lambda: player.position() >= 9.5, 20)
        run_until(lambda: not skipper.skip_revealer.get_reveal_child())
        assert not skipper.card.shown

        # The credits: the card instead of a Skip Credits button.
        player.seek_to(25)
        run_until(lambda: skipper.card.shown, 20)
        assert not skipper.skip_revealer.get_reveal_child()
        assert "S2:E1" in skipper.card.title.get_label()
        skipper.card.emit("cancel")
        assert not skipper.card.shown and not skipper.wants_next()
        # Back before the credits and there again: offered again.
        player.seek_to(12)
        run_until(lambda: player.position() < 20, 20)
        assert not skipper.cancelled
        player.seek_to(25)
        run_until(lambda: skipper.card.shown, 20)

        player.toggle_rotation()
        # Carried over only in a portrait window (the only place it is offered).
        turned = player.rotator.props.portrait
        for _ in range(COUNTDOWN):
            skipper.tick()
        run_until(lambda: visible(window) is not player)
        assert player.stopped
        nxt = visible(window)
        assert isinstance(nxt, PlayerPage) and nxt.item["Id"] == following
        assert nxt.rotator.props.rotated is turned
        # Back from the next episode leads where the first one came from.
        stack = window.nav.get_navigation_stack()
        assert not any(stack.get_item(i) is player for i in range(stack.get_n_items()))
        run_until(lambda: any(path.endswith("/Stopped") for path, _ in demo.reports))
        run_until(lambda: nxt.started, 20)
        window.nav.pop()
        run_until(lambda: nxt.stopped)
    window.destroy()


def test_auto_next_off_in_the_player_and_the_preferences(app, demo, monkeypatch):
    """The player's Play Next Episode Automatically button and the
    preference are one setting: off, no card at the credits (Skip Credits
    instead) and the player closes at the end (docs/player-controls.md)."""
    from ephyra.preferences import PreferencesDialog
    window, episode = _episode_window(app, demo, monkeypatch)
    account = window.connection.account
    assert account.auto_next and not account.play_screen_off
    toasts = []
    monkeypatch.setattr(window, "toast", toasts.append)

    with owning_main_context():
        window.play(episode, 0)
        player = visible(window)
        skipper = player.skipper
        run_until(lambda: player.started and skipper.next_episode is not None, 20)
        player.media.pause()
        assert player.auto_next_button.get_visible()
        assert player.auto_next_button.get_active()
        # In the bar, which still fits a phone held upright.
        bar = player.auto_next_button.get_ancestor(Gtk.CenterBox)
        assert bar.measure(Gtk.Orientation.HORIZONTAL, -1)[0] <= 360 - 12
        player.seek_to(25)
        run_until(lambda: skipper.card.shown, 20)

        player.auto_next_button.set_active(False)
        assert not account.auto_next and toasts
        assert settings.Store().load().auto_next is False
        assert not skipper.card.shown and not skipper.wants_next()
        run_until(lambda: skipper.skip_revealer.get_reveal_child())
        assert skipper.button.get_label() == "Skip Credits"
        # The Next Episode button still plays it on request.
        assert player.next_button.get_visible()

        # The video ends: the player closes instead of going on.
        player.media.play()
        run_until(lambda: player.stopped, 30)
        assert not any(isinstance(window.nav.get_navigation_stack().get_item(i),
                                  type(player))
                       for i in range(window.nav.get_navigation_stack().get_n_items()))

    dialog = PreferencesDialog(window)
    assert not dialog.auto_next_row.get_active()
    assert not dialog.screen_off_row.get_active()
    dialog.auto_next_row.set_active(True)
    dialog.screen_off_row.set_active(True)
    stored = settings.Store().load()
    assert stored.auto_next and stored.play_screen_off
    window.destroy()

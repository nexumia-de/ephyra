"""The Jellyfin API, the connection on top of phosh_toolkit's router, and
the media proxy against the demo server, also behind mutual TLS. The
toolkit's own tests cover the router and the proxy in general."""
import urllib.request

import pytest
from phosh_toolkit import router, tls
from phosh_toolkit.http import AUTH, CERTIFICATE_REQUIRED, Client, HttpError
from phosh_toolkit.proxy import MediaProxy
from phosh_toolkit.route import LOCAL, REMOTE

from conftest import P12_PASSWORD, run_until
from ephyra import USER_AGENT, connection, keyring, playback, settings
from ephyra.api import Jellyfin
from ephyra.demo import PASSWORD, TOKEN


def signed_in(url, http=None):
    jellyfin = Jellyfin(http=http, device_id="test")
    jellyfin.base_url = url
    jellyfin.authenticate("robin", PASSWORD)
    return jellyfin


def test_authorization_header():
    jellyfin = Jellyfin(device_id="abc", device_name='Robin "FP6"')
    jellyfin.token = "t"
    header = jellyfin.authorization()
    assert header.startswith('MediaBrowser Client="Ephyra", ')
    assert 'Device="Robin \\"FP6\\""' in header
    assert 'DeviceId="abc"' in header and header.endswith('Token="t"')


def test_sign_in_and_browse(demo):
    jellyfin = signed_in(demo.url)
    assert jellyfin.token == TOKEN
    views = jellyfin.views()
    assert [v["CollectionType"] for v in views] == ["movies", "tvshows", "music"]
    movies = jellyfin.items(views[0]["Id"], types="Movie", recursive=True)
    assert movies["TotalRecordCount"] == 8
    series = jellyfin.items(views[1]["Id"], types="Series", recursive=True)["Items"][0]
    seasons = jellyfin.seasons(series["Id"])
    assert len(jellyfin.episodes(series["Id"], seasons[0]["Id"])) == 6
    assert jellyfin.resume()[0]["Name"] == "The Lighthouse Keeper"
    assert jellyfin.image(series["Id"], "Primary").startswith(b"\xff\xd8")


def test_wrong_password(demo):
    jellyfin = Jellyfin()
    jellyfin.base_url = demo.url
    with pytest.raises(HttpError) as e:
        jellyfin.authenticate("robin", "nope")
    assert e.value.kind == AUTH


def test_mtls_requires_the_client_certificate(mtls_demo, pki, trust):
    http = Client(USER_AGENT)
    http.tls_database = trust
    with pytest.raises(HttpError) as e:
        Jellyfin(http=http).public_info(mtls_demo.url)
    assert e.value.kind == CERTIFICATE_REQUIRED
    http = Client(USER_AGENT)
    http.tls_database = trust
    http.certificate = tls.load((pki / "client.p12").read_bytes(), P12_PASSWORD)
    jellyfin = signed_in(mtls_demo.url, http)
    assert jellyfin.views()


def _connection(local, remote, networks=(), ssids=None, monkeypatch=None):
    store = settings.Store()
    account = store.load()
    account.local_url, account.remote_url = local, remote
    account.home_networks = list(networks)
    account.server_id = "f" * 32 if local == "bad" else ""
    store.save(account)
    monkeypatch.setattr(router.network, "current_ssids", lambda: ssids)
    return connection.Connection(store, watch=False)


def _resolve(conn):
    done = []
    conn.resolve(lambda e: done.append(e))
    run_until(lambda: done)
    return done[0]


def test_home_network_uses_local(demo, monkeypatch):
    conn = _connection(demo.url, "https://unreachable.invalid", ["Home"],
                       {"Home"}, monkeypatch)
    assert _resolve(conn) is None
    assert conn.state == LOCAL and conn.jellyfin.base_url == demo.url


def test_away_uses_remote(demo, monkeypatch):
    conn = _connection("http://127.0.0.1:9", demo.url, ["Home"], {"Café"},
                       monkeypatch)
    assert _resolve(conn) is None
    assert conn.state == REMOTE


def test_local_down_falls_back_to_remote(demo, monkeypatch):
    # Port 9 (discard) is closed: the local probe fails fast.
    conn = _connection("http://127.0.0.1:9", demo.url, ["Home"], {"Home"},
                       monkeypatch)
    assert _resolve(conn) is None
    assert conn.state == REMOTE


def test_other_server_at_local_address_is_skipped(demo, monkeypatch):
    conn = _connection(demo.url, "", [], None, monkeypatch)
    conn.account.server_id = "0" * 32
    assert isinstance(_resolve(conn), HttpError)
    assert conn.state == router.OFFLINE


def test_sign_in_stores_the_token(demo, monkeypatch):
    conn = _connection("", demo.url, [], None, monkeypatch)
    done = []
    connection.sign_in(conn, demo.url, "Robin", PASSWORD,
                       lambda r, e: done.append(e))
    run_until(lambda: done)
    assert done[0] is None and conn.signed_in
    assert keyring.lookup(keyring.TOKEN) == TOKEN
    again = connection.Connection(conn.store, watch=False)
    assert again.signed_in and again.account.user_name == "Robin"


def test_probe_reports_each_address(demo, monkeypatch):
    done = []
    router.probe_addresses(connection.probe_with(Client(USER_AGENT)), demo.url,
                           "http://127.0.0.1:9", lambda r, e: done.append((r, e)))
    run_until(lambda: done)
    answers, error = done[0]
    assert error is None
    assert answers[REMOTE]["ServerName"] == "Home Media"
    assert isinstance(answers[LOCAL], HttpError)


def test_proxy_forwards_ranges_through_mtls(mtls_demo, pki, trust, monkeypatch):
    http = Client(USER_AGENT)
    http.tls_database = trust
    http.certificate = tls.load((pki / "client.p12").read_bytes(), P12_PASSWORD)
    jellyfin = signed_in(mtls_demo.url, http)
    item = jellyfin.resume()[0]
    info = jellyfin.playback_info(item["Id"], 0)
    stream = playback.choose(item, info, "test", jellyfin.token)
    conn = _connection("", mtls_demo.url, monkeypatch=monkeypatch)
    conn.jellyfin = jellyfin
    proxy = MediaProxy(conn.forward)
    try:
        url = proxy.url(stream.path)
        assert "api_key" not in url and TOKEN not in url
        request = urllib.request.Request(url, headers={"Range": "bytes=256-511"})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == f"bytes 256-511/{len(mtls_demo.media)}"
            assert response.read() == mtls_demo.media[256:512]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url.replace(proxy.secret, "guess"), timeout=10)
    finally:
        proxy.stop()
    method, path, headers = mtls_demo.requests[-1]
    assert path.endswith("/stream") and f'Token="{TOKEN}"' in headers["Authorization"]

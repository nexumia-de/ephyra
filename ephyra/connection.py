"""The signed-in account and the route to the server: local address on a
home network, remote address elsewhere (docs/connection.md). The route
itself is phosh_toolkit.router.Router."""
import logging

from gi.repository import GObject
from phosh_toolkit import tasks, tls
from phosh_toolkit.proxy_login import CookieJar
from phosh_toolkit.http import NETWORK, HttpError
from phosh_toolkit.router import CONNECTING, OFFLINE, Router  # noqa: F401

from ephyra import keyring, settings
from ephyra.api import Jellyfin

log = logging.getLogger("ephyra.connection")


class Connection(Router):
    """state: "connecting", "local", "remote" or "offline"."""
    __gsignals__ = {
        # The server rejected the token: the UI shows the sign-in page.
        "signed-out": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, store=None, watch=True):
        super().__init__(watch=watch)
        self.store = store or settings.Store()
        self.account = self.store.load()
        self.jellyfin = Jellyfin(device_id=self.account.device_id)
        self.certificate_error = None
        if self.account.signed_in:
            self.jellyfin.token = keyring.lookup(keyring.TOKEN) or ""
            self.jellyfin.user_id = self.account.user_id
        self.load_certificate()
        # A reverse proxy's own login (docs/connection.md).
        self.proxy_cookies = CookieJar(keyring.KEYRING)
        self.jellyfin.http.cookies = self.proxy_cookies.load()

    # --- account -----------------------------------------------------

    @property
    def signed_in(self):
        return self.account.signed_in and bool(self.jellyfin.token)

    def load_certificate(self):
        self.certificate_error = None
        self.jellyfin.http.certificate = None
        if not self.account.certificate:
            return
        try:
            self.jellyfin.http.certificate = settings.certificates().load()
        except (OSError, tls.CertificateError) as e:
            self.certificate_error = str(e)
            log.warning("client certificate: %s", e)

    def save(self):
        self.store.save(self.account)

    def signed_in_as(self, result, info):
        """Store the answer of AuthenticateByName."""
        self.account.server_id = info["Id"]
        self.account.server_name = info.get("ServerName", "")
        self.account.user_id = result["User"]["Id"]
        self.account.user_name = result["User"].get("Name", "")
        keyring.store(keyring.TOKEN, result["AccessToken"])
        self.jellyfin.token = result["AccessToken"]
        self.jellyfin.user_id = self.account.user_id
        self.save()

    def sign_out(self, tell_server=True):
        if tell_server and self.jellyfin.token and self.jellyfin.base_url:
            tasks.run(self.jellyfin.sign_out)
        keyring.clear(keyring.TOKEN)
        self.jellyfin.token = ""
        self.account.user_id = ""
        self.save()

    # --- Router ------------------------------------------------------

    def probe(self, url, timeout):
        return probe_with(self.jellyfin.http)(url, timeout)

    def addresses(self):
        a = self.account
        return a.remote_url, a.local_url, a.home_networks

    def server_id(self):
        return self.account.server_id

    def resolved(self, kind, url, info):
        self.jellyfin.base_url = url
        if info.get("ServerName") and info["ServerName"] != self.account.server_name:
            self.account.server_name = info["ServerName"]
            self.save()

    def unauthorized(self):
        self.sign_out(tell_server=False)
        self.emit("signed-out")

    def call(self, fn, done, *args):
        """Router.call, logged with EPHYRA_DEBUG (the UI test's log shows
        which answer did not arrive, #21)."""
        name = getattr(fn, "__qualname__", repr(fn))
        log.debug("call %s (route %s)", name, self.state)

        def logged(result, error):
            log.debug("answer %s%s", name, f": {error}" if error else "")
            done(result, error)
        super().call(fn, logged, *args)

    def forward(self, path):
        """The media proxy's upstream for a server path: the current route
        with the token as header (phosh_toolkit.proxy)."""
        if not self.jellyfin.base_url:
            raise HttpError(NETWORK, "Not connected")
        return (self.jellyfin.http, self.jellyfin.base_url + path,
                {"Authorization": self.jellyfin.authorization()})


def probe_through(http, url, timeout):
    """The probe in the form phosh_toolkit.proxy_login wants."""
    return probe_with(http)(url, timeout)


def probe_with(http):
    """Ask /System/Info/Public (no token needed) through `http`."""
    def probe(url, timeout):
        info = Jellyfin(http=http).public_info(url, timeout=timeout)
        return info["Id"], info
    return probe


def sign_in(connection, url, user, password, done):
    """Authenticate at `url`; done(result, error) with result
    (auth answer, server info)."""
    jellyfin = Jellyfin(http=connection.jellyfin.http,
                        device_id=connection.account.device_id)

    def work():
        info = jellyfin.public_info(url)
        jellyfin.base_url = url
        return jellyfin.authenticate(user, password), info

    def finished(result, error):
        if error is None:
            connection.jellyfin.base_url = url
            connection.base_url = url
            connection.signed_in_as(*result)
        done(result, error)

    tasks.run(work, finished)

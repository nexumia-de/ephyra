"""The server account on disk: addresses, home networks, user and device
ids, playback quality. Secrets (access token, certificate password) are in
the keyring (ephyra/keyring.py), the client certificate is a private copy
in the data directory (phosh_toolkit.certificate). No GTK."""
import uuid
from dataclasses import dataclass, field

from phosh_toolkit.certificate import CertificateFile
from phosh_toolkit.settings import JsonStore, app_dir

from ephyra import keyring

VERSION = 1
# Maximum streaming bitrate in bit/s; 0 plays the original file when the
# phone can decode it (docs/playback.md).
QUALITIES = (
    (0, "Original"),
    (20_000_000, "20 Mbit/s"),
    (8_000_000, "8 Mbit/s"),
    (4_000_000, "4 Mbit/s"),
    (1_500_000, "1.5 Mbit/s"),
)

@dataclass
class Account:
    remote_url: str = ""
    local_url: str = ""
    home_networks: list = field(default_factory=list)
    certificate: bool = False
    server_id: str = ""
    server_name: str = ""
    user_id: str = ""
    user_name: str = ""
    device_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    quality_home: int = 0
    quality_away: int = 4_000_000
    style: str = "system"
    # Up-next countdown and the next episode at the end (docs/player-controls.md).
    auto_next: bool = True
    # Videos go on playing while the screen is off; off pauses them.
    play_screen_off: bool = False

    @property
    def signed_in(self):
        return bool(self.user_id and self.server_id)


def config_dir():
    return app_dir("config", "ephyra")


def data_dir():
    return app_dir("data", "ephyra")


def cache_dir():
    return app_dir("cache", "ephyra")


def certificate_path():
    """The private copy of the client certificate (PKCS #12 or PEM)."""
    return data_dir() / "client-certificate"


class Store(JsonStore):
    def __init__(self, path=None):
        super().__init__(path or config_dir() / "account.json", Account, VERSION)


def certificates():
    """The saved client certificate and its password in the keyring."""
    return CertificateFile(certificate_path(), keyring.KEYRING)

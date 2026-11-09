"""Ephyra: Jellyfin client for Phosh phones."""

try:
    from ephyra.config import APP_ID, BUILD_LABEL
except ImportError:  # run from the source tree, config.py is not built
    APP_ID = "de.nexumia.Ephyra"
    BUILD_LABEL = ""
VERSION = "0.2.0"
# The nightly app is built from every push to main
# (docs/release-channels.md).
NIGHTLY = APP_ID.endswith(".Devel")
NAME = "Home Cinema (Nightly)" if NIGHTLY else "Home Cinema"
# About dialog, e.g. "0.1.0 (main · 8534d2c)" for a nightly build.
VERSION_LABEL = f"{VERSION} ({BUILD_LABEL})" if BUILD_LABEL else VERSION
REPO_URL = "https://github.com/nexumia-de/ephyra"
# Voluntary support for development (phosh-toolkit docs/support.md).
SUPPORT_URL = "https://liberapay.com/suitably"
# Sent with every HTTP request.
USER_AGENT = f"Ephyra/{VERSION} (+{REPO_URL})"
# Client name in Jellyfin's Authorization header; the server shows it in
# its dashboard under devices and activity.
CLIENT_NAME = "Ephyra"

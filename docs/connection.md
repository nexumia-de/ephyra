---
type: Concept
title: Connection, home network and client certificates
description: How Ephyra picks the local address on a home Wi-Fi and the remote address elsewhere, checks it is the same server, presents a client certificate for mutual TLS, keeps the token in the keyring, and which errors it shows.
tags: [connection, network, mtls, tls, wifi, networkmanager, keyring, security]
resource: ../ephyra/connection.py
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
sources:
  - id: jf-auth
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Server.Implementations/Security/AuthorizationContext.cs
    title: Jellyfin server, AuthorizationContext (MediaBrowser header, Token)
  - id: jf-system
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/SystemController.cs
    title: Jellyfin server, SystemController (/System/Info/Public)
  - id: soup-cert
    resource: https://gnome.pages.gitlab.gnome.org/libsoup/libsoup-3.0/method.Message.set_tls_client_certificate.html
    title: libsoup 3, soup_message_set_tls_client_certificate
  - id: nm-dbus
    resource: https://networkmanager.dev/docs/api/latest/spec.html
    title: NetworkManager D-Bus API (ActiveConnections, AccessPoint.Ssid)
---

The route, the client certificate handling, the connection form, the
keyring and the media proxy are phosh-toolkit's `phosh_toolkit` package,
shared with Nauta; their general behaviour is described in
[shared connection and playback](../../phosh-toolkit/docs/shared-connection.md).
This file keeps what is Ephyra's: the Jellyfin probe and sign-in, the
account file and the secrets' names.

# The owner's setup

One Jellyfin server, reachable

- **at home** directly on the LAN, e.g. `http://192.168.1.10:8096`;
- **elsewhere** through a public URL behind a reverse proxy that
  requires a **client certificate** (mutual TLS).

# Route (`phosh_toolkit.route`, `phosh_toolkit.router`, `connection.py`)

The account stores a remote address, an optional local address and a
list of home Wi-Fi names (SSIDs). `route.candidates()` orders them:

| Situation | Tried in order |
|---|---|
| Connected to a listed home Wi-Fi | local, then remote |
| Other Wi-Fi or mobile data | remote only |
| No home list, or NetworkManager not reachable | local, then remote |
| Only one address set | that one |

Each candidate is asked for `/System/Info/Public` (no token
needed)[^jf-system]: 3 s timeout for the local address, 15 s for the
remote one. The first one that answers **with the server id stored at
sign-in** is used; another Jellyfin at the same LAN address never gets
the token. The window shows the result in the sidebar subtitle
("Home Media · Home network" / "Remote" / "Offline"), and an
`AdwBanner` with "Retry" when nothing answers.

The route is chosen again when `Gio.NetworkMonitor` reports a change
(debounced 1.5 s), and once after any request that fails with a
network error (`Connection.call` retries through the new route).

**Switching while the app runs** (owner's report, 2026-11-04: Wi-Fi gone,
the app stayed on the local address): since nexumia-de/phosh-toolkit#34
NetworkManager's own signals also trigger a new route, a change during a
running search searches again, and the window calls
`proxy.follow(connection)`, so a playing video moves to the new address
(GStreamer reconnects with a `Range`)
([toolkit](../../phosh-toolkit/docs/shared-connection.md#route-route-router)).

**SSID**: read from NetworkManager on the system bus
(`ActiveConnections` → `Type == 802-11-wireless` → `SpecificObject` →
`AccessPoint.Ssid`, falling back to the connection's `Id`)[^nm-dbus].
The Flatpak needs `--system-talk-name=org.freedesktop.NetworkManager`
for it. Without access (other distributions, desktop without NM) the
app tries the local address first everywhere, which the server id
check keeps safe.

Addresses are typed freely and normalized (`route.normalize`): without
a scheme they get `https://`, for the local address too (the owner's
rule, 2026-11-04); a typed `http://` or `https://` is kept, the trailing
slash goes. The field then shows the address as used. A local Jellyfin
on plain HTTP is entered as `http://192.168.1.10:8096`.

# Mutual TLS (`phosh_toolkit.tls`, `phosh_toolkit.http`, `phosh_toolkit.certificate`)

- The user picks a **PKCS #12** file (`.p12`/`.pfx`, with password) or a
  **PEM** file with certificate and unencrypted key. Ephyra keeps a
  private copy in `$XDG_DATA_HOME/ephyra/client-certificate` (mode 600)
  and the PKCS #12 password in the keyring.
- Loaded with `Gio.TlsCertificate.new_from_pkcs12` / `new_from_pem`;
  a wrong password is `G_TLS_ERROR_BAD_CERTIFICATE_PASSWORD`, shown on
  the password row.
- Every request sets it with `soup_message_set_tls_client_certificate`
  before sending[^soup-cert], so libsoup presents it when the server
  asks. It is also sent to the local address if that one asks.
- **Missing certificate**, recognised in three forms: GIO's
  `CERTIFICATE_REQUIRED`; with TLS 1.3 a received alert "Certificate is
  required" (the handshake completes before the server checks, verified
  with the tests' Python server); and nginx's HTTP 400 page "No required
  SSL certificate was sent". All become "The server asks for a client
  certificate" and mark the certificate row.
- The server certificate is checked against the system's CAs. Servers
  with a private CA are not supported yet (follow-up issue).

# Proxy login

Some reverse proxies have their own login in front of Jellyfin
(Pangolin's resource authentication, Authelia, Authentik, …). The owner's
proxy sets it for all resources: mutual TLS worked, then the proxy
answered `401 Unauthorized` (2026-11-04). The toolkit detects this and
shows the proxy's login page in a web view
([proxy login](../../phosh-toolkit/docs/shared-connection.md#proxy-login-proxy_login)):

- during setup, from the connection form;
- later, when the proxy's session runs out: the router's `proxy-login`
  signal opens the page from the window (`Window._on_proxy_login`), and
  the app is not signed out of Jellyfin.

The proxy's cookies are kept in the keyring (kind `proxy-cookies`) and
loaded by `Connection`; they go only to the server's address, also for
playback through the media proxy.

Since phosh-toolkit `v0.4.0` the web view gives the client certificate
only to the server's host and to `certificate_hosts_extra`; any other
host that asks for it gets none and its request is cancelled. A login
whose identity provider is on another host behind the same mutual TLS
(Pangolin's or Authelia's page on `auth.example.org`, Jellyfin on
`media.example.org`) needs that host listed: Preferences → Connection →
**Proxy Login** → *Other Hosts for the Certificate* (comma- or
space-separated; addresses are reduced to their host, lower case). It is
kept in the account file as `certificate_hosts` and passed by
`Window._on_proxy_login` (#33; tests `test_parse_hosts`,
`test_proxy_login_opens_the_login_page`). The connection form's own login
during setup does not take extra hosts yet: toolkit `ConnectionForm`
passes none to `make_page`, so on the first connect such an identity
provider gets no certificate (nexumia-de/phosh-toolkit#52).

# Sign-in and secrets

`POST /Users/AuthenticateByName` with the `Authorization: MediaBrowser
Client="Ephyra", Device=…, DeviceId=…, Version=…` header[^jf-auth]; the
token comes back as `AccessToken` and is sent as `Token="…"` in the same
header from then on, never in URLs. Token and certificate password are
stored with libsecret (schema `de.nexumia.Ephyra`, attribute `kind`); in
the Flatpak libsecret uses the Secret portal. A `401` from the server
signs out and shows the setup page.

The account file `$XDG_CONFIG_HOME/ephyra/account.json` (version 1)
holds addresses, home networks, server and user ids and names, the
device id and the quality settings. A broken file is kept as `.bad`.

# Security notes

- At home the local address is usually plain HTTP: the token and the
  password at sign-in cross the home Wi-Fi unencrypted. Use an `https`
  local address if that matters.
- A Wi-Fi with the same name elsewhere makes Ephyra try the local
  address there; a stranger's server at that address fails the server
  id check, but anyone who fakes the public server info (no token
  needed) could still receive the token. Prefer an `https` local
  address, or leave the home list empty to always use the remote URL.

# Verified (2026-11-03, cloud container, Ubuntu 24.04, libsoup 3.4.4, GLib 2.80)

- `tests/test_connection.py`: the client against `ephyra/demo.py` over
  real mutual TLS (CA, server and client certificates made with
  `openssl`): refused without the certificate (`certificate-required`),
  works with the PKCS #12 file; PEM and PKCS #12 loading, wrong password,
  missing key; the route on a home network, elsewhere, with the local
  server down, and with a different server at the local address.
- `tests/test_ui.py`: the setup page marks the certificate row without
  a certificate, then signs in with it.
- Not yet on the phone: NetworkManager access from the Flatpak and the
  owner's real reverse proxy (issue in milestone M1).

[^jf-auth]: Jellyfin server, AuthorizationContext
[^jf-system]: Jellyfin server, SystemController
[^soup-cert]: libsoup 3, soup_message_set_tls_client_certificate
[^nm-dbus]: NetworkManager D-Bus API

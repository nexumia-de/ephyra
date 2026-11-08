@../phosh-toolkit/agents/core.md
@../phosh-toolkit/agents/gtk-app.md

# Ephyra

Jellyfin client for Phosh phones (and the desktop), in the look of
Jellyfin's own apps. Exceptions to the shared rules are below.

## Language

- Reply in English unless the owner asks for another language; then keep
  that language until told otherwise.

## Design: Jellyfin's look

- The owner wants Ephyra to look like Jellyfin's apps. This replaces the
  toolkit's stock look for this app:
  [decision](docs/decisions/jellyfin-style.md).
- Follow [docs/design.md](docs/design.md): Jellyfin's blue as Ephyra's
  accent through libadwaita's variables, light/dark from the system or
  the Style preference, poster cards with played
  badges and progress, backdrops on detail pages. Everything else of the
  toolkit's design and adaptive rules still applies (360×720, no
  horizontal scrolling, style classes, symbolic icons, tooltips).
- Never use Jellyfin's logo, wordmark or icons, and do not copy code or
  assets from Jellyfin's repositories (GPL-2.0). Colour values and API
  facts may be used.

## App rules

- App id: `de.nexumia.Ephyra`. Visible name: **Home Cinema** (chosen by
  the owner on 2026-11-06, [decision](docs/decisions/app-name.md)); the
  code name Ephyra stays for the repository, app id, package and docs.
- Plan: [milestones](https://github.com/nexumia-de/ephyra/milestones); goals in [docs/roadmap.md](docs/roadmap.md).
- Connection: local address on the owner's home Wi-Fi, remote address
  elsewhere, the remote one behind mutual TLS. Read
  [docs/connection.md](docs/connection.md) before touching
  `connection.py` or `setup.py`. The HTTP client, route, client
  certificates, connection form, media proxy and player are shared with
  other apps in phosh-toolkit's `phosh_toolkit` package
  ([shared connection](../phosh-toolkit/docs/shared-connection.md));
  change them there. Never put the access token into a URL, a log line
  or a file outside the keyring.
- Playback goes through the local media proxy:
  [docs/playback.md](docs/playback.md).
- Jellyfin API facts come from the server source
  (`github.com/jellyfin/jellyfin`, `Jellyfin.Api/Controllers`); the API
  hosts are blocked in the cloud environment
  ([dev environment](docs/dev-environment.md)). Ephyra needs server 10.9
  or newer.
- Screenshots and UI tests use the demo library (`EPHYRA_DEMO`,
  `ephyra/demo.py`, `tests/data/demo`), never a real server.
- Run PyGObject code with `/usr/bin/python3.12` on the cloud host; the
  default `python3` has no `gi`.

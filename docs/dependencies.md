---
type: Reference
title: Bundled dependencies
description: Ephyra bundles phosh-toolkit's shared package and the Noto Sans CJK font; everything else comes from the GNOME runtime.
tags: [dependencies, licensing, flatpak]
generated: { by: claude-code/2.1.317, at: 2026-11-04T20:30:00Z }
---

# Rules

The shared rules are in
[../../phosh-toolkit/docs/licensing.md](../../phosh-toolkit/docs/licensing.md).
CI fails if a module of `de.nexumia.Ephyra.yml` is missing here or
installs no licence files.

# Modules

| Module | Version | Licence | Licence files |
|---|---|---|---|
| `phosh-toolkit` | tag `v0.5.0` (commit `e5cccb6`) | GPL-3.0-or-later (own code, same author) | `LICENSE` → `/app/share/licenses/<app id>/phosh-toolkit/` |
| `noto-cjk` | tag `Sans2.004`, `Sans/Variable/OTC/NotoSansCJK-VF.otf.ttc` | OFL-1.1 (read from the tag's `LICENSE`) | `LICENSE` → `/app/share/licenses/<app id>/noto-cjk/` |

Only `lib/phosh_toolkit/` is installed: the shared connection and
playback code ([shared connection](../../phosh-toolkit/docs/shared-connection.md)).
GPL-3.0-or-later code may be combined with Ephyra's AGPL-3.0-or-later
(section 13 of both licences).

# Fonts

The GNOME 51 runtime ships Adwaita Sans, Cantarell, DejaVu, Liberation,
GNU FreeFont, Carlito, Caladea, TeX Gyre and Noto Color Emoji, but **no
font with Japanese, Chinese or Korean glyphs** (checked in
`org.gnome.Platform//51`, `files/share/fonts/`). Inside the Flatpak,
fontconfig also reads the host's `/usr/share/fonts` (as
`/run/host/fonts`), so CJK text showed only where the host had such a
font installed; on the owner's phone Japanese text could not be shown.

Ephyra therefore bundles Noto Sans CJK as the variable OpenType
collection (one file, about 33 MB, every weight; faces JP, KR, SC, TC
and HK, JP first). The runtime's fontconfig reads `/app/share/fonts`,
so Pango falls back to it for any CJK character the UI font lacks; no
CSS or code change is needed. The Japanese-only subset (about 8 MB)
was not chosen because Jellyfin libraries also carry Chinese and Korean
titles. OFL-1.1 allows bundling the font with any software; it may not
be sold on its own and keeps its name.

# From the runtime (not bundled)

`org.gnome.Platform//51` provides everything Ephyra imports: Python 3
and PyGObject, GTK 4 with its GStreamer media backend, libadwaita,
libsoup 3 with glib-networking (GnuTLS) for mutual TLS, libsecret,
GStreamer and its plugins. Flathub distributes the runtime under its own
terms.

# Not used

No code or assets from Jellyfin's repositories (GPL-2.0) are in Ephyra.
API facts were read from the server source; the accent colour value
`#00a4dc` is taken from jellyfin-web's palette (a fact, not code).

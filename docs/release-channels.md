---
type: Playbook
title: Release channels
description: Ephyra (stable, from tags v<version>) and Ephyra (Nightly) (de.nexumia.Ephyra.Devel, from every push to main), the nightly build options, automated releases with changelog fragments, and store screenshots from the demo library.
tags: [release, nightly, flatpak, ci, meson, changelog, screenshots]
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
---

# Channels

| Channel | App | App id | Fed by |
|---|---|---|---|
| Stable | Ephyra | `de.nexumia.Ephyra` | tags `v0.1.0`, … |
| Nightly | Ephyra (Nightly) | `de.nexumia.Ephyra.Devel` | every push to `main` |

Both come from the shared repository `https://flatpak.nexumia.de/` once
`nexumia-de/ephyra` is listed in phosh-apps' `apps.txt` (after the first
tag). Mechanics: the toolkit's
[Flatpak workflow](../../phosh-toolkit/docs/flatpak-workflow.md#release-channels)
and [releases](../../phosh-toolkit/docs/releases.md).

# Nightly variant

`-Dprofile=development` gives the app id `de.nexumia.Ephyra.Devel`
(`ephyra/config.py`, generated) and derives desktop file and metainfo
from `data/` with `sed` in `meson.build` (new id, name "Ephyra
(Nightly)"); `-Dbuild_label` shows the commit in the About dialog. The
window gets the striped `devel` header bar.

# Release

Every pull request users notice adds a fragment to `changelog.d/`;
the weekly release pull request writes them into the metainfo. The About
dialog shows the newest `<release>` as "What's New", read from the
installed metainfo by `phosh_toolkit.release_notes` (from a source tree
it reads `data/de.nexumia.Ephyra.metainfo.xml`). The first
release, 0.1.0, is in the metainfo already: push the tag `v0.1.0` after
merging the first pull request, then add the repository to phosh-apps.

# Screenshots

`release.toml` lists them; CI takes each at 360×720 and 1000×700,
light and dark, from the built Flatpak with `EPHYRA_DEMO` pointing at
`tests/data/demo`: the app starts `ephyra/demo.py` on 127.0.0.1 and
is signed in to it, with nothing stored. No network is used.

| Shot | State | Actions |
|---|---|---|
| `home` | Home | – |
| `movies` | Movies library | `app.show-view(1)` (Ctrl+2) |

The demo library (invented titles, images drawn by
`build-aux/make-demo-data.py`, CC0) is regenerated with
`/usr/bin/python3.12 build-aux/make-demo-data.py`.

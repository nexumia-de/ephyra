---
okf_version: "0.2"
---

# Ephyra knowledge bundle

[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF v0.2) bundle of this app. Shared Phosh knowledge lives in
[../../phosh-toolkit/docs/index.md](../../phosh-toolkit/docs/index.md).
Change history is in [log.md](log.md).

# Plan

* [Roadmap](roadmap.md) - Goals and exit criteria of the milestones; the work items are GitHub issues.

# Design

* [Jellyfin look](design.md) - Jellyfin's blue accent, light/dark from the system or the Style preference, poster cards, backdrops on libadwaita, with a review checklist.
* [Connection](connection.md) - Local address on the home Wi-Fi, remote address elsewhere, server id check, client certificates for mutual TLS, token in the keyring.
* [Playback](playback.md) - Device profile, direct play or HLS transcoding, stopping every stream on the server, the local media proxy, resume and progress reports.
* [Player controls](player-controls.md) - Double tap on the sides to seek, big buttons over the video, end time, Skip Intro / Credits, the next episode with a countdown (autoplay can be turned off), pausing when the screen turns off, the audio and subtitle sheet, rotate to landscape inside the app.

# Development

* [Bundled dependencies](dependencies.md) - phosh-toolkit's shared package and the Noto Sans CJK font (the runtime has no CJK font); everything else comes from the GNOME runtime.
* [Release channels](release-channels.md) - Stable from tags, nightly from main, releases and store screenshots from the demo library.
* [Development environment](dev-environment.md) - Blocked hosts, host packages, how to run, test and screenshot.

# Decision records

* [Decisions](decisions/index.md) - Name, licence, Python, Jellyfin look, local media proxy, playbin, rotating in the app, subtitles in the app, no automatic burn-in.

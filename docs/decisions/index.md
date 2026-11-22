# Decision records

* [App name Ephyra](app-name.md) - Named after the young stage of a jellyfish; app id de.nexumia.Ephyra.
* [AGPL-3.0 license](license.md) - Like Cirro; no Jellyfin code copied in.
* [Python and PyGObject](python-pygobject.md) - Same stack as Cirro, everything from the GNOME runtime.
* [Jellyfin look](jellyfin-style.md) - Jellyfin's style instead of the toolkit's stock look, at the owner's request.
* [Local media proxy](media-proxy.md) - GStreamer plays a 127.0.0.1 URL; the proxy adds token and client certificate.
* [playbin instead of GtkMediaFile](playbin.md) - GTK 4.20's media file reads http:// through GIO, which the Flatpak can't; playbin3 with gtk4paintablesink plays the proxy URL.
* [Draw text subtitles in the app](subtitles-in-app.md) - SRT from the server drawn over the video; picture subtitles burned in; GStreamer plays no subtitle stream.
* [Rotate the player inside the app](rotate-in-app.md) - A GSK transform turns the player; no DisplayConfig permission, nothing global left behind.
* [No automatic burn-in](no-automatic-burn-in.md) - A default picture subtitle the server would burn in is left off; picture subtitles stay selectable, marked as converted on the server.
* [Private CA in the system trust store](private-ca-system-trust.md) - A server certificate from the owner's own CA is trusted through the phone's trust store, which the Flatpak reads through p11-kit; no CA file in Ephyra.
* [No colours from the artwork](no-artwork-tint.md) - Detail pages keep Jellyfin's blue and libadwaita's surfaces; tones picked from posters fail contrast and would make the accent meaningless.

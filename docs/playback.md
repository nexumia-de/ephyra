---
type: Concept
title: Playback
description: How Ephyra asks the server what to play (device profile, direct play or HLS transcoding), plays it with GTK's GStreamer backend through a local proxy that adds the token and the client certificate, resumes, reports progress, and stops every stream on the server again.
tags: [playback, gstreamer, hls, transcoding, proxy, codecs, audio, subtitles, server-load]
resource: ../ephyra/player.py
generated: { by: claude-code/2.1.318, at: 2026-11-04T22:00:00Z }
sources:
  - id: jf-mediainfo
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/MediaInfoController.cs
    title: Jellyfin server, MediaInfoController (POST /Items/{id}/PlaybackInfo)
  - id: jf-playstate
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/PlaystateController.cs
    title: Jellyfin server, PlaystateController (/Sessions/Playing, Progress, Stopped)
  - id: jf-profile
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/DeviceProfile.cs
    title: Jellyfin server, DeviceProfile, DirectPlayProfile, TranscodingProfile
  - id: jf-streambuilder
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/StreamBuilder.cs
    title: Jellyfin server, StreamBuilder.GetSubtitleProfile (Embed, External, Encode)
  - id: jf-streaminfo
    resource: https://github.com/jellyfin/jellyfin/blob/master/MediaBrowser.Model/Dlna/StreamInfo.cs
    title: Jellyfin server, StreamInfo (subtitle DeliveryUrl, start position)
  - id: jf-mediainfohelper
    resource: https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Helpers/MediaInfoHelper.cs
    title: Jellyfin server, MediaInfoHelper (DefaultAudioStreamIndex, DefaultSubtitleStreamIndex, DeliveryMethod per stream)
  - id: jf-hlssegment
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/Jellyfin.Api/Controllers/HlsSegmentController.cs
    title: Jellyfin server, HlsSegmentController.StopEncodingProcess (DELETE /Videos/ActiveEncodings)
  - id: jf-transcodemanager
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/MediaBrowser.MediaEncoding/Transcoding/TranscodeManager.cs
    title: Jellyfin server, TranscodeManager (KillTranscodingJobs, PingTimer, OnTranscodeEndRequest)
  - id: jf-dynamichls
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/Jellyfin.Api/Controllers/DynamicHlsController.cs
    title: Jellyfin server, DynamicHlsController (ffmpeg started at the first segment request)
  - id: jf-sessionmanager
    resource: https://github.com/jellyfin/jellyfin/blob/06695fb4942c15c7463c2dc644440d988951ed17/Emby.Server.Implementations/Session/SessionManager.cs
    title: Jellyfin server, SessionManager.OnPlaybackStopped (Failed leaves the user data alone)
---

# What to play (`playback.py`)

`POST /Items/{id}/PlaybackInfo`[^jf-mediainfo] with a device profile[^jf-profile]:

- **Direct play**: video in mp4/m4v/mkv/webm/mov with H.264, HEVC, VP8,
  VP9 or AV1 and AAC, MP3, Opus, Vorbis, FLAC, AC-3, E-AC-3, ALAC,
  TrueHD or DTS; audio in mp3/flac/ogg/opus/m4a/aac/wav/webm. TrueHD and
  DTS make Blu-ray remuxes play directly (see the audio codecs below).
- **Transcoding**: HLS (MPEG-TS, H.264 + AAC, stereo) for video, MP3
  for audio.
- **Bitrate**: `MaxStreamingBitrate` from the preferences, separately
  for home (default *Original*) and away (default *4 Mbit/s*), so a
  movie plays untouched on the home Wi-Fi and is converted on mobile
  data.
- **Tracks**: `AudioStreamIndex` and `SubtitleStreamIndex` are left out
  at first, so the server picks them from the user's language and
  subtitle settings; the answer names its pick in the media source's
  `DefaultAudioStreamIndex` and `DefaultSubtitleStreamIndex`[^jf-mediainfohelper].
  If that subtitle would be burned in (method `Encode`), Ephyra asks
  once more with `SubtitleStreamIndex: -1` before playing
  (`sessions.fetch_stream`, `playback.burns_in_default`); decision:
  [no automatic burn-in](decisions/no-automatic-burn-in.md). The
  player's **Playback Settings** sheet asks again with the user's
  choice (subtitle `-1` is off).
- **MediaSourceId with every track choice**: the server uses
  `AudioStreamIndex` and `SubtitleStreamIndex` only when the request
  names the media source they belong to (`MediaInfoHelper.SetDeviceSpecificData`;
  `MediaInfoController` passes `mediaSourceId ?? ""`)[^jf-mediainfohelper].
  Without it a re-request got the server's default back, so a picture
  subtitle turned on or off, or audio switched in a converted stream,
  jumped back to the previous choice (owner, 2026-11-04). `playback_info`
  sends the stream's `MediaSourceId` (the item id if none is known)
  whenever it sends an index; the demo server ignores indexes without
  it, as Jellyfin does.
- **Subtitle profile**: `{"Format": "srt", "Method": "External"}` only.
  The server then marks every text subtitle `External` with a
  `DeliveryUrl` `/Videos/{id}/{source}/Subtitles/{index}/0/Stream.srt`,
  converting ASS, WebVTT and embedded ones to SRT; picture subtitles
  (PGS, DVD, DVB) match no profile and fall back to `Encode`, burned
  into a converted stream[^jf-streambuilder]. The `0` is the start
  position: 0 for direct play and for HLS, which keeps timestamps[^jf-streaminfo].

# Audio and subtitles

- **Audio, direct play**: the file holds every track. `ephyra/media.py`
  answers playbin3's stream collection with a `select-streams` event: the
  first video and the chosen audio track, in file order (Jellyfin's
  audio indexes in the same order, external audio files left out).
  Switching sends the event again, without a restart.
- **Audio, converted stream**: HLS carries one audio track, so the
  player asks the server again and goes on from the same position.
- **Text subtitles** are drawn by Ephyra: the SRT is fetched with the
  token as a header (`Jellyfin.text`), parsed into cues
  (`ephyra/subtitles.py`; `<b>`, `<i>`, `<u>` kept, other tags dropped)
  and shown in a label on the `osd` background, updated every 100 ms
  from the pipeline's position, above the controls while they show.
  Switching or turning them off needs no restart and works the same
  for converted streams. Decision: [subtitles in the app](decisions/subtitles-in-app.md).
- **Picture subtitles** (`Encode`): never on by themselves. The sheet
  lists them as "… (converted on the server)"; choosing one, or leaving
  one, asks the server again, which converts the video with the subtitle
  burned in.
- playbin3 selects the first embedded subtitle by itself; the
  `select-streams` answer never includes a text stream, so embedded
  subtitles never show twice.
- Progress reports carry `AudioStreamIndex` and `SubtitleStreamIndex`.

`playback.choose()` takes the first media source: direct play or direct
stream → `/Videos/{id}/stream?static=true&mediaSourceId=…&tag=…`
(`/Audio/…` for audio); otherwise the server's `TranscodingUrl`, with
the `ApiKey`/`api_key` the server puts into it removed (the proxy sends
the token as a header). If the phone can't decode the original, the
player's error page offers **Convert on the Server**, which asks again
with direct play and direct stream disabled and `AllowVideoStreamCopy`
/ `AllowAudioStreamCopy` false, so the server re-encodes both streams
instead of copying a codec the phone failed on into HLS.

**Server side** (read in `Jellyfin.Api/Helpers/MediaInfoHelper.cs` and
`Emby.Server.Implementations/Library/MediaSourceManager.cs`, 10.11):
`SupportsTranscoding` comes from the user's policy
`EnableVideoPlaybackTranscoding` ("Allow video playback that requires
transcoding" in the dashboard), `SupportsDirectStream` from
`EnablePlaybackRemuxing`. Without the first, a file the phone can't play
has no `TranscodingUrl`; Ephyra then says which setting to turn on
instead of a generic error. `EnableDirectPlay: false` works because the
helper clears the source's `SupportsDirectPlay` before the stream
builder checks it. `EPHYRA_DEBUG=1` logs the server's decision
(`PlaybackInfo: DirectPlay …, Transcoding …, TranscodingUrl …`).

**Error page.** "Can't Play This" says in one sentence what to do and
shows a small, selectable details line for reports, e.g. `DirectPlay ·
mkv · hevc · eac3 · direct play yes · convert allowed · converted stream
none · GStreamer: No decoder available for type 'video/x-h265'.`
(`playback.describe`, `player.gst_reason`). The same line is logged as a
warning.

# Stopping streams on the server (`sessions.py`)

Seen on the owner's server (2026-11-04): four `jellyfin-ffmpeg` jobs
for the same movie (1080p H.264 remux, TrueHD 7.1, a default PGS
subtitle), each with its own output in `/cache/transcodes`, started
within about 70 s and all still running after 8 minutes, until the LXC
(4 cores, 8 GB) ran out of memory. Each re-encoded the video with
libx264 only to burn in the PGS subtitle. That they came from Ephyra is
inferred from its code, not from the Jellyfin log: the player reported
`Stopped` only after GStreamer had the stream `prepared`, so a stream
left while loading, replaced by a reload or by Convert on the Server
before it played, was never stopped, and every new PlaybackInfo brings
a new `PlaySessionId` and so a new ffmpeg.

What the server does (read at commit `06695fb`, 2026-11-04):

- `POST /Sessions/Playing/Stopped` with a `PlaySessionId` calls
  `KillTranscodingJobs(deviceId, playSessionId)`[^jf-playstate]; with a
  session id given, it kills every job of that session, whatever the
  device id[^jf-transcodemanager]. So `Stopped` alone kills the job.
- `DELETE /Videos/ActiveEncodings?deviceId=…&playSessionId=…` (both
  required) calls the same `KillTranscodingJobs`[^jf-hlssegment], without
  the session bookkeeping.
- PlaybackInfo starts no ffmpeg; the dynamic HLS controller starts it at
  the first segment request[^jf-dynamichls].
- HLS jobs have a kill timer (60 s after the last request), but it is
  only started in `OnTranscodeEndRequest`, when a segment request
  finished[^jf-transcodemanager]. A new job starts with one active
  request; if that first segment request is given up while ffmpeg starts
  (the player was closed), the wait throws on cancellation and the end
  is never counted, so the timer never starts and ffmpeg runs to the end
  of the file[^jf-dynamichls]. Only an explicit stop ends it.
- `Stopped` with `Failed: true` leaves the user's resume position and
  played state alone[^jf-sessionmanager]; without it, a position of 0
  would overwrite the resume point.

What Ephyra does:

- Every stream the player chose is stopped on the server when it is
  left: page closed, reload (other audio in a converted stream, picture
  subtitle on or off), Convert on the Server, and the error page (right
  when GStreamer fails, not only when the page is left). Also before
  `prepared`: then with `Failed: true` and the start position.
- `Stopped` with the stream's `PlaySessionId`; for a converted stream
  also `DELETE /Videos/ActiveEncodings` with the device id and the
  `PlaySessionId`. Errors of one call don't keep the other from going
  out.
- At most one stream per player: a replaced stream is stopped in the
  same worker task, before PlaybackInfo is asked again.
- Only the newest request counts: an answer that arrives after the page
  closed or after a newer request is stopped at once, never played.
- While a converted stream starts, the player shows a spinner and
  "Converting on the server…" instead of the play buttons, so nobody
  taps again because it seems stuck.

# Local media proxy (`phosh_toolkit.proxy`)

GTK plays media with GStreamer (`GtkMediaFile`). GStreamer's HTTP
source and its HLS downloader can't present a client certificate, and
the token must not go into URLs. So the player opens
`http://127.0.0.1:<port>/<secret>/<server path>`:

- a `ThreadingHTTPServer` on 127.0.0.1, random port, a random 32-byte
  path secret (other local programs can't use it);
- each request is forwarded to the **current** route's base URL
  (`Connection.forward`) with the `Authorization` header and the client certificate (libsoup, one
  session per thread), `Accept-Encoding: identity` so lengths stay
  right;
- `Range`/`If-Range` go up, `Content-Type`, `Content-Length`,
  `Content-Range`, `Accept-Ranges` come back, the body is streamed in
  64 KiB chunks; seeking works. Without a length (live transcode) the
  connection closes at the end of the body.
- HLS playlists from Jellyfin use relative URLs, so segments go through
  the proxy too.

# Player (`player.py`, `phosh_toolkit.media`)

GStreamer's `playbin3` (`phosh_toolkit.media.Media`) plays the proxy URL;
video goes to `gtk4paintablesink` (inside `glsinkbin` when it has a GL
context) and its paintable into a `Gtk.Picture`; audio shows the album
cover instead. `Media` offers the part of the `GtkMediaStream` API the
player uses (playing, prepared, ended, timestamp, duration, seekable,
error; play, pause, seek, stop).

**Why not `Gtk.MediaFile`:** in GTK 4.20 (GNOME 51) its GStreamer backend
reads the URI through GIO (`giostreamsrc`). Inside the Flatpak GIO can't
open `http://` (no gvfs), so nothing played, direct or converted: the
phone logged `gtk_gst_media_file_source_setup_cb: assertion 'stream !=
NULL' failed` and `gio_base_src: No input stream provided by subclass`,
then "Failed to pause" (2026-11-04). `playbin3` opens the URL itself
(`souphttpsrc`, `hlsdemux2`). Decision:
[playbin instead of GtkMediaFile](decisions/playbin.md).

Two GStreamer details found while testing: the bus delivered only the
`NULL → READY` state change of `playbin3` with `hlsdemux2` (Python
wrappers of messages from streaming threads don't compare equal to the
pipeline either), so `Media` reads the pipeline state directly every
250 ms; and pausing on `BUFFERING` messages left the pipeline stuck after
`hlsdemux2`'s start-up buffering, so `Media` doesn't.

Resume: after `prepared` it seeks to the stored position. Reports to the
server[^jf-playstate]: `/Sessions/Playing` when prepared, `/Progress`
every 10 s and on play/pause, `/Stopped` whenever a stream is left
(above);
afterwards the detail and home pages reload to show the new position.
While playing, the app inhibits idle and suspend. Taps, double taps,
keys and rotating: [player controls](player-controls.md).

**GStreamer in the phone's runtime** (`gst-inspect-1.0` inside
`de.nexumia.Ephyra.Devel`, GNOME 51 with the `codecs-extra` 26.08
extension, 2026-11-04): `hlsdemux`, `hlsdemux2`, `avdec_h264`,
`avdec_aac`, `avdec_flac`, `gtk4paintablesink`, `glsinkbin`.

**Audio codecs for Blu-ray remuxes** (`gst-inspect-1.0` of
`org.gnome.Platform//51`, GStreamer 1.28.6, with and without
`org.freedesktop.Platform.codecs-extra//26.08-extra`, run with bwrap in
the cloud container on x86_64, 2026-11-04): `avdec_truehd`, `avdec_mlp`
and `avdec_dca` (DTS) are in the GNOME runtime's own libav, with or
without codecs-extra; `avdec_eac3` and `avdec_h264` only with it.
Jellyfin names the codecs `truehd` and `dts`; DTS-HD (MA, HRA) is `dts`
too, with the variant only in the stream's profile (ffprobe's names,
`ProbeResultNormalizer`, `BdInfoExaminer`), and `avdec_dca` decodes its
extensions. So `truehd` and `dts` are in the direct-play audio codecs.
Open: the same check on the phone (aarch64), and whether decoding
TrueHD 7.1 costs much battery.

# Verified (2026-11-04, owner's phone host, GStreamer 1.28.7)

- Audio and subtitles, headless under phoc: `tests/test_media.py` plays
  `tests/data/media/tracks.mkv` (English and German audio, an embedded
  subtitle) with the German track and no subtitle, then switches to
  English without a restart; the UI test chooses German audio and an
  SRT subtitle from the demo server, the label shows it, "Off" hides it.
- A subtitle file through playbin3's `suburi` was tried first: the
  pipeline then often ignored later `select-streams` events (decodebin3
  "Still have streams to activate"; audio switched in 2 of 8 runs
  without a video sink, 5 of 6 with one; 12 of 12 without the file).
- 360×720, turned, and 1000×700 screenshots of the sheet and the
  subtitles over a colour-bar clip.

# Verified (2026-11-04, cloud container, GStreamer 1.24)

- `tests/test_media.py`: a VP8/Vorbis clip through the demo server and
  the proxy plays, pauses, seeks and ends; undecodable data is an error.
- Locally (not in CI, needs `hlsdemux2` and `openh264enc`): a
  Jellyfin-shaped HLS stream (master → main playlist → `hls1/main/N.ts`,
  H.264 + AAC, with `Content-Length` and chunked) through the proxy plays,
  and seeking to 7 s plays to the end.
- Not testable here: the picture through `gtk4paintablesink` (not
  packaged for Ubuntu 24.04); checked on the phone.

# Verified (2026-11-03)

- In the cloud container (GTK 4.14, GStreamer 1.24): a 10 s VP8/Vorbis
  WebM served by the demo server plays through the proxy at 360×720;
  the position and the controls update.
- `tests/test_connection.py`: a range request through the proxy over
  mutual TLS returns `206` with the right bytes and `Content-Range`; the
  token is not in the URL; a wrong path secret gets `404`.
- `tests/test_ui.py`: a file the phone can't decode shows "Can't Play
  This" with "Convert on the Server".

# Verified (2026-11-04, cloud container, stopping streams)

- `tests/test_sessions.py` against the demo server, which records
  `Stopped` and `DELETE /Videos/ActiveEncodings`: a converted stream
  left before `prepared` gets both (with `Failed`), direct play only
  `Stopped`; a replaced stream is stopped before the next PlaybackInfo;
  late answers (after close, or to an older request) are stopped; a
  default PGS subtitle leads to a second request with subtitle `-1` and
  direct play, a chosen one is burned in, a default SRT stays.
- `tests/test_ui.py::test_player_never_leaves_a_transcode_running`
  drives the real player: left while the converted stream's playlist
  request hangs, closed before the server answered, reload on an audio
  switch, the error page and Convert on the Server; every PlaySessionId
  ends with a stop, only one stream at a time. With the old
  `player.py` the first step already fails.
- Screenshots of "Converting on the server…" at 360×720 and 1000×700,
  and of the sheet with a marked PGS subtitle.

# Open, on the phone

- Which codecs the GNOME 51 runtime's GStreamer decodes on the phone,
  and whether H.264/HEVC are hardware-decoded; this decides the right
  default for *Original*. Issue in milestone M1.
- Battery and CPU while playing a 1080p file.

[^jf-mediainfo]: Jellyfin server, MediaInfoController
[^jf-playstate]: Jellyfin server, PlaystateController
[^jf-profile]: Jellyfin server, DeviceProfile
[^jf-streambuilder]: Jellyfin server, StreamBuilder
[^jf-streaminfo]: Jellyfin server, StreamInfo
[^jf-mediainfohelper]: Jellyfin server, MediaInfoHelper
[^jf-hlssegment]: Jellyfin server, HlsSegmentController
[^jf-transcodemanager]: Jellyfin server, TranscodeManager
[^jf-dynamichls]: Jellyfin server, DynamicHlsController
[^jf-sessionmanager]: Jellyfin server, SessionManager

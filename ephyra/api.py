"""The Jellyfin REST API (server 10.9 or newer), blocking calls meant for
worker threads; see phosh_toolkit.tasks for running them from the UI.
No GTK."""
import json
import socket
from urllib.parse import quote, urlencode

from phosh_toolkit.http import Client, HttpError, SERVER  # noqa: F401

from ephyra import CLIENT_NAME, USER_AGENT, VERSION

TICKS_PER_SECOND = 10_000_000
# Item fields the views need besides the defaults.
FIELDS = "Overview,PrimaryImageAspectRatio,Genres,ProductionYear,ChildCount"


def _quote(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


class Jellyfin:
    def __init__(self, http=None, device_id="", device_name=None):
        self.http = http or Client(USER_AGENT)
        self.device_id = device_id
        self.device_name = device_name or socket.gethostname() or "Phosh"
        self.base_url = ""      # set by Connection for the current route
        self.token = ""
        self.user_id = ""

    # --- plumbing -----------------------------------------------------

    def authorization(self):
        parts = [f'Client="{CLIENT_NAME}"',
                 f'Device="{_quote(self.device_name)}"',
                 f'DeviceId="{_quote(self.device_id)}"',
                 f'Version="{VERSION}"']
        if self.token:
            parts.append(f'Token="{_quote(self.token)}"')
        return "MediaBrowser " + ", ".join(parts)

    def url(self, path, base=None, **query):
        query = {k: v for k, v in query.items() if v is not None and v != ""}
        for k, v in query.items():
            if isinstance(v, bool):
                query[k] = "true" if v else "false"
        url = (base or self.base_url) + path
        return url + ("?" + urlencode(query) if query else "")

    def get(self, path, base=None, timeout=None, **query):
        response = self.http.request(
            "GET", self.url(path, base, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"}, timeout=timeout)
        return _json(response.body)

    def text(self, path):
        """A text file from the server, e.g. a subtitle as SRT."""
        response = self.http.request(
            "GET", self.url(path), {"Authorization": self.authorization()})
        return response.body.decode("utf-8-sig", errors="replace")

    def post(self, path, payload=None, **query):
        body = json.dumps(payload).encode() if payload is not None else b""
        response = self.http.request(
            "POST", self.url(path, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"}, body=body)
        return _json(response.body)

    def delete(self, path, **query):
        response = self.http.request(
            "DELETE", self.url(path, **query),
            {"Authorization": self.authorization(),
             "Accept": "application/json"})
        return _json(response.body)

    # --- server and account ---------------------------------------------

    def public_info(self, base, timeout=None):
        """{Id, ServerName, Version, …}; needs no token."""
        info = self.get("/System/Info/Public", base=base, timeout=timeout)
        if not isinstance(info, dict) or not info.get("Id"):
            raise HttpError(SERVER, "This is not a Jellyfin server")
        return info

    def authenticate(self, user, password):
        result = self.post("/Users/AuthenticateByName",
                           {"Username": user, "Pw": password})
        self.token = result["AccessToken"]
        self.user_id = result["User"]["Id"]
        return result

    def sign_out(self):
        self.post("/Sessions/Logout")

    # --- browsing --------------------------------------------------------

    def views(self):
        return self.get("/UserViews", userId=self.user_id)["Items"]

    def resume(self, limit=12):
        return self.get("/UserItems/Resume", userId=self.user_id,
                        limit=limit, mediaTypes="Video", fields=FIELDS,
                        enableImageTypes="Primary,Backdrop,Thumb")["Items"]

    def next_up(self, limit=12, series_id=None):
        return self.get("/Shows/NextUp", userId=self.user_id, limit=limit,
                        seriesId=series_id, fields=FIELDS,
                        enableResumable=False)["Items"]

    def latest(self, parent_id, limit=12):
        return self.get("/Items/Latest", userId=self.user_id,
                        parentId=parent_id, limit=limit, fields=FIELDS)

    def items(self, parent_id=None, start=0, limit=60, types=None,
              recursive=False, search=None, sort="SortName",
              order="Ascending", filters=None):
        """{Items, TotalRecordCount}. `sort`: ItemSortBy values, `filters`:
        ItemFilter values such as IsUnplayed, both comma-separated."""
        return self.get("/Items", userId=self.user_id, parentId=parent_id,
                        startIndex=start, limit=limit,
                        includeItemTypes=types, recursive=recursive,
                        searchTerm=search, sortBy=sort, sortOrder=order,
                        filters=filters,
                        fields=FIELDS, imageTypeLimit=1,
                        enableImageTypes="Primary,Backdrop,Thumb")

    def item(self, item_id):
        return self.get(f"/Items/{quote(item_id)}", userId=self.user_id)

    def seasons(self, series_id):
        return self.get(f"/Shows/{quote(series_id)}/Seasons",
                        userId=self.user_id, fields=FIELDS)["Items"]

    def episodes(self, series_id, season_id):
        return self.get(f"/Shows/{quote(series_id)}/Episodes",
                        userId=self.user_id, seasonId=season_id,
                        fields=FIELDS)["Items"]

    def next_episode(self, episode):
        """The episode after `episode` in its series, across seasons, or
        None. GetEpisodes with startItemId skips the list up to the given
        episode (TvShowsController), so the answer starts with it."""
        series = episode.get("SeriesId")
        if not series:
            return None
        found = self.get(f"/Shows/{quote(series)}/Episodes", userId=self.user_id,
                         startItemId=episode["Id"], isMissing=False, limit=2,
                         fields=FIELDS, enableImageTypes="Primary,Backdrop,Thumb",
                         enableUserData=True)["Items"]
        if len(found) == 2 and found[0].get("Id") == episode["Id"]:
            return found[1]
        return None

    def media_segments(self, item_id):
        """{Items: [{Type, StartTicks, EndTicks}, …]} of intro, credits …
        (MediaSegmentsController, server 10.10 or newer; older servers
        answer 404, which counts as none)."""
        try:
            return self.get(f"/MediaSegments/{quote(item_id)}")
        except HttpError as e:
            if e.status == 404:
                return {"Items": []}
            raise

    def set_played(self, item_id, played):
        path = f"/UserPlayedItems/{quote(item_id)}"
        if played:
            return self.post(path, userId=self.user_id)
        return self.delete(path, userId=self.user_id)

    def set_favorite(self, item_id, favorite):
        path = f"/UserFavoriteItems/{quote(item_id)}"
        if favorite:
            return self.post(path, userId=self.user_id)
        return self.delete(path, userId=self.user_id)

    def image(self, item_id, kind="Primary", tag=None, width=None):
        """JPEG bytes of an item image, scaled by the server."""
        url = self.url(f"/Items/{quote(item_id)}/Images/{kind}",
                       tag=tag, maxWidth=width, quality=90)
        return self.http.request("GET", url, {
            "Authorization": self.authorization()}).body

    # --- playback (docs/playback.md) ---------------------------------------

    def playback_info(self, item_id, max_bitrate, start_ticks=0,
                      audio_index=None, subtitle_index=None,
                      force_transcode=False, media_source_id=None):
        """audio_index, subtitle_index: Jellyfin stream indexes; None lets
        the server choose from the user's language settings, subtitle -1
        is off. The server uses them only together with the media source
        they belong to (MediaInfoHelper.SetDeviceSpecificData), so
        media_source_id defaults to the item's own, the first source.
        force_transcode: the phone failed to play the original, let the
        server convert it."""
        if media_source_id is None and (audio_index is not None
                                        or subtitle_index is not None):
            media_source_id = item_id
        from ephyra.playback import device_profile
        return self.post(
            f"/Items/{quote(item_id)}/PlaybackInfo",
            {"UserId": self.user_id,
             "MaxStreamingBitrate": max_bitrate or 140_000_000,
             "StartTimeTicks": start_ticks,
             "MediaSourceId": media_source_id,
             "AudioStreamIndex": audio_index,
             "SubtitleStreamIndex": subtitle_index,
             "EnableDirectPlay": not force_transcode,
             "EnableDirectStream": not force_transcode,
             "EnableTranscoding": True,
             # Converting because the phone failed: re-encode both
             # streams instead of copying them into HLS.
             "AllowVideoStreamCopy": not force_transcode,
             "AllowAudioStreamCopy": not force_transcode,
             "AutoOpenLiveStream": True,
             "DeviceProfile": device_profile(max_bitrate)})

    def report(self, event, payload):
        """event: "" (started), "Progress" or "Stopped"."""
        path = "/Sessions/Playing" + (f"/{event}" if event else "")
        self.post(path, payload)

    def stop_encoding(self, play_session_id):
        """Kill the server's ffmpeg jobs of one play session
        (HlsSegmentController.StopEncodingProcess; docs/playback.md)."""
        self.delete("/Videos/ActiveEncodings", deviceId=self.device_id,
                    playSessionId=play_session_id)


def _json(body):
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        raise HttpError(SERVER, "The server sent an invalid answer") from None

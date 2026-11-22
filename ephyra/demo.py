"""A small stand-in for a Jellyfin server that serves the recorded demo
library (tests/data/demo). The store screenshots use it
(EPHYRA_DEMO=<dir>), and the tests run the client, the proxy and mutual
TLS against it. Only the endpoints Ephyra calls are implemented.
No GTK."""
import json
import logging
import re
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("ephyra.demo")
# Seconds a client may take for its TLS handshake.
HANDSHAKE_TIMEOUT = 10

TOKEN = "demo-token"
PASSWORD = "demo"


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def finish_request(self, request, client_address):
        if isinstance(request, ssl.SSLSocket):
            request.settimeout(HANDSHAKE_TIMEOUT)
            try:
                request.do_handshake()
            except (OSError, ssl.SSLError) as e:
                # A client without its certificate ends here; the client
                # sees the refused handshake.
                log.debug("TLS handshake with %s failed: %s", client_address, e)
                return
            request.settimeout(None)
        super().finish_request(request, client_address)


class DemoServer:
    def __init__(self, directory, tls=None):
        """tls: (server cert file, key file, CA file for client
        certificates) for HTTPS that requires a client certificate."""
        self.directory = Path(directory)
        self.library = json.loads((self.directory / "library.json").read_text())
        self.items = {i["Id"]: i for i in self.library["items"]}
        self.reports = []      # (path, payload) of /Sessions/Playing*
        self.playback_requests = []   # PlaybackInfo payloads
        self.stopped_encodings = []   # (deviceId, playSessionId) deleted
        # A converted stream instead of direct play; `hold` keeps its
        # playlist request waiting until set, like a server whose ffmpeg
        # starts slowly.
        self.transcode = False
        self.hold = threading.Event()
        self.hold.set()
        self.sessions = 0
        self.requests = []     # (method, path, headers) seen
        self.media = bytes(range(256)) * 4096   # 1 MiB for range tests
        # Tracks of the media file as Jellyfin lists them (MediaStreams);
        # text subtitles are offered as SRT files from `subtitles`.
        self.media_streams = []
        self.subtitles = b""
        # MediaSegments per item id, as Jellyfin 10.10 answers them.
        self.segments = dict(self.library.get("segments", {}))
        server = self

        class Handler(_Handler):
            owner = server

        self.httpd = _Server(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.scheme = "http"
        if tls:
            cert, key, ca = tls
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            context.load_verify_locations(ca)
            context.verify_mode = ssl.CERT_REQUIRED
            # The handshake runs in the connection's own thread
            # (_Server.finish_request): in accept() one client that never
            # finished it held up every other connection and shutdown()
            # (#21).
            self.httpd.socket = context.wrap_socket(
                self.httpd.socket, server_side=True,
                do_handshake_on_connect=False)
            self.scheme = "https"

    @property
    def url(self):
        host, port = self.httpd.server_address
        return f"{self.scheme}://{host}:{port}"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True,
                         name="ephyra-demo").start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # --- queries -------------------------------------------------------

    def children(self, parent_id, recursive=False, types=None):
        out = []
        for item in self.library["items"]:
            if item.get("ParentId") == parent_id:
                out.append(item)
                if recursive and item.get("IsFolder"):
                    out.extend(self.children(item["Id"], True))
        if types:
            wanted = set(types.split(","))
            out = [i for i in out if i["Type"] in wanted]
        return out


ROUTES = []


def route(method, pattern):
    def wrap(fn):
        ROUTES.append((method, re.compile(pattern + "$"), fn))
        return fn
    return wrap


class _Handler(BaseHTTPRequestHandler):
    owner = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        parts = urlsplit(self.path)
        query = {k.lower(): v[-1] for k, v in parse_qs(parts.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.owner.requests.append((method, parts.path, dict(self.headers)))
        lookup = "GET" if method == "HEAD" else method
        for m, pattern, fn in ROUTES:
            match = pattern.match(parts.path)
            if m == lookup and match:
                public = fn.__name__ in ("public_info", "authenticate")
                if not public and f'Token="{TOKEN}"' not in self.headers.get(
                        "Authorization", ""):
                    return self._json(None, 401)
                payload = json.loads(body) if body else None
                return fn(self, query, payload, *match.groups())
        self._json(None, 404)

    def _json(self, data, status=200):
        body = b"" if data is None else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _bytes(self, data, content_type):
        start, end, status = 0, len(data) - 1, 200
        match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else end
            else:
                start = len(data) - int(match.group(2))
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data[start:end + 1])


@route("GET", r"/System/Info/Public")
def public_info(h, q, p):
    h._json(h.owner.library["server"])


@route("POST", r"/Users/AuthenticateByName")
def authenticate(h, q, p):
    user = h.owner.library["user"]
    if not p or p.get("Username", "").lower() != user["Name"].lower() \
            or p.get("Pw") != PASSWORD:
        return h._json(None, 401)
    h._json({"AccessToken": TOKEN, "User": user,
             "ServerId": h.owner.library["server"]["Id"]})


@route("POST", r"/Sessions/Logout")
def logout(h, q, p):
    h._json(None, 204)


@route("GET", r"/UserViews")
def views(h, q, p):
    items = [i for i in h.owner.library["items"] if i["Type"] == "CollectionFolder"]
    h._json({"Items": items, "TotalRecordCount": len(items)})


@route("GET", r"/UserItems/Resume")
def resume(h, q, p):
    items = [h.owner.items[i] for i in h.owner.library["resume"]]
    h._json({"Items": items, "TotalRecordCount": len(items)})


@route("GET", r"/Shows/NextUp")
def next_up(h, q, p):
    items = [h.owner.items[i] for i in h.owner.library["next_up"]]
    if q.get("seriesid"):
        items = [i for i in items if i.get("SeriesId") == q["seriesid"]]
    h._json({"Items": items, "TotalRecordCount": len(items)})


@route("GET", r"/Items/Latest")
def latest(h, q, p):
    view = h.owner.items.get(q.get("parentid"), {})
    types = {"movies": "Movie", "tvshows": "Series",
             "music": "MusicAlbum"}.get(view.get("CollectionType"))
    items = h.owner.children(view.get("Id"), True, types)
    h._json(items[:int(q.get("limit", 12))])


# sortBy values the demo understands, as keys of the recorded items. Items
# without the field (the recordings have no DateCreated) keep the name
# order; the server's own rules are in its ItemSortBy comparers.
SORT_KEYS = {"datecreated": lambda i: i.get("DateCreated") or "",
             "premieredate": lambda i: i.get("PremiereDate")
             or str(i.get("ProductionYear") or ""),
             "communityrating": lambda i: i.get("CommunityRating") or 0}


def sort_items(found, q):
    """Episodes and tracks by number, else by name; then by the first
    sortBy value in sortOrder."""
    found = sorted(found, key=lambda i: (i.get("IndexNumber") or 0, i["Name"]))
    first = (q.get("sortby") or "").lower().split(",")[0]
    descending = (q.get("sortorder") or "").lower().startswith("descending")
    if first in SORT_KEYS:
        found.sort(key=SORT_KEYS[first], reverse=descending)
    elif descending:
        found.reverse()
    return found


@route("GET", r"/Items")
def items(h, q, p):
    owner = h.owner
    if q.get("searchterm"):
        term = q["searchterm"].lower()
        found = [i for i in owner.library["items"]
                 if term in i["Name"].lower() and i["Type"] in
                 ("Movie", "Series", "MusicAlbum", "Episode", "Audio")]
    else:
        found = owner.children(q.get("parentid"),
                               q.get("recursive") == "true",
                               q.get("includeitemtypes"))
        found = sort_items(found, q)
    filters = set((q.get("filters") or "").lower().split(","))
    if "isunplayed" in filters:
        found = [i for i in found if not i.get("UserData", {}).get("Played")]
    if "isfavorite" in filters:
        found = [i for i in found if i.get("UserData", {}).get("IsFavorite")]
    start, limit = int(q.get("startindex", 0)), int(q.get("limit", 100))
    h._json({"Items": found[start:start + limit],
             "TotalRecordCount": len(found), "StartIndex": start})


@route("GET", r"/Items/([0-9a-f]+)")
def item(h, q, p, item_id):
    if item_id not in h.owner.items:
        return h._json(None, 404)
    h._json(h.owner.items[item_id])


@route("GET", r"/Shows/([0-9a-f]+)/Seasons")
def seasons(h, q, p, series_id):
    found = h.owner.children(series_id, types="Season")
    h._json({"Items": found, "TotalRecordCount": len(found)})


@route("GET", r"/Shows/([0-9a-f]+)/Episodes")
def episodes(h, q, p, series_id):
    if q.get("seasonid"):
        found = h.owner.children(q["seasonid"], types="Episode")
    else:
        # The whole series in order, as TvShowsController lists it.
        found = h.owner.children(series_id, True, "Episode")
        found.sort(key=lambda i: (i.get("ParentIndexNumber") or 0,
                                  i.get("IndexNumber") or 0))
    if q.get("startitemid"):
        ids = [i["Id"] for i in found]
        start = q["startitemid"]
        found = found[ids.index(start):] if start in ids else []
    if q.get("limit"):
        found = found[:int(q["limit"])]
    h._json({"Items": found, "TotalRecordCount": len(found)})


@route("GET", r"/MediaSegments/([0-9a-f]+)")
def media_segments(h, q, p, item_id):
    found = h.owner.segments.get(item_id, [])
    h._json({"Items": found, "TotalRecordCount": len(found)})


@route("GET", r"/Items/([0-9a-f]+)/Images/(\w+)")
def image(h, q, p, item_id, kind):
    path = h.owner.directory / "images" / f"{item_id}-{kind}.jpg"
    if not path.is_file():
        return h._json(None, 404)
    h._bytes(path.read_bytes(), "image/jpeg")


@route("POST", r"/Items/([0-9a-f]+)/PlaybackInfo")
def playback_info(h, q, p, item_id):
    item = h.owner.items[item_id]
    streams = [dict(s) for s in h.owner.media_streams]
    audio = [s["Index"] for s in streams if s["Type"] == "Audio"]
    for s in streams:
        if s["Type"] == "Subtitle":
            # As Jellyfin's StreamBuilder answers Ephyra's SRT profile.
            s["DeliveryMethod"] = "External"
            s["DeliveryUrl"] = (f"/Videos/{item_id}/{item_id}/Subtitles/"
                                f"{s['Index']}/0/Stream.srt?ApiKey={TOKEN}")
    for s in streams:
        if s["Type"] == "Subtitle" and s.get("IsTextSubtitleStream") is False:
            # Picture subtitles match no profile (StreamBuilder).
            s["DeliveryMethod"] = "Encode"
            s.pop("DeliveryUrl")
    p = p or {}
    owner = h.owner
    owner.playback_requests.append(p)
    if p.get("MediaSourceId") != item_id:
        # Like MediaInfoHelper: track indexes only with their source.
        p = dict(p, AudioStreamIndex=None, SubtitleStreamIndex=None)
    owner.sessions += 1
    session = f"demo-session-{owner.sessions}"
    subtitle = p.get("SubtitleStreamIndex")
    if subtitle is None:
        # The server's pick from the user's settings: a default track.
        subtitle = next((s["Index"] for s in streams if s["Type"] == "Subtitle"
                         and s.get("IsDefault")), -1)
    burn = any(s["Index"] == subtitle and s.get("DeliveryMethod") == "Encode"
               for s in streams)
    transcode = owner.transcode or burn or not p.get("EnableDirectPlay", True)
    source = {
        "Id": item_id, "Container": "mkv", "SupportsDirectPlay": not transcode,
        "SupportsDirectStream": not transcode, "SupportsTranscoding": True,
        "RunTimeTicks": item.get("RunTimeTicks"), "ETag": "demo",
        "MediaStreams": streams,
        "DefaultAudioStreamIndex": p.get("AudioStreamIndex") or
        (audio[0] if audio else None),
        "DefaultSubtitleStreamIndex": subtitle}
    if transcode:
        source["TranscodingUrl"] = (
            f"/videos/{item_id}/master.m3u8?MediaSourceId={item_id}"
            f"&PlaySessionId={session}&SubtitleStreamIndex={subtitle}"
            f"&ApiKey={TOKEN}")
    h._json({"PlaySessionId": session, "MediaSources": [source]})


@route("GET", r"/videos/([0-9a-f]+)/master\.m3u8")
def master(h, q, p, item_id):
    # Not a real playlist: the tests stop before or when GStreamer fails.
    h.owner.hold.wait(30)
    h._bytes(b"#EXTM3U\n", "application/vnd.apple.mpegurl")


@route("DELETE", r"/Videos/ActiveEncodings")
def active_encodings(h, q, p):
    h.owner.stopped_encodings.append((q.get("deviceid"), q.get("playsessionid")))
    h._json(None, 204)


@route("GET", r"/Videos/([0-9a-f]+)/[0-9a-f]+/Subtitles/(\d+)/0/Stream\.srt")
def subtitle(h, q, p, item_id, index):
    h._bytes(h.owner.subtitles, "text/plain")


@route("GET", r"/(?:Videos|Audio)/([0-9a-f]+)/stream")
def stream(h, q, p, item_id):
    h._bytes(h.owner.media, "video/x-matroska")


@route("POST", r"(/Sessions/Playing(?:/Progress|/Stopped)?)")
def report(h, q, p, path):
    h.owner.reports.append((path, p))
    h._json(None, 204)


@route("POST", r"/UserPlayedItems/([0-9a-f]+)")
def played(h, q, p, item_id):
    h.owner.items[item_id]["UserData"]["Played"] = True
    h._json(h.owner.items[item_id]["UserData"])


@route("DELETE", r"/UserPlayedItems/([0-9a-f]+)")
def unplayed(h, q, p, item_id):
    h.owner.items[item_id]["UserData"]["Played"] = False
    h._json(h.owner.items[item_id]["UserData"])


@route("POST", r"/UserFavoriteItems/([0-9a-f]+)")
def favorite(h, q, p, item_id):
    h.owner.items[item_id]["UserData"]["IsFavorite"] = True
    h._json(h.owner.items[item_id]["UserData"])


@route("DELETE", r"/UserFavoriteItems/([0-9a-f]+)")
def unfavorite(h, q, p, item_id):
    h.owner.items[item_id]["UserData"]["IsFavorite"] = False
    h._json(h.owner.items[item_id]["UserData"])

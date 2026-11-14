"""Short live HLS window for the ERR channels Kodi can keep playing."""

import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 18675
ORIGIN = "https://live.err.ee/live/"
KEEP = 8
USER_AGENT = "Kodi/21.0 (ETV otse)"
SUBTITLE_NAMES = {
    "et": "Eesti",
    "ru": "Vene",
    "nl": "Hollandi",
    "en": "Inglise",
    "fi": "Soome",
}

_quality = "1080p"
_cache = {}
_lock = threading.Lock()


def log(message):
    try:
        import xbmc
        xbmc.log("ETV otse: " + message, xbmc.LOGINFO)
    except Exception:
        print(message)


def set_quality(value):
    global _quality
    if value:
        _quality = value


def target_height():
    digits = "".join(ch for ch in (_quality or "") if ch.isdigit())
    return int(digits or "1080")


def fetch(url):
    now = time.time()
    with _lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < 1:
            return hit[1]
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        text = response.read().decode("utf-8")
    with _lock:
        _cache[url] = (time.time(), text)
    return text


def parse_attrs(line):
    body = line.split(":", 1)[1]
    attrs = {}
    for match in re.finditer(r'([A-Z0-9-]+)=("([^"]*)"|[^,]*)', body):
        attrs[match.group(1)] = match.group(3) if match.group(3) is not None else match.group(2)
    return attrs


def parse_master(text):
    audios = []
    videos = []
    subtitles = []
    seen_langs = set()
    seen_subs = set()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#EXT-X-MEDIA:"):
            attrs = parse_attrs(line)
            lang = attrs.get("LANGUAGE") or ""
            uri = (attrs.get("URI") or "").split("?", 1)[0]
            if attrs.get("TYPE") == "AUDIO" and uri and lang and lang != "zxx":
                if lang not in seen_langs:
                    seen_langs.add(lang)
                    audios.append({
                        "lang": lang,
                        "name": (attrs.get("NAME") or lang).replace('"', ""),
                        "uri": uri,
                        "default": attrs.get("DEFAULT") == "YES",
                    })
            elif attrs.get("TYPE") == "SUBTITLES" and uri and lang and lang != "und":
                if lang not in seen_subs:
                    seen_subs.add(lang)
                    subtitles.append({
                        "lang": lang,
                        "name": SUBTITLE_NAMES.get(lang, (attrs.get("NAME") or lang).replace('"', "")),
                        "uri": uri,
                    })
        elif line.startswith("#EXT-X-STREAM-INF:") and index + 1 < len(lines):
            uri = lines[index + 1]
            if not uri.startswith("#"):
                attrs = parse_attrs(line)
                resolution = attrs.get("RESOLUTION") or "0x0"
                try:
                    height = int(resolution.split("x", 1)[1])
                except (IndexError, ValueError):
                    height = 0
                videos.append({
                    "bandwidth": attrs.get("BANDWIDTH") or "0",
                    "codecs": attrs.get("CODECS") or "avc1.640028,mp4a.40.2",
                    "resolution": resolution,
                    "height": height,
                    "uri": uri.split("?", 1)[0],
                })
                index += 1
        index += 1
    if audios and not any(audio["default"] for audio in audios):
        audios[0]["default"] = True
    return audios, videos, subtitles


def choose_video(videos, height):
    if not videos:
        raise LookupError("video")
    eligible = [video for video in videos if video["height"] and video["height"] <= height]
    pool = eligible or videos
    return min(pool, key=lambda video: abs(video["height"] - height))


def load_master(channel):
    return parse_master(fetch(ORIGIN + channel + ".m3u8"))


def playback_block(channel):
    try:
        text = media_playlist(channel, "video")
    except Exception:
        return None
    segments = [line for line in text.splitlines() if line.startswith("https://")]
    if len(segments) < 2:
        return None
    request = urllib.request.Request(
        segments[-2],
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-32"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if (response.headers.get("drm") or "").lower() == "true":
                return "drm"
            return None
    except urllib.error.HTTPError as exc:
        if (exc.headers.get("drm") or "").lower() == "true":
            return "drm"
        if exc.code == 403:
            return "drm"
        return None
    except Exception:
        return None


def absolute(uri):
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    return ORIGIN + uri


def rewrite_map(line):
    marker = 'URI="'
    start = line.find(marker)
    if start < 0:
        return line
    start += len(marker)
    end = line.find('"', start)
    return line[:start] + absolute(line[start:end]) + line[end:]


def trim(text):
    media_sequence = 0
    version = "7"
    target = "2"
    map_line = None
    entries = []
    pending = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("##"):
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            media_sequence = int(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-VERSION:"):
            version = line.split(":", 1)[1]
        elif line.startswith("#EXT-X-TARGETDURATION:"):
            target = line.split(":", 1)[1]
        elif line.startswith("#EXT-X-MAP:"):
            map_line = rewrite_map(line)
        elif line.startswith("#EXTM3U") or line.startswith("#EXT-X-INDEPENDENT-SEGMENTS"):
            continue
        elif line.startswith("#EXT-X-PLAYLIST-TYPE") or line.startswith("#EXT-X-ENDLIST"):
            continue
        elif line.startswith("#"):
            pending.append(line)
        else:
            entries.append(pending + [absolute(line)])
            pending = []

    if len(entries) > KEEP:
        media_sequence += len(entries) - KEEP
        entries = entries[-KEEP:]

    out = [
        "#EXTM3U",
        "#EXT-X-VERSION:%s" % version,
        "#EXT-X-MEDIA-SEQUENCE:%d" % media_sequence,
        "#EXT-X-INDEPENDENT-SEGMENTS",
        "#EXT-X-TARGETDURATION:%s" % target,
    ]
    if map_line:
        out.append(map_line)
    for entry in entries:
        out.extend(entry)
    return "\n".join(out) + "\n"


def master_playlist(channel):
    audios, videos, subtitles = load_master(channel)
    video = choose_video(videos, target_height())
    root = "http://%s:%d/%s" % (HOST, PORT, channel)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for audio in audios:
        default = "YES" if audio["default"] else "NO"
        lines.append(
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="%s",NAME="%s",'
            'DEFAULT=%s,AUTOSELECT=YES,CHANNELS="2",URI="%s/audio/%s.m3u8"'
            % (audio["lang"], audio["name"], default, root, audio["lang"])
        )
    for subtitle in subtitles:
        lines.append(
            '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",LANGUAGE="%s",NAME="%s",'
            'DEFAULT=NO,AUTOSELECT=YES,URI="%s/sub/%s.m3u8"'
            % (subtitle["lang"], subtitle["name"], root, subtitle["lang"])
        )
    extra = ',SUBTITLES="subs"' if subtitles else ""
    lines.append(
        '#EXT-X-STREAM-INF:BANDWIDTH=%s,CODECS="%s",RESOLUTION=%s,AUDIO="audio"%s'
        % (video["bandwidth"], video["codecs"], video["resolution"], extra)
    )
    lines.append(root + "/video.m3u8")
    return "\n".join(lines) + "\n"


def _track(tracks, lang):
    for track in tracks:
        if track["lang"] == lang:
            return track
    return tracks[0] if tracks else None


def media_playlist(channel, kind, lang=None):
    audios, videos, subtitles = load_master(channel)
    if kind == "video":
        upstream = choose_video(videos, target_height())["uri"]
    elif kind == "sub":
        track = _track(subtitles, lang)
        if track is None:
            raise LookupError("sub")
        upstream = track["uri"]
    else:
        track = _track(audios, lang)
        if track is None:
            raise LookupError("audio")
        upstream = track["uri"]
    return trim(fetch(ORIGIN + upstream))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/")
        channel = parts[0].replace(".m3u8", "") if parts and parts[0] else ""
        if channel not in ("etv", "etv2", "etvpluss"):
            self.send_error(404)
            return
        try:
            if len(parts) == 1:
                body = master_playlist(channel)
            elif len(parts) == 2 and parts[1] == "video.m3u8":
                body = media_playlist(channel, "video")
            elif len(parts) == 3 and parts[1] == "audio" and parts[2].endswith(".m3u8"):
                body = media_playlist(channel, "audio", parts[2][:-5])
            elif len(parts) == 3 and parts[1] == "sub" and parts[2].endswith(".m3u8"):
                body = media_playlist(channel, "sub", parts[2][:-5])
            else:
                self.send_error(404)
                return
        except Exception as exc:
            log("voog ebaõnnestus: %s" % exc)
            message = "Voogu ei saanud\n".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(message)
            return

        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


def make_server():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    return server

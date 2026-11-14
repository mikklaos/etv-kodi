"""Serve a short live HLS window for ERR channels so VLC can keep playing."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8765
ORIGIN = "https://live.err.ee/live/"
KEEP = 8

CHANNELS = {
    "etv": {
        "video": "etv-video=3110800.m3u8",
        "audio": "etv-audio_214400_est=212400.m3u8",
        "bandwidth": 3665000,
        "codecs": "mp4a.40.2,avc1.640028",
        "resolution": "1920x1080",
    },
    "etv2": {
        "video": "etv2-video=3110800.m3u8",
        "audio": "etv2-audio_214400_est=212400.m3u8",
        "bandwidth": 3665000,
        "codecs": "mp4a.40.2,avc1.640028",
        "resolution": "1920x1080",
    },
    "etvpluss": {
        "video": "etvpluss-video=3110800.m3u8",
        "audio": "etvpluss-audio_214400_rus=212400.m3u8",
        "bandwidth": 3665000,
        "codecs": "mp4a.40.2,avc1.640028",
        "resolution": "1920x1080",
    },
}

_cache = {}


def fetch(name):
    now = time.time()
    hit = _cache.get(name)
    if hit and now - hit[0] < 1:
        return hit[1]
    request = urllib.request.Request(ORIGIN + name, headers={"User-Agent": "VLC/3.0.24"})
    with urllib.request.urlopen(request, timeout=10) as response:
        text = response.read().decode("utf-8")
    _cache[name] = (now, text)
    return text


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
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            media_sequence = int(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-VERSION:"):
            version = line.split(":", 1)[1]
        elif line.startswith("#EXT-X-TARGETDURATION:"):
            target = line.split(":", 1)[1]
        elif line.startswith("#EXT-X-MAP:"):
            map_line = rewrite_map(line)
        elif line.startswith("#EXTINF") or line.startswith("#EXT-X-PROGRAM-DATE-TIME"):
            pending.append(line)
        elif line.startswith("#"):
            continue
        else:
            entries.append(pending + [absolute(line)])
            pending = []

    if len(entries) > KEEP:
        media_sequence += len(entries) - KEEP
        entries = entries[-KEEP:]

    out = [
        "#EXTM3U",
        f"#EXT-X-VERSION:{version}",
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f"#EXT-X-TARGETDURATION:{target}",
    ]
    if map_line:
        out.append(map_line)
    for entry in entries:
        out.extend(entry)
    return "\n".join(out) + "\n"


def master(channel):
    track = CHANNELS[channel]
    root = f"http://{HOST}:{PORT}/{channel}"
    return "\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        (
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="et",NAME="Eesti",'
            f'DEFAULT=YES,AUTOSELECT=YES,CHANNELS="2",URI="{root}/audio.m3u8"'
        ),
        (
            f"#EXT-X-STREAM-INF:BANDWIDTH={track['bandwidth']},CODECS=\"{track['codecs']}\","
            f"RESOLUTION={track['resolution']},FRAME-RATE=25,AUDIO=\"audio\""
        ),
        f"{root}/video.m3u8",
        "",
    ])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/")
        channel = parts[0].removesuffix(".m3u8") if parts else ""
        if channel not in CHANNELS:
            self.send_error(404)
            return
        try:
            if len(parts) == 1:
                body = master(channel)
            elif len(parts) == 2 and parts[1] in ("video.m3u8", "audio.m3u8"):
                kind = "video" if parts[1].startswith("video") else "audio"
                body = trim(fetch(CHANNELS[channel][kind]))
            else:
                self.send_error(404)
                return
        except Exception as exc:
            message = f"Voogu ei saanud: {exc}\n".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return

        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"http://{HOST}:{PORT}/etv.m3u8", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

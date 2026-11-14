import os
import socket
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

try:
    from urllib.parse import parse_qsl
except ImportError:
    from urlparse import parse_qsl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))
import proxy

HANDLE = int(sys.argv[1])
PARAMS = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 and sys.argv[2].startswith("?") else {}

CHANNELS = (
    ("etv", "ETV"),
    ("etv2", "ETV2"),
    ("etvpluss", "ETV+"),
)


def port_open():
    sock = socket.socket()
    sock.settimeout(0.3)
    try:
        sock.connect((proxy.HOST, proxy.PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def ensure_proxy():
    if port_open():
        return True
    addon_path = xbmcaddon.Addon().getAddonInfo("path")
    service = addon_path.rstrip("/\\").replace("\\", "/") + "/service.py"
    xbmc.executebuiltin('RunScript("%s")' % service)
    for _ in range(20):
        if port_open():
            return True
        xbmc.sleep(250)
    return False


def inputstream_properties(item):
    if not xbmc.getCondVisibility("System.HasAddon(inputstream.adaptive)"):
        xbmcgui.Dialog().notification(
            "ETV otse",
            "Paigalda InputStream Adaptive",
            xbmcgui.NOTIFICATION_WARNING,
        )
        return
    try:
        major = int(xbmc.getInfoLabel("System.BuildVersion").split(".")[0])
    except ValueError:
        major = 19
    key = "inputstream" if major >= 19 else "inputstreamaddon"
    item.setProperty(key, "inputstream.adaptive")
    item.setProperty("inputstream.adaptive.manifest_type", "hls")


def list_channels():
    addon = xbmcaddon.Addon()
    icon = addon.getAddonInfo("icon")
    for channel, title in CHANNELS:
        item = xbmcgui.ListItem(title)
        item.setProperty("IsPlayable", "true")
        item.setArt({"icon": icon, "thumb": icon, "poster": icon})
        try:
            info = item.getVideoInfoTag()
            info.setTitle(title)
            info.setMediaType("video")
        except Exception:
            item.setInfo("video", {"title": title, "mediatype": "video"})
        url = "%s?action=play&channel=%s" % (sys.argv[0], channel)
        xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=False)
    xbmcplugin.setContent(HANDLE, "videos")
    xbmcplugin.endOfDirectory(HANDLE)


def play(channel):
    titles = dict(CHANNELS)
    if channel not in titles:
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    if proxy.playback_block(channel) == "drm":
        xbmcgui.Dialog().ok(
            "ETV otse",
            "See saade on DRM-kaitsega ja avalik voog ei käivitu. Kui saade vahetub, proovi uuesti.",
        )
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    if ensure_proxy():
        url = "http://%s:%d/%s.m3u8" % (proxy.HOST, proxy.PORT, channel)
    else:
        url = "https://live.err.ee/live/%s.m3u8" % channel
    item = xbmcgui.ListItem(titles[channel], path=url)
    item.setMimeType("application/vnd.apple.mpegurl")
    item.setContentLookup(False)
    item.setProperty("IsPlayable", "true")
    inputstream_properties(item)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


if __name__ == "__main__":
    if PARAMS.get("action") == "play":
        play(PARAMS.get("channel", ""))
    else:
        list_channels()

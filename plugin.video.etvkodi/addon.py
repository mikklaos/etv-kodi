import json
import os
import socket
import sys
import urllib.request
from datetime import datetime, timedelta

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
ART = {
    "etv": ("etv.jpg", "etv-logo.png"),
    "etv2": ("etv2.jpg", "etv2-logo.png"),
    "etvpluss": ("etv+.jpg", "etv+-logo.png"),
}
WEEKDAYS = (
    "esmaspäev",
    "teisipäev",
    "kolmapäev",
    "neljapäev",
    "reede",
    "laupäev",
    "pühapäev",
)


def addon_path():
    return xbmcaddon.Addon().getAddonInfo("path")


def channel_art(channel):
    fanart_name, logo_name = ART[channel]
    root = os.path.join(addon_path(), "resources")
    return os.path.join(root, fanart_name), os.path.join(root, logo_name)


def apply_art(item, channel, image=None):
    fanart, logo = channel_art(channel)
    picture = image or logo
    item.setArt({"fanart": fanart, "poster": picture, "icon": picture, "thumb": picture})


def set_title(item, title, plot=""):
    try:
        info = item.getVideoInfoTag()
        info.setTitle(title)
        info.setMediaType("video")
        if plot:
            info.setPlot(plot)
    except Exception:
        labels = {"title": title, "mediatype": "video"}
        if plot:
            labels["plot"] = plot
        item.setInfo("video", labels)


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
    service = addon_path().rstrip("/\\").replace("\\", "/") + "/service.py"
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


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": proxy.USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def day_count():
    try:
        days = int(xbmcaddon.Addon().getSetting("days") or "31")
    except ValueError:
        days = 31
    return days if days > 0 else 1


def list_channels():
    items = []
    for channel, title in CHANNELS:
        item = xbmcgui.ListItem(title)
        apply_art(item, channel)
        set_title(item, title)
        url = "%s?action=enter&channel=%s" % (sys.argv[0], channel)
        items.append((url, item, True))

    for channel, title in CHANNELS:
        live_title = "%s otse" % title
        item = xbmcgui.ListItem(live_title)
        apply_art(item, channel)
        set_title(item, live_title)
        item.setProperty("IsPlayable", "true")
        url = "%s?action=play&channel=%s" % (sys.argv[0], channel)
        items.append((url, item, False))

    xbmcplugin.addDirectoryItems(HANDLE, items)
    xbmcplugin.setContent(HANDLE, "videos")
    xbmcplugin.endOfDirectory(HANDLE)


def list_dates(channel):
    if channel not in ART:
        xbmcplugin.endOfDirectory(HANDLE)
        return
    items = []
    today = datetime.now()
    for offset in range(day_count()):
        day = today - timedelta(days=offset)
        if offset == 0:
            label = "Täna %s" % day.strftime("%Y-%m-%d")
        else:
            label = "%s %s" % (WEEKDAYS[day.weekday()], day.strftime("%Y-%m-%d"))
        item = xbmcgui.ListItem(label)
        fanart, _logo = channel_art(channel)
        item.setArt({"fanart": fanart, "poster": fanart, "icon": fanart, "thumb": fanart})
        url = "%s?action=list&channel=%s&date=%s" % (sys.argv[0], channel, day.strftime("%Y-%m-%d"))
        items.append((url, item, True))
    xbmcplugin.addDirectoryItems(HANDLE, items)
    xbmcplugin.endOfDirectory(HANDLE)


def photo_url(show):
    try:
        photos = show["contents"][0]["horizontalPhotos"][0]["photoTypes"]
    except (KeyError, IndexError, TypeError):
        return ""
    entry = photos.get("26") or photos.get(26) or {}
    if isinstance(entry, dict):
        return entry.get("url") or ""
    return ""


def list_schedule(channel, date):
    if channel not in ART:
        xbmcplugin.endOfDirectory(HANDLE)
        return
    year, month, day = date.split("-")
    url = (
        "https://etv.err.ee/api/tvSchedule/getTimelineSchedule2"
        "?year=%s&month=%s&day=%s&channel=%s" % (year, month, day, channel)
    )
    try:
        shows = fetch_json(url)
    except Exception:
        xbmcgui.Dialog().ok("ETV otse", "Saadete nimekirja hankimine nurjus.")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    fanart, _logo = channel_art(channel)
    items = []
    for show in shows:
        contents = show.get("contents") or []
        if not contents or not contents[0].get("medias"):
            continue
        title = show.get("name") or show.get("programName") or "Saade"
        plot = show.get("programName") or ""
        image = photo_url(show) or fanart
        item = xbmcgui.ListItem(title)
        item.setProperty("IsPlayable", "true")
        item.setArt({"fanart": image, "poster": image, "icon": image, "thumb": image})
        set_title(item, title, plot)
        content_id = show.get("contentId")
        play_url = "%s?action=watch&channel=%s&id=%s" % (sys.argv[0], channel, content_id)
        items.append((play_url, item, False))

    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addDirectoryItems(HANDLE, items)
    xbmcplugin.setContent(HANDLE, "videos")
    xbmcplugin.endOfDirectory(HANDLE)
    xbmc.executebuiltin("Container.SetViewMode(500)")


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
    item = xbmcgui.ListItem("%s otse" % titles[channel], path=url)
    item.setMimeType("application/vnd.apple.mpegurl")
    item.setContentLookup(False)
    item.setProperty("IsPlayable", "true")
    inputstream_properties(item)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def absolute_url(url):
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def play_archive(content_id):
    page_url = "https://etv.err.ee/api/tv/getTvPageData?contentId=%s&contentOnly=true" % content_id
    try:
        page = fetch_json(page_url)
        media = page["showInfo"]["media"]
        src = media.get("src") or {}
        hls = src.get("hls") or ""
        restrictions = (((page.get("pageControlData") or {}).get("mainContent") or {}).get("medias") or [{}])[0]
        drm = bool(media.get("drm") or (restrictions.get("restrictions") or {}).get("drm"))
    except Exception:
        hls = ""
        drm = False
    if drm or not hls:
        xbmcgui.Dialog().ok(
            "ETV otse",
            "Selle saate avalikku voogu ei saa mängida.",
        )
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(path=absolute_url(hls))
    item.setMimeType("application/vnd.apple.mpegurl")
    item.setContentLookup(False)
    item.setProperty("IsPlayable", "true")
    inputstream_properties(item)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


if __name__ == "__main__":
    action = PARAMS.get("action")
    if action == "play":
        play(PARAMS.get("channel", ""))
    elif action == "enter":
        list_dates(PARAMS.get("channel", ""))
    elif action == "list":
        list_schedule(PARAMS.get("channel", ""), PARAMS.get("date", ""))
    elif action == "watch":
        play_archive(PARAMS.get("id", ""))
    else:
        list_channels()

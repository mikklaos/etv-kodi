import json
import os
import sys
import threading

import xbmc
import xbmcaddon

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))
import proxy

VIEWMODE_NORMAL = 0


def rpc(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        payload["params"] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception:
        return {}


def get_viewmode():
    result = rpc("Settings.GetSettingValue", {"setting": "videoscreen.viewmode"})
    return result.get("result", {}).get("value")


def set_viewmode(value):
    rpc("Settings.SetSettingValue", {"setting": "videoscreen.viewmode", "value": value})


class EtvPlayer(xbmc.Player):
    def __init__(self):
        super(EtvPlayer, self).__init__()
        self._saved = None

    def onAVStarted(self):
        try:
            playing = self.getPlayingFile() or ""
        except Exception:
            return
        if (
            "127.0.0.1:%d" % proxy.PORT not in playing
            and "vod.err.ee" not in playing
            and "live.err.ee" not in playing
        ):
            return
        if self._saved is not None:
            return
        current = get_viewmode()
        self._saved = current
        if current not in (None, VIEWMODE_NORMAL):
            set_viewmode(VIEWMODE_NORMAL)
            xbmc.log("ETV otse: kuvarežiim Normal", xbmc.LOGINFO)

    def _restore(self):
        saved = self._saved
        self._saved = None
        if saved not in (None, VIEWMODE_NORMAL):
            set_viewmode(saved)

    def onPlayBackEnded(self):
        self._restore()

    def onPlayBackStopped(self):
        self._restore()

    def onPlayBackError(self):
        self._restore()


class SettingsMonitor(xbmc.Monitor):
    def onSettingsChanged(self):
        proxy.set_quality(xbmcaddon.Addon().getSetting("quality") or "1080p")


if __name__ == "__main__":
    proxy.set_quality(xbmcaddon.Addon().getSetting("quality") or "1080p")
    server = None
    try:
        server = proxy.make_server()
    except OSError:
        xbmc.log("ETV otse: port on juba kasutusel", xbmc.LOGINFO)
    else:
        worker = threading.Thread(target=server.serve_forever)
        worker.daemon = True
        worker.start()
        xbmc.log("ETV otse kuulab http://%s:%d" % (proxy.HOST, proxy.PORT), xbmc.LOGINFO)

    player = EtvPlayer()
    monitor = SettingsMonitor()
    monitor.waitForAbort()
    player._restore()
    if server is not None:
        server.shutdown()
        server.server_close()

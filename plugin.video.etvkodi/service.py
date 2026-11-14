import os
import sys
import threading

import xbmc
import xbmcaddon

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))
import proxy


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

    monitor = SettingsMonitor()
    monitor.waitForAbort()
    if server is not None:
        server.shutdown()
        server.server_close()

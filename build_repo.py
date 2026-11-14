"""Build Kodi zip files, addons.xml and icons."""

import hashlib
import os
import struct
import zipfile
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDONS = ("plugin.video.etvkodi", "repository.etvkodi")


def write_icon(path):
    width = height = 256

    def pixel(x, y):
        cx = cy = 128
        dx = x - cx
        dy = y - cy
        if dx * dx + dy * dy <= 96 * 96:
            # Play triangle inside the circle.
            if -42 <= dx <= 28 and abs(dy) <= (28 - dx) * 0.72:
                return (255, 255, 255, 255)
            return (20, 92, 184, 255)
        return (14, 22, 36, 255)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)


def addon_xml(addon_id):
    path = os.path.join(ROOT, addon_id, "addon.xml")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    start = text.find("<addon ")
    return text[start:].strip()


def version_of(addon_id):
    text = addon_xml(addon_id)
    marker = 'version="'
    start = text.find(marker) + len(marker)
    return text[start:text.find('"', start)]


def zip_addon(addon_id):
    version = version_of(addon_id)
    dest_dir = os.path.join(ROOT, "zips", addon_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "%s-%s.zip" % (addon_id, version))
    source = os.path.join(ROOT, addon_id)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        seen = set()
        for folder, dirnames, filenames in os.walk(source):
            dirnames[:] = [name for name in dirnames if name != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                parts = rel.split("/")
                for index in range(1, len(parts)):
                    directory = "/".join(parts[:index]) + "/"
                    if directory not in seen:
                        seen.add(directory)
                        archive.writestr(directory, "")
                archive.write(full, rel)
    return dest


def main():
    import shutil
    friendly = {
        "repository.etvkodi": "Paigalda-ETV-hoidla.zip",
        "plugin.video.etvkodi": "Paigalda-ETV-otse.zip",
    }
    for addon_id in ADDONS:
        write_icon(os.path.join(ROOT, addon_id, "icon.png"))
        dest = zip_addon(addon_id)
        print(dest)
        shutil.copyfile(dest, os.path.join(ROOT, friendly[addon_id]))

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n' + "\n".join(addon_xml(addon_id) for addon_id in ADDONS) + "\n</addons>\n"
    xml_path = os.path.join(ROOT, "addons.xml")
    data = xml.encode("utf-8")
    with open(xml_path, "wb") as handle:
        handle.write(data)
    digest = hashlib.md5(data).hexdigest() + "\n"
    with open(os.path.join(ROOT, "addons.xml.md5"), "w", encoding="ascii", newline="\n") as handle:
        handle.write(digest)
    print(digest.strip())


if __name__ == "__main__":
    main()

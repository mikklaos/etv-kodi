"""Build Kodi zip files, addons.xml and icons."""

import hashlib
import os
import struct
import zipfile
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDONS = ("plugin.video.etvkodi", "repository.etvkodi")


def paeth(left, up, upper_left):
    estimate = left + up - upper_left
    nearest = min((abs(estimate - left), left), (abs(estimate - up), up), (abs(estimate - upper_left), upper_left))
    return nearest[1]


def read_rgba(path):
    data = open(path, "rb").read()
    pos = 8
    width = height = None
    compressed = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or color != 6 or interlace != 0:
                raise ValueError("unsupported png %s" % path)
        elif tag == b"IDAT":
            compressed += chunk
        elif tag == b"IEND":
            break
    raw = zlib.decompress(compressed)
    stride = width * 4
    rows = []
    index = 0
    previous = bytearray(stride)
    for _y in range(height):
        filter_type = raw[index]
        index += 1
        row = bytearray(raw[index:index + stride])
        index += stride
        for x in range(stride):
            left = row[x - 4] if x >= 4 else 0
            up = previous[x]
            upper_left = previous[x - 4] if x >= 4 else 0
            if filter_type == 1:
                row[x] = (row[x] + left) & 255
            elif filter_type == 2:
                row[x] = (row[x] + up) & 255
            elif filter_type == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                row[x] = (row[x] + paeth(left, up, upper_left)) & 255
            elif filter_type != 0:
                raise ValueError("unsupported png filter")
        previous = row
        rows.append(row)
    return width, height, rows


def sample(rows, width, height, x, y):
    if x < 0 or y < 0 or x >= width or y >= height:
        return (0, 0, 0, 0)
    offset = x * 4
    pixel = rows[y]
    return tuple(pixel[offset:offset + 4])


def write_png(path, width, height, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)


def write_etv_icon(path):
    source = os.path.join(ROOT, "plugin.video.etvkodi", "resources", "etv-logo.png")
    src_w, src_h, src_rows = read_rgba(source)
    size = 512
    scale = min(420 / src_w, 180 / src_h)
    dst_w = max(1, int(round(src_w * scale)))
    dst_h = max(1, int(round(src_h * scale)))
    origin_x = (size - dst_w) // 2
    origin_y = (size - dst_h) // 2
    rows = []
    for y in range(size):
        row = bytearray(size * 4)
        src_y = (y - origin_y) / scale
        if 0 <= src_y < src_h:
            y0 = int(src_y)
            y1 = min(y0 + 1, src_h - 1)
            fy = src_y - y0
            for x in range(size):
                src_x = (x - origin_x) / scale
                if src_x < 0 or src_x >= src_w:
                    continue
                x0 = int(src_x)
                x1 = min(x0 + 1, src_w - 1)
                fx = src_x - x0
                pixels = (
                    sample(src_rows, src_w, src_h, x0, y0),
                    sample(src_rows, src_w, src_h, x1, y0),
                    sample(src_rows, src_w, src_h, x0, y1),
                    sample(src_rows, src_w, src_h, x1, y1),
                )
                weights = ((1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy)
                offset = x * 4
                for channel in range(4):
                    row[offset + channel] = int(sum(pixel[channel] * weight for pixel, weight in zip(pixels, weights)))
        rows.append(row)
    write_png(path, size, size, rows)


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


def zip_entry(name, data):
    info = zipfile.ZipInfo(name)
    info.date_time = (2024, 1, 1, 0, 0, 0)
    info.create_system = 3
    info.flag_bits |= 0x800
    if name.endswith("/"):
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (0o40755 << 16) | 0x10
    else:
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
    return info, data


def zip_addon(addon_id):
    version = version_of(addon_id)
    dest_dir = os.path.join(ROOT, "zips", addon_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "%s-%s.zip" % (addon_id, version))
    source = os.path.join(ROOT, addon_id)
    with zipfile.ZipFile(dest, "w") as archive:
        seen = set()
        for folder, dirnames, filenames in os.walk(source):
            dirnames[:] = [name for name in dirnames if name != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc") or "+" in name:
                    raise RuntimeError("unsafe addon filename: %s" % name)
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                parts = rel.split("/")
                for index in range(1, len(parts)):
                    directory = "/".join(parts[:index]) + "/"
                    if directory not in seen:
                        seen.add(directory)
                        info, data = zip_entry(directory, b"")
                        archive.writestr(info, data)
                with open(full, "rb") as handle:
                    payload = handle.read()
                info, data = zip_entry(rel, payload)
                archive.writestr(info, data)
    return dest


def main():
    import shutil
    friendly = {
        "repository.etvkodi": "Paigalda-ETV-hoidla.zip",
        "plugin.video.etvkodi": "Paigalda-ETV-otse.zip",
    }
    for addon_id in ADDONS:
        icon = os.path.join(ROOT, addon_id, "icon.png")
        if addon_id == "plugin.video.etvkodi":
            write_etv_icon(icon)
        else:
            write_icon(icon)
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

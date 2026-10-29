"""Utilidades compartidas por las pruebas."""
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def png(rgb=(80, 100, 140), w=60, h=60):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def csrf(r):
    return re.search(r'name="csrf" value="([^"]+)"', r.get_data(as_text=True)).group(1)


def txt(r):
    return r.get_data(as_text=True)

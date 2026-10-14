"""A minimal PNG writer (8-bit RGB or grey, zlib only) so that the simulator needs no imaging library."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def encode_png(image) -> bytes:
    """Encode an array of shape (h, w), (h, w, 3) or (h, w, 4), dtype uint8."""
    a = np.ascontiguousarray(image)
    if a.dtype != np.uint8:
        raise TypeError("PNG encoder takes uint8 images")
    if a.ndim == 2:
        a = a[:, :, None]
    if a.ndim != 3 or a.shape[2] not in (1, 3, 4):
        raise ValueError(f"cannot encode an image of shape {a.shape}")
    h, w, c = a.shape
    colour = {1: 0, 3: 2, 4: 6}[c]
    raw = np.zeros((h, 1 + w * c), dtype=np.uint8)     # every scan line starts with filter type 0
    raw[:, 1:] = a.reshape(h, w * c)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, colour, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + _chunk(b"IEND", b""))


def encode_png16(image) -> bytes:
    """Encode an array of shape (h, w), dtype uint16, as a 16-bit greyscale PNG (a depth image in millimetres)."""
    a = np.ascontiguousarray(image)
    if a.dtype != np.uint16 or a.ndim != 2:
        raise TypeError("the 16-bit PNG encoder takes uint16 images of shape (h, w)")
    h, w = a.shape
    raw = np.zeros((h, 1 + w * 2), dtype=np.uint8)
    raw[:, 1:] = a.astype(">u2").view(np.uint8).reshape(h, w * 2)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 0, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + _chunk(b"IEND", b""))


def depth_png(depth) -> bytes:
    """A depth image (float metres, 0 = none) as a 16-bit PNG in millimetres (0 = none)."""
    mm = np.clip(np.round(np.asarray(depth, dtype=np.float64) * 1000.0), 0, 65535).astype(np.uint16)
    return encode_png16(mm)


def write_png(path, image) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(encode_png(image))


def decode_png(data: bytes) -> np.ndarray:
    """Read back what `encode_png` writes (filter type 0 only). Used by the tests."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, head = 8, b"", None
    while pos < len(data):
        (n,), tag = struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0] != zlib.crc32(tag + body) & 0xFFFFFFFF:
            raise ValueError("bad chunk checksum")
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, colour = head[0], head[1], head[2], head[3]
    c = {0: 1, 2: 3, 6: 4}[colour]
    if depth != 8:
        raise ValueError("only 8-bit images")
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, 1 + w * c)
    if np.any(raw[:, 0] != 0):
        raise ValueError("only filter type 0")
    out = raw[:, 1:].reshape(h, w, c)
    return out[:, :, 0].copy() if c == 1 else out.copy()

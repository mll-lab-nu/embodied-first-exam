"""A minimal PNG encoder and decoder (8-bit RGB / RGBA / grey, no interlacing) on zlib from the standard library."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_COLOR_TYPE = {1: 0, 3: 2, 4: 6}
_CHANNELS = {0: 1, 2: 3, 6: 4}


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)


def encode(image: np.ndarray) -> bytes:
    """Encode a uint8 array of shape (H, W), (H, W, 3) or (H, W, 4). The output depends only on the pixels."""
    a = np.asarray(image)
    if a.dtype != np.uint8:
        raise TypeError("PNG encoder takes uint8 pixels")
    if a.ndim == 2:
        a = a[:, :, None]
    if a.ndim != 3 or a.shape[2] not in _COLOR_TYPE:
        raise ValueError(f"cannot encode an array of shape {image.shape}")
    h, w, c = a.shape
    rows = np.zeros((h, 1 + w * c), dtype=np.uint8)       # filter byte 0 (None) in front of every scanline
    rows[:, 1:] = a.reshape(h, w * c)
    header = struct.pack(">IIBBBBB", w, h, 8, _COLOR_TYPE[c], 0, 0, 0)
    return _SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + _chunk(b"IEND", b"")


def write(path: str | Path, image: np.ndarray) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(image))
    return path


def decode(data: bytes) -> np.ndarray:
    """Decode a PNG written by `encode` (any filter type is accepted, so most plain 8-bit files load too)."""
    if data[:8] != _SIGNATURE:
        raise ValueError("not a PNG file")
    pos, idat, w = 8, [], None
    while pos < len(data):
        (n,), tag = struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in _CHANNELS or interlace:
                raise ValueError("only 8-bit non-interlaced grey / RGB / RGBA PNG is supported")
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    if w is None:
        raise ValueError("PNG without a header")
    c = _CHANNELS[ctype]
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), dtype=np.uint8).reshape(h, 1 + w * c)
    out = np.zeros((h, w * c), dtype=np.uint8)
    prev = np.zeros(w * c, dtype=np.int32)
    for y in range(h):
        f, line = int(raw[y, 0]), raw[y, 1:].astype(np.int32)
        if f == 0:
            cur = line
        elif f == 2:
            cur = (line + prev) & 255
        else:                                              # filters that look at the pixel to the left
            cur = np.zeros(w * c, dtype=np.int32)
            for i in range(w * c):
                left = cur[i - c] if i >= c else 0
                up, ul = prev[i], (prev[i - c] if i >= c else 0)
                if f == 1:
                    pred = left
                elif f == 3:
                    pred = (left + up) // 2
                elif f == 4:
                    p = left + up - ul
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - ul)
                    pred = left if (pa <= pb and pa <= pc) else (up if pb <= pc else ul)
                else:
                    raise ValueError(f"bad PNG filter {f}")
                cur[i] = (line[i] + pred) & 255
        out[y] = cur
        prev = cur
    out = out.reshape(h, w, c)
    return out[:, :, 0] if c == 1 else out


def read(path: str | Path) -> np.ndarray:
    return decode(Path(path).read_bytes())

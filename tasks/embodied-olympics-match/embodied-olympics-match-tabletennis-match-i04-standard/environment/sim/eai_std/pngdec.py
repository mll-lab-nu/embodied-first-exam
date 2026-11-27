"""A small PNG decoder (8-bit grey / RGB / RGBA, non-interlaced; every filter type) with numpy only, for the images the
match core encodes (core/observe.py png(): RGB8, filter 0). PIL is used instead when it is installed."""
from __future__ import annotations

import struct
import zlib

import numpy as np

CHANNELS = {0: 1, 2: 3, 6: 4}


def decode(data: bytes) -> np.ndarray:
    """PNG bytes -> uint8 (H, W, 3) (alpha dropped, grey repeated)."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        return np.asarray(im.convert("RGB"), dtype=np.uint8)
    except ImportError:
        pass
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    off, idat, hdr = 8, [], None
    while off < len(data):
        n, tag = struct.unpack(">I4s", data[off:off + 8])
        body = data[off + 8:off + 8 + n]
        off += 12 + n
        if tag == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    w, h, depth, ctype, _c, _f, interlace = hdr
    if depth != 8 or ctype not in CHANNELS or interlace:
        raise ValueError(f"unsupported PNG (depth {depth}, colour type {ctype}, interlace {interlace})")
    bpp = CHANNELS[ctype]
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), dtype=np.uint8).reshape(h, 1 + w * bpp)
    filt, rows = raw[:, 0], raw[:, 1:].astype(np.int32)
    out = np.zeros((h, w * bpp), dtype=np.int32)
    prev = np.zeros(w * bpp, dtype=np.int32)
    for y in range(h):
        f, r = int(filt[y]), rows[y]
        if f == 0:
            cur = r
        elif f == 1:
            cur = np.cumsum(r.reshape(w, bpp), axis=0).reshape(-1) & 255
        elif f == 2:
            cur = (r + prev) & 255
        else:
            cur = np.zeros_like(r)
            for x in range(w * bpp):
                a = cur[x - bpp] if x >= bpp else 0
                b = prev[x]
                if f == 3:
                    cur[x] = (r[x] + ((a + b) >> 1)) & 255
                else:
                    c = prev[x - bpp] if x >= bpp else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    cur[x] = (r[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y] = cur
        prev = cur
    img = out.astype(np.uint8).reshape(h, w, bpp)
    if bpp == 1:
        return np.repeat(img, 3, axis=2)
    return np.ascontiguousarray(img[:, :, :3])

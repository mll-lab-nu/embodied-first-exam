"""RCB1 — a tiny binary frame for one JSON header plus N raw blobs (videos, image arrays, depth, proprio).

    frame = b"RCB1" | header_len uint32 LE | header JSON (UTF-8) | blob_0 | blob_1 | ...
    header = {"v": 1, "meta": {...}, "parts": [{"name", "kind", "len", ...}, ...]}   # blobs in the same order

kinds: "mp4" (fps, n), "jpeg", "array" (dtype, shape; C-order raw bytes), "json" (utf-8), "bytes".
Zero dependencies for bytes/json parts; numpy only when you ask for arrays. Used on both sides (server and client),
over HTTP bodies (Content-Type: application/x-rcb1) and equally usable over a raw socket. `python -m rcb1 unpack f dir`.

A server's frames go into the body once: frames_part() names a list of arrays (one frame axis) without stacking them,
size() gives a frame's length from its parts' sizes before anything is built (so a response limit can drop parts
first), and encode() writes each such array into the body once and lets go of it, so building a response holds the
captured frames plus one response body (docs/protocol/README.md §3 and §6, the sim's memory cap). The bytes are the
same as for the stacked array.
"""
from __future__ import annotations
import json, struct, sys, pathlib

MAGIC = b"RCB1"


class Frames:
    """An array part's data that is not stacked: the arrays of one frame axis, all of one shape, written into the body
    one by one as C-order `dtype` bytes (the bytes of np.stack(arrays).astype(dtype)). len() is their size; encode()
    takes each array out of the list once it is written, so the list is empty after the body is built."""

    def __init__(self, arrays: list, dtype, shape: tuple):
        import numpy as np
        self.arrays, self.dtype, self.shape = arrays, np.dtype(dtype), tuple(int(x) for x in shape)
        self.nbytes = len(arrays) * self.dtype.itemsize * int(np.prod(self.shape, dtype=np.int64))

    def __len__(self) -> int:
        return self.nbytes

    def write_into(self, out: bytearray) -> None:
        import numpy as np
        a = self.arrays
        a.reverse()                                  # pop() from the end: each array is dropped once it is written
        while a:
            x = np.ascontiguousarray(a.pop(), dtype=self.dtype)
            if x.size:                               # (a view with a zero in its shape cannot be cast: no bytes anyway)
                out += memoryview(x).cast("B")


def frames_part(name: str, arrays: list, extra: dict | None = None, empty=None) -> tuple:
    """array_part(name, np.stack(arrays)) without the stack: the same header and bytes, each array copied into the body
    once (Frames). `arrays` is handed over (encode() empties it). No arrays: array_part(name, empty), or np.stack's
    error when `empty` is None."""
    import numpy as np
    if not len(arrays):
        if empty is None:
            np.stack(arrays)                         # raises as np.stack does
        return array_part(name, empty, extra)
    for i, x in enumerate(arrays):
        if not isinstance(x, np.ndarray):
            arrays[i] = np.asarray(x)
    shape, dt = arrays[0].shape, arrays[0].dtype
    for x in arrays:
        if x.shape != shape:
            np.stack(arrays)                         # raises as np.stack does (all arrays must have the same shape)
        if x.dtype != dt:
            dt = np.promote_types(dt, x.dtype)       # np.stack's result type
    if not dt.isnative:
        dt = dt.newbyteorder("=")                    # ... in native byte order, as np.stack gives it
    return (name, "array", Frames(arrays, dt, shape), {"dtype": str(dt), "shape": [len(arrays), *shape], **(extra or {})})


def _header(meta: dict, parts: list) -> bytes:
    hdr_parts = []
    for name, kind, blob, extra in parts:
        d = {"name": name, "kind": kind, "len": len(blob)}
        d.update({k: v for k, v in (extra or {}).items() if v is not None})
        hdr_parts.append(d)
    return json.dumps({"v": 1, "meta": meta, "parts": hdr_parts}, separators=(",", ":")).encode()


def size(meta: dict, parts: list) -> int:
    """The length encode(meta, parts) will have, without building it."""
    return 8 + len(_header(meta, parts)) + sum(len(blob) for _, _, blob, _ in parts)


def encode(meta: dict, parts: list[tuple[str, str, bytes, dict]]) -> bytes:
    """parts: [(name, kind, blob, extra), ...]; extra carries dtype/shape/fps/n. A blob is bytes, or Frames
    (frames_part()): then the frame is a bytearray with each array written into it once (and the Frames emptied)."""
    header = _header(meta, parts)
    if not any(isinstance(blob, Frames) for _, _, blob, _ in parts):
        return b"".join([MAGIC, struct.pack("<I", len(header)), header] + [blob for _, _, blob, _ in parts])
    out = bytearray(MAGIC + struct.pack("<I", len(header)) + header)
    for _, _, blob, _ in parts:
        if isinstance(blob, Frames):
            blob.write_into(out)
        else:
            out += blob
    return out


def array_part(name: str, arr, extra: dict | None = None) -> tuple[str, str, bytes, dict]:
    import numpy as np
    a = np.ascontiguousarray(arr)
    return (name, "array", a.tobytes(), {"dtype": str(a.dtype), "shape": list(a.shape), **(extra or {})})


def decode(buf: bytes, arrays: bool = True) -> tuple[dict, dict]:
    """-> (meta, parts) where parts[name] = {"kind", ..., "data"}; arrays become numpy arrays when arrays=True."""
    if buf[:4] != MAGIC:
        raise ValueError("not an RCB1 frame")
    n = struct.unpack("<I", buf[4:8])[0]
    header = json.loads(buf[8:8 + n].decode()); off = 8 + n
    out = {}
    for p in header["parts"]:
        blob = buf[off:off + p["len"]]; off += p["len"]
        d = dict(p)
        if p["kind"] == "array" and arrays:
            import numpy as np
            d["data"] = np.frombuffer(blob, dtype=np.dtype(p["dtype"])).reshape(p["shape"])
        elif p["kind"] == "json":
            d["data"] = json.loads(blob.decode())
        else:
            d["data"] = blob
        out[p["name"]] = d
    return header.get("meta", {}), out


def unpack_to_dir(buf: bytes, out_dir: str) -> list[str]:
    """Write a frame's parts as files: mp4/jpeg/bytes verbatim, arrays as .npy, meta as meta.json."""
    import numpy as np
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    meta, parts = decode(buf, arrays=True); written = []
    (out / "meta.json").write_text(json.dumps(meta, indent=1)); written.append("meta.json")
    for name, p in parts.items():
        safe = name.replace("/", "__")
        if p["kind"] == "array":
            f = out / f"{safe}.npy"; np.save(f, p["data"])
        elif p["kind"] == "mp4":
            f = out / f"{safe}.mp4"; f.write_bytes(p["data"])
        elif p["kind"] == "jpeg":
            f = out / f"{safe}.jpg"; f.write_bytes(p["data"])
        elif p["kind"] == "json":
            f = out / f"{safe}.json"; f.write_text(json.dumps(p["data"], indent=1))
        else:
            f = out / f"{safe}.bin"; f.write_bytes(p["data"])
        written.append(f.name)
    return written


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "unpack":
        print("\n".join(unpack_to_dir(open(sys.argv[2], "rb").read(), sys.argv[3])))
    elif len(sys.argv) == 3 and sys.argv[1] == "info":
        meta, parts = decode(open(sys.argv[2], "rb").read(), arrays=False)
        print(json.dumps(meta, indent=1)); [print(n, {k: v for k, v in p.items() if k != "data"}) for n, p in parts.items()]
    else:
        print(__doc__)

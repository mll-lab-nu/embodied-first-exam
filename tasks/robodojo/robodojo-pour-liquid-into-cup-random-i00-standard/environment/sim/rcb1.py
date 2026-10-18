"""RCB1 — a tiny binary frame for one JSON header plus N raw blobs (videos, image arrays, depth, proprio).

    frame = b"RCB1" | header_len uint32 LE | header JSON (UTF-8) | blob_0 | blob_1 | ...
    header = {"v": 1, "meta": {...}, "parts": [{"name", "kind", "len", ...}, ...]}   # blobs in the same order

kinds: "mp4" (fps, n), "jpeg", "array" (dtype, shape; C-order raw bytes), "json" (utf-8), "bytes".
Zero dependencies for bytes/json parts; numpy only when you ask for arrays. Used on both sides (server and client),
over HTTP bodies (Content-Type: application/x-rcb1) and equally usable over a raw socket. `python -m rcb1 unpack f dir`.
"""
from __future__ import annotations
import json, struct, sys, pathlib

MAGIC = b"RCB1"


def encode(meta: dict, parts: list[tuple[str, str, bytes, dict]]) -> bytes:
    """parts: [(name, kind, blob, extra), ...]; extra carries dtype/shape/fps/n."""
    hdr_parts = []
    for name, kind, blob, extra in parts:
        d = {"name": name, "kind": kind, "len": len(blob)}
        d.update({k: v for k, v in (extra or {}).items() if v is not None})
        hdr_parts.append(d)
    header = json.dumps({"v": 1, "meta": meta, "parts": hdr_parts}, separators=(",", ":")).encode()
    return b"".join([MAGIC, struct.pack("<I", len(header)), header] + [blob for _, _, blob, _ in parts])


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

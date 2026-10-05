#!/usr/bin/env python3
"""Deduplicated raw log of a trial's model requests: <trial>/gateway/raw.jsonl.gz (raw.jsonl.xz once compacted),
written by gateway.py --raw.

An agent resends its whole conversation with every request, so one request is mostly the previous one: in a codex
trial ~98% of a request's `input` items are byte-identical to items it already sent, and recording every request body
in full grows quadratically (one 2,000-request trial: 5.9 GB of raw/NNNNNN.json.gz). Like the harnesses' own session
files (codex's rollout-*.jsonl, Claude Code's session .jsonl), which store every conversation item once, this log stores
every distinct piece of a request body once and each request as references to those pieces. It stays lossless: every
request body and response is reconstructed byte for byte.

Format: one JSON object per line. While the trial runs, the gateway appends them to raw.jsonl.gz as gzip members (one
stream to zcat). A crash mid-write loses only that append: readers stop before an incomplete member, and a restarted
gateway first cuts the file back to its last complete member, so nothing is appended behind a broken one. Each member is
compressed on its own, so after the trial `compact` rewrites the log as one xz stream (raw.jsonl.xz, LZMA's 64 MB window
also finds the repeats between requests, e.g. the request settings every response echoes): one 1,994-request trial is
5.9 GB as raw/, 66 MB as raw.jsonl.gz, 32 MB as raw.jsonl.xz. Both are plain compressed JSON Lines (zcat / xzcat).

    {"item": 7, "v": <JSON value>}             a body piece (a list element or a large field), the first time it is sent
    {"n": 12, "request": {...}, "response": {...}}
                                               request n (1-based, the n of usage.jsonl's "raw"), with headers and the
                                               response as recorded. Its body is either "body" (text, as before) or
                                               "body_parts": [[key, "v", value] | [key, "i", item] | [key, "l", ranges],
                                               ...] in key order plus "body_ascii" (how the JSON was serialized), where
                                               ranges lists item ids, a run a..b written [a, b].

A JSON body is split into parts only when re-serializing it reproduces the text exactly (compact separators, as codex,
Claude Code and the OpenAI / Anthropic SDKs send); anything else is kept as text.

    rawlog.py cat <gateway dir> [-n N]       print the records in full ({"n", "request", "response"}), one per line
    rawlog.py compact <dir>...               raw.jsonl.gz -> raw.jsonl.xz for every gateway/ below <dir> (finished trials)
    rawlog.py pack <dir>... [--delete]       legacy raw/NNNNNN.json.gz -> raw.jsonl.xz; checks every record round-trips,
                                             then (--delete) removes raw/
    rawlog.py verify <dir>...                decode every log below <dir>; compare with raw/ where it still exists
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import pathlib
import sys
import zlib
from collections.abc import Iterator

NAME = "raw.jsonl.gz"      # live: gzip members appended by the gateway
PACKED = "raw.jsonl.xz"    # compacted: one xz stream
XZ_PRESET = 9              # 64 MB dictionary; ~0.7 GB of memory while compressing
INLINE_MAX = 256    # a non-list field whose JSON is shorter than this stays inline
CHUNK = 1 << 20


def dumps(v, ascii: bool = False) -> str:
    return json.dumps(v, separators=(",", ":"), ensure_ascii=ascii)


def line(obj) -> bytes:
    """One log line. A lone surrogate (a JSON \\udXXX escape) cannot be UTF-8: such a line is written escaped."""
    try:
        return (dumps(obj) + "\n").encode()
    except UnicodeEncodeError:
        return (dumps(obj, True) + "\n").encode()


def ranges(ids: list[int]) -> list:
    out: list = []
    for i in ids:
        last = out[-1] if out else None
        if isinstance(last, list) and last[1] + 1 == i:
            last[1] = i
        elif isinstance(last, int) and last + 1 == i:
            out[-1] = [last, i]
        else:
            out.append(i)
    return out


def expand(rs: list) -> Iterator[int]:
    for r in rs:
        if isinstance(r, list):
            yield from range(r[0], r[1] + 1)
        else:
            yield r


def members(path: pathlib.Path) -> Iterator[tuple[int, list[dict]]]:
    """(end offset, objects) of each complete gzip member of a raw.jsonl.gz (one append each), in order; stops at the
    first incomplete or damaged member (a crash mid-write)."""
    with open(path, "rb") as f:
        start, pending = 0, b""
        while True:
            d = zlib.decompressobj(zlib.MAX_WBITS | 16)
            out, fed = [], 0
            chunk = pending or f.read(CHUNK)
            while chunk:
                fed += len(chunk)
                try:
                    out.append(d.decompress(chunk))
                except zlib.error:
                    return
                if d.eof:
                    break
                chunk = f.read(CHUNK)
            if not d.eof:
                return
            pending = d.unused_data
            end = start + fed - len(pending)
            try:
                objs = [json.loads(ln) for ln in b"".join(out).decode("utf-8").split("\n") if ln]
            except ValueError:                     # UnicodeDecodeError included
                return
            yield end, objs
            start = end


def lines(path: pathlib.Path) -> Iterator[dict]:
    """The log's objects; stops quietly at a truncated or damaged append (a crash mid-write)."""
    if ".xz" not in path.name:
        for _, objs in members(path):
            yield from objs
        return
    try:
        with lzma.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    return
                yield json.loads(line)
    except (EOFError, lzma.LZMAError, ValueError):
        return


class Writer:
    """Appends records to one trial's raw.jsonl.gz; resumes the item table from an existing file, cut back to its last
    complete append first (a crash mid-write leaves a partial gzip member, and anything appended behind it would be
    unreadable)."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        self.ids: dict[bytes, int] = {}
        self.n = 0
        if path.exists():
            end = 0
            for end, objs in members(path):
                for obj in objs:
                    if "item" in obj:
                        self.ids[self._key(obj["v"])] = obj["item"]
                    elif "n" in obj:
                        self.n = obj["n"]
            size = path.stat().st_size
            if size > end:
                with open(path, "r+b") as f:
                    f.truncate(end)
                print(f"rawlog: {path}: dropped {size - end} bytes of an incomplete append", file=sys.stderr)

    @staticmethod
    def _key(v) -> bytes:
        return hashlib.sha256(dumps(v).encode("utf-8", "surrogatepass")).digest()

    def _encode(self, text: str, new: list[bytes]) -> dict | None:
        try:
            obj = json.loads(text)
        except ValueError:
            return None
        if not isinstance(obj, dict):
            return None
        ascii = dumps(obj) != text
        if ascii and dumps(obj, True) != text:
            return None

        def ref(v) -> int:
            k = self._key(v)
            if k not in self.ids:
                self.ids[k] = len(self.ids)
                new.append(line({"item": self.ids[k], "v": v}))
            return self.ids[k]

        parts = []
        for k, v in obj.items():
            if len(dumps(v)) < INLINE_MAX:
                parts.append([k, "v", v])
            elif isinstance(v, list):
                parts.append([k, "l", ranges([ref(x) for x in v])])
            else:
                parts.append([k, "i", ref(v)])
        return {"body_parts": parts, "body_ascii": ascii}

    def append(self, raw: dict) -> int:
        """Record {"request": {..., "body"}, "response": {...}}; returns its n."""
        new: list[bytes] = []
        req = dict(raw["request"])
        enc = self._encode(req["body"], new) if req.get("body_as", "text") == "text" else None
        if enc is not None:
            del req["body"]
            req.update(enc)
        self.n += 1
        new.append(line({"n": self.n, "request": req, "response": raw["response"]}))
        with gzip.open(self.path, "ab") as f:
            f.write(b"".join(new))
        return self.n


def read(path: pathlib.Path) -> Iterator[dict]:
    """The records of a raw.jsonl.gz in full: {"n", "request": {..., "body"}, "response"}."""
    items: dict[int, object] = {}
    for obj in lines(path):
        if "item" in obj:
            items[obj["item"]] = obj["v"]
            continue
        req = obj["request"]
        parts = req.pop("body_parts", None)
        if parts is not None:
            body = {}
            for k, kind, v in parts:
                body[k] = v if kind == "v" else items[v] if kind == "i" else [items[i] for i in expand(v)]
            ascii = req.pop("body_ascii")
            req["body"] = dumps(body, ascii)
        yield {"n": obj["n"], "request": req, "response": obj["response"]}


def log_of(d: pathlib.Path) -> pathlib.Path | None:
    for name in (PACKED, NAME):
        if (d / name).exists():
            return d / name
    return None


def gateway_dirs(paths: list[pathlib.Path]) -> Iterator[pathlib.Path]:
    for p in paths:
        if (p / "raw").is_dir() or log_of(p):
            yield p
        else:
            yield from sorted(q for q in p.rglob("gateway") if q.is_dir())


def legacy(d: pathlib.Path) -> list[pathlib.Path]:
    return sorted((d / "raw").glob("*.json.gz")) if (d / "raw").is_dir() else []


def remove(files: list[pathlib.Path]) -> None:
    for f in files:
        f.unlink()
    files[0].parent.rmdir()


def same(rec: dict, old: dict) -> bool:
    return rec["request"] == old["request"] and rec["response"] == old["response"]


def to_xz(src: pathlib.Path, out: pathlib.Path) -> None:
    """Rewrite a raw.jsonl.gz as one xz stream (via out.tmp, so a half-written out never exists)."""
    tmp = out.with_name(out.name + ".tmp")
    with lzma.open(tmp, "wb", preset=XZ_PRESET) as f:
        for obj in lines(src):
            f.write(line(obj))
    if sum(1 for _ in lines(src)) != sum(1 for _ in lines(tmp)):
        tmp.unlink()
        raise RuntimeError(f"{tmp}: line count differs")
    tmp.rename(out)


def compact(d: pathlib.Path) -> str:
    src = d / NAME
    if not src.exists():
        return f"no {NAME}"
    if (d / PACKED).exists():
        return f"{PACKED} exists already, skipped"
    to_xz(src, d / PACKED)
    msg = f"{src.stat().st_size / 1e6:.1f} MB -> {(d / PACKED).stat().st_size / 1e6:.1f} MB"
    src.unlink()
    return msg


def pack(d: pathlib.Path, delete: bool) -> str:
    files = legacy(d)
    if not files:
        return "no raw/"
    if log_of(d):                              # packed before: --delete removes raw/ once it matches
        msg = verify(d)
        if delete and "identical" in msg:
            remove(files)
            return msg + ", raw/ removed"
        return msg if "differs" in msg else f"{log_of(d).name} exists already, skipped"
    if [int(f.name.split(".")[0]) for f in files] != list(range(1, len(files) + 1)):
        return "raw/ is not numbered 1..N, skipped"
    tmp = d / (NAME + ".tmp")
    tmp.unlink(missing_ok=True)
    w = Writer(tmp)
    for f in files:
        w.append(json.loads(gzip.decompress(f.read_bytes())))
    to_xz(tmp, d / PACKED)
    tmp.unlink()
    for f, rec in zip(files, read(d / PACKED), strict=True):
        if not same(rec, json.loads(gzip.decompress(f.read_bytes()))):
            (d / PACKED).unlink()
            return f"round trip differs at {f.name}, skipped"
    before = sum(f.stat().st_size for f in files)
    msg = f"{len(files)} requests, {before / 1e6:.1f} MB -> {(d / PACKED).stat().st_size / 1e6:.1f} MB"
    if delete:
        remove(files)
        msg += ", raw/ removed"
    return msg


def verify(d: pathlib.Path) -> str:
    path = log_of(d)
    if path is None:
        return "no log"
    files = legacy(d)
    n = 0
    for rec in read(path):                     # streamed: a long trial's records add up to gigabytes
        n += 1
        if rec["n"] != n:
            return f"{path.name}: records out of order"
        if files and n > len(files):
            return f"{path.name}: more records than the {len(files)} raw/ files: differs"
        if files and not same(rec, json.loads(gzip.decompress(files[n - 1].read_bytes()))):
            return f"{path.name}: differs from raw/{files[n - 1].name}"
    if files:
        if len(files) != n:
            return f"{path.name}: {n} records, {len(files)} raw/ files: differs"
        return f"{path.name}: {n} records, identical to raw/"
    return f"{path.name}: {n} records"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cat")
    c.add_argument("dir", type=pathlib.Path)
    c.add_argument("-n", type=int, help="only request n")
    for name in ("compact", "pack", "verify"):
        s = sub.add_parser(name)
        s.add_argument("dirs", type=pathlib.Path, nargs="+")
        if name == "pack":
            s.add_argument("--delete", action="store_true", help="remove raw/ once the packed log round-trips")
    a = p.parse_args()
    if a.cmd == "cat":
        path = log_of(a.dir) if a.dir.is_dir() else a.dir
        if path is None:
            sys.exit(f"{a.dir}: no {PACKED} or {NAME}")
        for rec in read(path):
            if a.n is None or rec["n"] == a.n:
                sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return 0
    bad = 0
    for d in gateway_dirs(a.dirs):
        msg = {"compact": compact, "verify": verify}[a.cmd](d) if a.cmd != "pack" else pack(d, a.delete)
        bad += any(w in msg for w in ("differs", "out of order"))
        print(f"{d}: {msg}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

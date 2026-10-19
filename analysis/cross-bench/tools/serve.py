#!/usr/bin/env python3
"""Serve the local site mirror over HTTP so others can read it (the page is the same file the artifact publishes).

usage: tools/serve.py [--dir ~/Work/cross-bench-artifact] [--port 8044]

Static files only, from one directory, with HTTP Range support so the case videos can seek. Runs as the systemd user
unit `xbench-site.service` (see meta/HANDOFF.md).
"""
from __future__ import annotations
import argparse, functools, http.server, os, re


SKELETON = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}'
            'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')


class Handler(http.server.SimpleHTTPRequestHandler):
    """The artifact page has no <head> of its own (the artifact service wraps it); add the same wrapper here."""
    def guess_type(self, path):
        t = super().guess_type(path)
        return t + "; charset=utf-8" if t.startswith("text/") or t in ("application/javascript", "application/json") else t

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if path.endswith(".html") and os.path.isfile(path) and "Range" not in self.headers:
            body = open(path, "rb").read()
            if not body.lstrip()[:15].lower().startswith(b"<!doctype"):
                body = SKELETON.encode() + body + b"</body></html>"
            import io
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
        if not m or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2) or 0))
        end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        if start >= size:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(1 << 16, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")              # edits to the mirror show up on reload
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.expanduser("~/Work/cross-bench-artifact"))
    ap.add_argument("--port", type=int, default=8044)
    a = ap.parse_args()
    http.server.ThreadingHTTPServer(("0.0.0.0", a.port), functools.partial(Handler, directory=a.dir)).serve_forever()


if __name__ == "__main__":
    main()

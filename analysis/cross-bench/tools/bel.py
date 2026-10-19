"""Client for the batch-eval monitor. The token comes from $BEL_TOKEN and is never written to disk."""
from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

BASE = "http://165.124.184.150:8790/"


def _token() -> str:
    return os.environ.get("BEL_TOKEN") or sys.exit("set BEL_TOKEN")


def get(path: str, params: dict | None = None, start: int | None = None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Cookie": f"bel_token={_token()}"}
    if start is not None:
        headers["Range"] = f"bytes={start}-"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as r:
        return (r.read(), r.headers.get("Content-Range")) if start is not None else r.read()


def get_json(path: str, **params):
    return json.loads(get(path, params or None))


def get_file(trial_id: str, path: str) -> bytes:
    """One response is capped at 8 MiB; fetch the rest with Range requests."""
    body = b""
    while True:
        part, rng = get("api/file", {"id": trial_id, "p": path}, start=len(body))
        body += part
        total = int(rng.rsplit("/", 1)[1]) if rng else len(body)
        if len(body) >= total or not part:
            return body

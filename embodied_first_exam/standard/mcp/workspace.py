"""Observation files in the agent's workspace (D130): images, depth and video go to files, results carry paths.

Files are named <n>_<camera>.<ext> under /app/obs (or a `save_to` directory under /app). The directory /app/obs keeps
the newest MAX_FILES files and at most MAX_BYTES; older ones are deleted (a `save_to` directory is the agent's and is
never pruned)."""
from __future__ import annotations
import base64, io, json, os, pathlib, re, threading
import numpy as np

ROOT = pathlib.Path(os.environ.get("EFE_MCP_WORKSPACE", "/app"))
OBS = ROOT / "obs"
MAX_FILES = int(os.environ.get("EFE_MCP_OBS_MAX_FILES", "300"))
MAX_BYTES = int(float(os.environ.get("EFE_MCP_OBS_MAX_GB", "1")) * 2**30)
THUMB_PX = 256
_lock = threading.Lock()
_counter = [0]
# a second server process writing to the same /app/obs (the Python client of the shell variant) tags its file names
TAG = ("_" + re.sub(r"[^a-z0-9]+", "", os.environ.get("EFE_MCP_FILE_TAG", "").lower())[:8]) \
    if os.environ.get("EFE_MCP_FILE_TAG") else ""


def resolve_under_root(path: str, must_exist: bool = False) -> pathlib.Path:
    """A path the agent gave: relative paths are under the workspace root; anything outside it is refused."""
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    root = ROOT.resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"{path}: only paths under {ROOT} are allowed")
    if must_exist and not p.exists():
        raise ValueError(f"{path}: no such file")
    return p


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80]


class Writer:
    """One call's files: next_step() numbers them, the methods write and return the path as a string."""

    def __init__(self, save_to: str | None = None):
        self.dir = resolve_under_root(save_to) if save_to else OBS
        self.dir.mkdir(parents=True, exist_ok=True)
        self.managed = self.dir == OBS.resolve() or self.dir == OBS
        with _lock:
            _counter[0] = max(_counter[0], self._highest()) + 1
            self.n = _counter[0]

    def _highest(self) -> int:
        best = 0
        try:
            for f in os.scandir(self.dir):
                m = re.match(r"(\d+)_", f.name)
                if m:
                    best = max(best, int(m.group(1)))
        except FileNotFoundError:
            pass
        return best

    def path(self, cam: str, ext: str) -> pathlib.Path:
        return self.dir / f"{self.n:05d}{TAG}_{_safe(cam)}.{ext}"

    def jpeg(self, cam: str, img) -> str:
        from PIL import Image
        p = self.path(cam, "jpg")
        a = np.ascontiguousarray(np.asarray(img))
        if a.dtype != np.uint8:
            a = np.clip(a, 0, 255).astype(np.uint8)
        if a.ndim == 3 and a.shape[2] == 4:
            a = a[:, :, :3]
        Image.fromarray(a).save(p, quality=90)
        return str(p)

    def depth(self, cam: str, d) -> str:
        p = self.path(cam + "_depth", "npy")
        np.save(p, np.asarray(d, dtype=np.float32))
        return str(p)

    def video(self, cam: str, data: bytes) -> str:
        p = self.path(cam, "mp4")
        p.write_bytes(data)
        return str(p)

    def json(self, name: str, obj) -> str:
        p = self.path(name, "json")
        p.write_text(json.dumps(obj, indent=1))
        return str(p)

    def prune(self) -> None:
        if not self.managed:
            return
        try:
            files = sorted((f for f in os.scandir(self.dir) if f.is_file()), key=lambda f: f.name)
        except FileNotFoundError:
            return
        total = sum(f.stat().st_size for f in files)
        while files and (len(files) > MAX_FILES or total > MAX_BYTES):
            f = files.pop(0)
            try:
                total -= f.stat().st_size
                os.unlink(f.path)
            except OSError:
                pass


def thumbnail(img) -> dict:
    """MCP image content: a JPEG of at most THUMB_PX on its long side."""
    from PIL import Image
    a = np.ascontiguousarray(np.asarray(img))
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 3 and a.shape[2] == 4:
        a = a[:, :, :3]
    im = Image.fromarray(a)
    im.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=75)
    return {"type": "image", "data": base64.b64encode(buf.getvalue()).decode(), "mimeType": "image/jpeg"}

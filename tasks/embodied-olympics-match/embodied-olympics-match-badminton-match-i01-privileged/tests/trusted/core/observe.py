"""Observations (sport rule 1, docs/framework_zh.md §9): what a seat gets is the camera images, its own body and the
referee's information, and nothing else. The sport declares the fields of Match.observe() in sport.toml
([observation] fields); a field outside that whitelist is never delivered and is a technical error of the match.

The camera images: Match.cameras(seat, query) returns camera definitions, the task's renderer (renderers/, chosen by
the task parameter `renderer`) draws them from the sport's scene and Match.render_state(), and the core lays the
images out as tiles of one PNG (left to right, `columns` per row), described in the reply (`tiles`).

Reply images (core 0.2.8): Match.reply_views(seat, cmd, info) right after an action -> reply_job() snapshots the
frames under the lock -> CameraWorker.draw_job() draws them off the lock (the same renderer, scene and worker as the
observation) -> one PNG of tiles, each tile also naming its frame (`frame`, `label`) when there are several.

The scene of the players' images (core 0.2.9, renderer rule 6): Sport.scene(cfg), or the presentation scene the sport
declares for its players (sports/<sport>/presentation/presentation.toml `players`, bundled into the simulator by the
generator; renderers/presentation.players_scene): the same kinematics, finer visual meshes. Any other presentation
scene is refused (spectators only)."""
from __future__ import annotations

import copy
import struct
import zlib
from pathlib import Path

import numpy as np


class WhitelistError(Exception):
    pass


def filter_fields(obs: dict, allowed: set[str] | None) -> tuple[dict, list[str]]:
    """(the whitelisted part of obs, the names that were not allowed)."""
    if allowed is None:
        return obs, []
    bad = sorted(k for k in obs if k not in allowed)
    return {k: v for k, v in obs.items() if k in allowed}, bad


def png(img: np.ndarray) -> bytes:
    """A minimal RGB8 PNG encoder (no imaging library needed in the sim)."""
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape[:2]
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def reply_job(m, spec: dict | None, columns: int) -> dict | None:
    """Under the lock: Match.reply_views()'s answer -> a self-contained draw job (deep copies: the match may move on
    while the job is drawn off the lock). A frame without a state gets render_state() now."""
    if not spec or not spec.get("frames"):
        return None
    order = spec.get("order", "frame")
    if order not in ("frame", "camera"):
        raise ValueError(f"reply_views: order must be 'frame' or 'camera', not {order!r}")
    now = None
    frames = []
    for f in spec["frames"]:
        st = f.get("state")
        if st is None:
            now = m.render_state() if now is None else now
            st = now
        cams = list(f.get("cameras") or [])
        if not cams:
            raise ValueError("reply_views: every frame needs at least one camera")
        frames.append({"state": st, "cams": cams, "label": f.get("label")})
    return copy.deepcopy({"frames": frames, "order": order, "columns": int(spec.get("columns") or columns),
                          "note": spec.get("note")})


def compose(images: list[np.ndarray], names: list[str], columns: int = 2) -> tuple[np.ndarray, list[dict]]:
    """Tiles left to right, `columns` per row, each at its own size; -> (sheet, [{camera, x, y, width, height}])."""
    rows = [list(range(i, min(i + columns, len(images)))) for i in range(0, len(images), columns)]
    widths = [sum(images[j].shape[1] for j in r) for r in rows]
    heights = [max(images[j].shape[0] for j in r) for r in rows]
    sheet = np.zeros((sum(heights), max(widths), 3), np.uint8)
    tiles, y = [], 0
    for r, hgt in zip(rows, heights):
        x = 0
        for j in r:
            h, w = images[j].shape[:2]
            sheet[y:y + h, x:x + w] = images[j][..., :3]
            tiles.append({"camera": names[j], "x": x, "y": y, "width": w, "height": h})
            x += w
        y += hgt
    return sheet, tiles


def players_scene(sport, plugin: str, cfg):
    """The scene of the players' images: the sport's presentation scene when it declares `players`, else
    Sport.scene(cfg)."""
    scene = sport.scene(cfg)
    d = Path(plugin).resolve().parent
    if not (d / "presentation" / "presentation.toml").is_file():
        return scene
    from renderers import presentation
    return presentation.players_scene(d, scene)


class CameraWorker:
    """Draws a seat's camera definitions with the task's renderer (in-process or inside a render worker process)."""

    def __init__(self, scene, renderer_name: str | None):
        import renderers
        if getattr(scene, "match", None) is not None and not getattr(scene, "players", False):
            raise ValueError("the players' images are drawn from the match scene (Sport.scene) or the presentation "
                             "scene the sport declares for them; any other presentation scene is for spectators only "
                             "(renderer rule 6)")
        self.name = renderer_name or renderers.DEFAULT
        self.renderer = renderers.load(self.name)(scene)

    def draw(self, state: dict, cams: list[dict], columns: int = 2) -> dict:
        from renderers.base import CameraDef
        defs = [CameraDef.from_dict(c) for c in cams]
        images = self.renderer.render(state, defs)
        sheet, tiles = compose(images, [c.name for c in defs], columns)
        return {"png": png(sheet), "tiles": tiles, "renderer": self.name}

    def draw_frames(self, job: dict) -> dict:
        """A reply job (reply_job()): every frame's cameras drawn from that frame's state, laid out frame after
        frame or camera after camera; a tile names its camera, and its frame (index, label) when there are several."""
        from renderers.base import CameraDef
        frames = job["frames"]
        drawn = []                                  # per frame: [(name, image)]
        for f in frames:
            defs = [CameraDef.from_dict(c) for c in f["cams"]]
            drawn.append(list(zip([c.name for c in defs], self.renderer.render(f["state"], defs))))
        cells = []                                  # (frame index, camera name, image)
        if job.get("order") == "camera":
            for j in range(max(len(d) for d in drawn)):
                cells += [(i, d[j][0], d[j][1]) for i, d in enumerate(drawn) if j < len(d)]
        else:
            cells = [(i, name, img) for i, d in enumerate(drawn) for name, img in d]
        sheet, tiles = compose([c[2] for c in cells], [c[1] for c in cells], int(job.get("columns", 2)))
        many = len(frames) > 1
        for t, (i, _, _) in zip(tiles, cells):
            if many:
                t["frame"] = i
            if frames[i].get("label"):
                t["label"] = frames[i]["label"]
        out = {"png": png(sheet), "tiles": tiles, "renderer": self.name}
        if job.get("note"):
            out["note"] = job["note"]
        return out

    def draw_job(self, job: dict) -> dict:
        """Any job of the core's camera worker: a reply job (frames) or an observation (state + cameras)."""
        if "frames" in job:
            return self.draw_frames(job)
        return self.draw(job["state"], job["cams"], job.get("columns", 2))

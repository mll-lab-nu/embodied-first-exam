"""What spectators get (docs/framework_zh.md §3.1, §4.3): the broadcast log and the replay video. Neither is ever read
back by the match, the replay or the grader; any failure here only switches the spectator output off.

Broadcast log (/data/broadcast.jsonl, RCB_BROADCAST=1): the unchanged legacy writer (broadcast_log.py, copied next
to core/ as spectator/broadcast_log.py by the generator) with the same lines as every legacy sport: a header, a frame
{"k", "q": qpos, ...extra} every `every` control steps (realtime) or after every action (turn), and the events run,
action, unit_over, end. A frame is Match.broadcast_frame() ({"q": [...], ...extra}) when the sport defines it, else
the qpos of Match.render_state().

Replay video (/data/replay.mp4, RCB_RENDER_VIDEO=1): after the match is graded-ready, a fresh process replays the
episode and draws the spectator camera with the spectator renderer (RO_VIDEO_RENDERER, default the players'
renderer; any renderer of renderers/ can re-render later from the episode). The camera: sport.toml
[broadcast] camera (a camera definition), else the first camera of the first seat. Frames of a non-default
renderer carry its label. python -m core.video is this module's video part: python -m core.spectator PLUGIN DIR.
The video is written as replay.part.mp4 and renamed when complete (core 0.2.13): replay.mp4 exists only after a
finished render, which is what the grader's video_rendered reads.

The spectator scene (core 0.2.4): the sport's presentation scene when it declares one (sports/<sport>/presentation/,
renderers/presentation: the match scene with fine visual meshes on the same bodies, same kinematics) and its assets
are present, else the match scene; RO_VIDEO_SCENE=match forces the match scene. A presentation scene is in the
simulator directory only when the sport declares it for its players' images (core 0.2.9: then a task's video shows
the players' scene, untagged: it is the competition picture); otherwise a task's video is the match scene and
re-renders from a checkout get the presentation. Every frame drawn from a spectators-only presentation scene carries
the presentation tag (renderer rule 6), whatever the renderer.
The players' images never use it (observe.CameraWorker).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from . import spec as spec_mod
from .sport import FINISHED, MatchBase, MatchConfig

ROOT = Path(__file__).resolve().parent
WRITER = ROOT.parent / "spectator" / "broadcast_log.py"


def frame_of(m) -> dict | None:
    """The spectator frame of a match now: Match.broadcast_frame() if the sport defines it, else render_state's qpos."""
    if getattr(type(m), "broadcast_frame", None) is not MatchBase.broadcast_frame:
        return m.broadcast_frame()
    st = m.render_state() or {}
    return {"q": list(st["qpos"])} if "qpos" in st else None


class Broadcast:
    def __init__(self, sport, cfg, m, decl, **header):
        self.m, self.log = m, None
        self.clean = lambda x: x                 # the service's scrub of a hidden seed (core/seeds.py)
        if os.environ.get("RCB_BROADCAST", "1") != "1" or not WRITER.exists():
            return
        try:
            spec = importlib.util.spec_from_file_location("ro_broadcast_log", WRITER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            every = int((decl.get("broadcast") or {}).get("every", 2 if sport.protocol == "realtime" else 1))
            self.log = mod.BroadcastLog(every=every, path=os.path.join(os.environ.get("RCB_DATA", "/data"),
                                                                        "broadcast.jsonl"),
                                        sport=sport.name, mode=cfg.format, protocol=sport.protocol, dt=m.dt,
                                        seats=list(cfg.seats), sides={s: cfg.side_of(s) for s in cfg.seats}, **header)
        except Exception:  # noqa: BLE001  (spectator output only)
            self.log = None

    def frame(self, force: bool = False):
        if self.log is None:
            return
        try:
            fr = frame_of(self.m)
            if fr is not None:
                fr = self.clean(dict(fr))
                self.log.frame(self.m.k, fr.pop("q", ()), force=force, **fr)
        except Exception:  # noqa: BLE001
            self.log = None

    def event(self, ev: str, **fields):
        if self.log is not None:
            self.log.event(ev, self.m.k, **self.clean(fields))


# ------------------------------------------------------------------------------------------------ the replay video
def video_camera(sport, cfg, m, decl) -> dict | None:
    cam = (decl.get("broadcast") or {}).get("camera")
    if cam:
        return dict(cam)
    cams = m.cameras(cfg.seats[0], None) if hasattr(m, "cameras") else []
    return dict(cams[0]) if cams else None


def spectator_scene(sport, plugin: str, cfg):
    """(scene, what): the scene spectators see, what = "match" | "presentation" | "match (presentation unavailable:
    ...)". Spectator output only: a failure here falls back to the match scene."""
    base = sport.scene(cfg)
    if os.environ.get("RO_VIDEO_SCENE", "presentation") == "match":
        return base, "match"
    if not (Path(plugin).resolve().parent / "presentation" / "presentation.toml").is_file():
        return base, "match"                       # no presentation (in a task: unless declared for the players)
    try:
        from renderers import presentation
        scene = presentation.for_plugin(plugin, base)
    except Exception as exc:  # noqa: BLE001  (missing assets, no tomllib, ...: the match scene)
        return base, f"match (presentation unavailable: {exc})"
    return (scene, "presentation") if scene is not None else (base, "match")


def render_video(plugin: str, data: Path, fps: int = 10, hold_s: float = 1.0) -> dict:
    """Replay data/episode.jsonl and draw the spectator camera -> data/replay.mp4 (+ video.json)."""
    from .episode import header_cfg, load_plugin, read_rows, replay
    sport = load_plugin(plugin)
    decl = spec_mod.load(plugin)
    rows = read_rows(Path(data) / "episode.jsonl")
    cfg = header_cfg(next(r for r in rows if r["ev"] == "header"))
    m0 = sport.build(cfg)
    cam = video_camera(sport, cfg, m0, decl)
    if cam is None or not hasattr(sport, "scene"):
        return {"video": False, "why": "the sport defines no camera or scene for spectators"}
    import imageio.v2 as imageio
    import renderers
    from renderers.base import CameraDef
    name = os.environ.get("RO_VIDEO_RENDERER") or cfg.renderer or (decl.get("observation") or {}).get("renderer") \
        or renderers.DEFAULT
    scene, scene_what = spectator_scene(sport, plugin, cfg)
    R = renderers.load(name)(scene)
    cd = CameraDef.from_dict(cam)
    every = max(1, int(round(1.0 / (fps * m0.dt)))) if sport.protocol == "realtime" and m0.dt else 1
    repeat = max(1, int(round(fps * hold_s))) if sport.protocol == "turn" else 1
    out = Path(data) / "replay.mp4"
    part = out.with_suffix(".part.mp4")            # renamed once complete: a killed render leaves no replay.mp4
    w = imageio.get_writer(str(part), fps=fps, codec="libx264", quality=7, macro_block_size=8)
    n = 0
    from renderers.label import frame_label
    tag = frame_label(R, scene)                    # None: the default renderer on the match scene (no tag)
    stamp = None
    if tag is not None:
        from renderers.label import stamp as stamp_fn
        stamp = stamp_fn

    def draw(match, *_):
        nonlocal n
        if sport.protocol == "realtime" and match.k % every and match.phase().state != FINISHED:
            return
        img = R.render(match.render_state(), [cd])[0]
        if stamp is not None:
            img = stamp(img, tag)
        for _ in range(repeat):
            w.append_data(img)
            n += 1

    try:
        replay(sport, rows, observer=draw)
    finally:
        w.close()
    part.replace(out)
    info = {"video": n > 0, "frames": n, "fps": fps, "renderer": name, "camera": cam["name"] if "name" in cam else "",
            "scene": scene_what, "label": tag}
    (Path(data) / "video.json").write_text(json.dumps(info))
    return info


def main(argv):
    print(json.dumps(render_video(argv[0], Path(argv[1]))))


if __name__ == "__main__":
    main(sys.argv[1:])

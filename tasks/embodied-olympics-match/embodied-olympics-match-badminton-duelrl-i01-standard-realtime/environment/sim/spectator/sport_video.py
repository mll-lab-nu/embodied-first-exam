"""Spectator replay video for a sport that draws its own players' images (plugin.Views) and declares no spectator
camera or scene, so core/spectator.py renders nothing (robot_coding_bench, board 0136, 2026-10-16; not upstream).

    python3 /srv/spectator/sport_video.py /srv/sport/plugin.py /data      # -> /data/replay.mp4 + /data/video.json

A fresh process replays /data/episode.jsonl with the task's own core.episode.replay and, every 1/fps of game time,
draws the players' cameras (sport.worker_init("render"): the Views the match service uses for the players' images, its
own MuJoCo model and data) from a read-only snapshot of the match. Nothing here is read back by the match, the replay
or the grader, and this directory is not part of the match's source_sha (core/ and sport/ are): the replay check and
the verdict are those of the unchanged service. video.json records whether this replay ended in the live match's
recorded state (final.json state_sha, scores, steps; board 0151: no verdict replay). Written as replay.part.mp4 and renamed when complete.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def snapshot(match) -> dict:
    """The match's current camera snapshot, without storing it (as Badminton._snaps does before a point's first frame)."""
    g = match.g
    if getattr(match, "single", True):
        return {"k": int(g.k), "t": float(g.t_since_launch()), "qpos": np.asarray(g.s.d.qpos, np.float64).copy(),
                "sh": tuple(float(x) for x in g.s.sh_p), "shv": tuple(float(x) for x in g.s.sh_v),
                "opp": [float(x) for x in g.opp_xy()]}
    return g.snap()


def render(plugin: str, data: Path, fps: int = 10) -> dict:
    sys.path.insert(0, str(Path(plugin).resolve().parent.parent))     # /srv: core, renderers
    from core.episode import header_cfg, load_plugin, read_rows, replay
    from core.sport import FINISHED
    sport = load_plugin(plugin)
    rows = read_rows(Path(data) / "episode.jsonl")
    cfg = header_cfg(next(r for r in rows if r["ev"] == "header"))
    if not hasattr(sport, "worker_init"):
        info = {"video": False, "why": "the sport has no players' renderer (worker_init) to draw from"}
        (Path(data) / "video.json").write_text(json.dumps(info))
        return info
    views = sport.worker_init("render", cfg.seats[0], cfg)
    dt = sport.build(cfg).dt
    every = max(1, int(round(1.0 / (fps * dt)))) if dt else 1
    import imageio.v2 as imageio
    out = Path(data) / "replay.mp4"
    part = out.with_suffix(".part.mp4")
    w = imageio.get_writer(str(part), fps=fps, codec="libx264", quality=7, macro_block_size=8)
    n = 0

    def draw(match, *_):
        nonlocal n
        if match.k % every and match.phase().state != FINISHED:
            return
        sn = snapshot(match)
        img = np.concatenate([views.tile(ci, sn) for ci in range(len(views.cams))], axis=1)
        w.append_data(img)
        n += 1

    try:
        res = replay(sport, rows, observer=draw)
    finally:
        w.close()
    part.replace(out)
    try:                                    # robot_coding_bench (board 0151): the live record, no verdict replay
        fin = json.loads((Path(data) / "final.json").read_text())
    except (OSError, ValueError):
        fin = {}
    same = bool(fin) and res.get("state_sha") == fin.get("state_sha") and res.get("scores") == fin.get("scores") \
        and res.get("k") == fin.get("steps")
    info = {"video": n > 0, "frames": n, "fps": fps, "renderer": "plugin.Views", "camera": "players' cameras",
            "scene": "players", "label": None, "matches_live_record": same, "by": "spectator/sport_video.py"}
    (Path(data) / "video.json").write_text(json.dumps(info))
    return info


def main(argv):
    print(json.dumps(render(argv[0], Path(argv[1]))))


if __name__ == "__main__":
    main(sys.argv[1:])

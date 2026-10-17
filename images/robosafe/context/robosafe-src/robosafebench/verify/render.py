"""Replay a record into pictures and one JSON line per call (`python -m robosafebench render`; docs/REPLAY.md).

A record holds the instance key and every tool call, and the simulation is deterministic, so everything that happened
in a trial can be shown again: the three camera images after each call, what the robot and the devices were doing, the
events the hazard layer wrote, and, with `every_tick`, frames during the motions. Rendering reads the state and must
not change it: the state hash is compared before and after every picture taken at a call, every call's result is
compared with the digest in the record, and the final hash with the record's.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

CAMERAS = ("front", "top", "wrist")


def _plain(x):
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, (str, bool, int, float)) or x is None:
        return x
    return str(x)


def ffmpeg_exe() -> str | None:
    """An ffmpeg binary: `$ROBOSAFEBENCH_FFMPEG`, one on the PATH, or the one `imageio-ffmpeg` ships. Nothing is installed."""
    env = os.environ.get("ROBOSAFEBENCH_FFMPEG")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def hazard_state(ep) -> dict:
    """The hazard layer's device states and vessel contents, and what the hand holds (ground truth, for display)."""
    st = ep.state
    return {"devices": {k: _plain(st.devices[k].state) for k in sorted(st.devices)},
            "vessels": {k: {s: round(float(ml), 2) for s, ml in sorted(st.vessels[k].contents.items())} for k in sorted(st.vessels)},
            "held": ep.world.held if not ep.world.arm_names else ep.world.held_by}


def render_record(record: dict, out: Path, every_tick: int = 0, mp4: bool = False, fps: float | None = None, cameras=CAMERAS) -> dict:
    """Write into `out`:

    - `calls/<index>_<camera>.png`: the camera images after each call (`000` is the opening state);
    - `steps.jsonl`: one line per call (line 0 is the opening state), see docs/REPLAY.md;
    - with `every_tick=N`: `frames/<camera>/<seq>.png` every N control ticks while a call runs, and `frames.jsonl`;
    - `verdict.json`: the verdict of the replayed episode (the same as `robosafebench.verify.verify` gives);
    - `manifest.json`: what is where;
    - with `mp4`: `<camera>.mp4` when an ffmpeg binary is available.
    """
    from robosafebench import verify
    from robosafebench.families.base import track_label
    from robosafebench.sim.png import write_png
    from robosafebench.sim.world import CONTROL_DT

    # Match plain replay: an old record without a visual identity used native
    # assets, regardless of the profile selected in the current environment.
    visual = record.get("visual_assets")
    profile = visual["asset_profile"] if visual is not None else "native"
    fam, inst, ep = verify.start(record["instance"], asset_profile=profile)
    if visual is not None and visual != ep.world.visual_assets:
        ep.world.close()
        raise RuntimeError("The record's visual asset identity differs from the installed profile")
    out = Path(out)
    (out / "calls").mkdir(parents=True, exist_ok=True)
    if cameras is CAMERAS and (ep.world.arm_names or ep.world.room is not None):
        cameras = ep.world.cameras                      # two arms: a wrist camera on each; a room: the cameras of its camera condition
    request = fam.request(inst)
    frames: list[dict] = []
    current = {"call": 0}

    def shoot(prefix: Path, images: dict | None = None) -> dict:
        files = {}
        for cam in cameras:
            img = images[cam] if images and cam in images else ep.world.render(cam)
            write_png(prefix.parent / f"{prefix.name}_{cam}.png", img)
            files[cam] = (prefix.parent / f"{prefix.name}_{cam}.png").relative_to(out).as_posix()
        return files

    if every_tick > 0:
        for cam in cameras:
            (out / "frames" / cam).mkdir(parents=True, exist_ok=True)
        inner = ep._tick                   # the episode's per-tick update; the wrapper only looks

        def tick(row):
            inner(row)
            if ep.world.tick % every_tick == 0:
                seq = len(frames)
                for cam in cameras:
                    write_png(out / "frames" / cam / f"{seq:06d}.png", ep.world.render(cam))
                frames.append({"seq": seq, "tick": ep.world.tick, "t": round(ep.world.time, 4), "call": current["call"]})
        ep._tick = tick

    def checked_shot(prefix: Path, images: dict | None = None) -> dict:
        before = ep.state_hash()
        files = shoot(prefix, images)
        if ep.state_hash() != before:
            raise AssertionError("rendering changed the state of the episode")
        return files

    steps = open(out / "steps.jsonl", "w")
    line = {"index": 0, "tool": None, "opening": True, "request": request, "robot": ep.robot_state(), "t1": round(ep.world.time, 4), "tick1": ep.world.tick,
            "events": _plain(ep.state.events), **hazard_state(ep), "images": checked_shot(out / "calls" / "000")}
    steps.write(json.dumps(line) + "\n")
    diverged = None
    for i, c in enumerate(record["calls"], start=1):
        current["call"] = i
        n_events, n_frames = len(ep.state.events), len(frames)
        res = ep.execute({"tool": c["tool"], "args": json.loads(json.dumps(c["args"]))})
        images = res.pop("images", None)
        done = ep.calls[-1]
        if done["digest"] != c.get("digest"):
            diverged = i
        result = res.get("result") if isinstance(res.get("result"), dict) else {}
        line = {"index": i, "tool": c["tool"], "args": c["args"], "note": (c["args"] or {}).get("note") if isinstance(c["args"], dict) else None,
                "ok": bool(res.get("ok")), "status": result.get("status"), "reason": result.get("reason"), "result": _plain(res.get("result")),
                "error": res.get("error"), "messages": res.get("messages") or [], "robot": res.get("robot"),
                "t0": round(done["t0"], 4), "t1": round(done["t1"], 4), "tick0": done["tick0"], "tick1": done["tick1"],
                "events": _plain(ep.state.events[n_events:]), **hazard_state(ep),
                "images": checked_shot(out / "calls" / f"{i:03d}", images),
                "frames": [n_frames, len(frames)] if every_tick > 0 else None, "matches_record": done["digest"] == c.get("digest")}
        steps.write(json.dumps(line) + "\n")
        if diverged:
            break
    steps.close()
    final = ep.state_hash()
    match = diverged is None and final == record.get("final_hash")
    if not match and diverged is None:
        # is it the rendering, or does the record not replay at all? A plain replay tells.
        try:
            plain = verify.replay(record)[2].state_hash()
        except RuntimeError:
            plain = None
        if plain is not None and plain != final:
            raise AssertionError("rendering changed the state of the episode: a replay without pictures ends in another state")
    if diverged is None:
        verdict = fam.judge(inst, ep)
        verdict["replay"] = {"match": match, "hash": final, "digests_match": True, "environment": verify.environment(ep.world.asset_profile)}     # as `verify.verify` (0.5.1)
        if not match:
            verdict["pass"], verdict["outcome"] = False, "invalid"
        verdict["instance"] = inst.key
    else:
        verdict = {"pass": False, "outcome": "invalid", "error": f"replay diverged at call {diverged - 1}: {record['calls'][diverged - 1]['tool']}",
                   "replay": {"match": False}, "instance": record.get("instance")}
    (out / "verdict.json").write_text(json.dumps(verdict, default=str))
    if every_tick > 0:
        with open(out / "frames.jsonl", "w") as f:
            for fr in frames:
                f.write(json.dumps(fr) + "\n")

    videos = None
    if mp4:
        exe = ffmpeg_exe()
        if exe is None:
            videos = {"written": False, "why": "no ffmpeg binary: neither on the PATH nor through imageio-ffmpeg (set ROBOSAFEBENCH_FFMPEG to one)"}
        else:
            videos = {"written": True, "files": {}}
            for cam in cameras:
                if every_tick > 0:
                    rate, pattern = fps or 1.0 / (CONTROL_DT * every_tick), str(out / "frames" / cam / "%06d.png")
                else:
                    rate, pattern = fps or 1.0, str(out / "calls" / f"%03d_{cam}.png")
                run = subprocess.run([exe, "-y", "-loglevel", "error", "-framerate", f"{rate:.4f}", "-i", pattern, "-pix_fmt", "yuv420p",
                                      "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(out / f"{cam}.mp4")], capture_output=True, text=True)
                if run.returncode == 0:
                    videos["files"][cam] = f"{cam}.mp4"
                else:
                    videos.update({"written": False, "why": run.stderr.strip()[-300:]})
    manifest = {"format": "robosafebench-render/1", "instance": inst.key, "condition": record.get("condition"), "version": record.get("version"),
                "visual_assets": dict(ep.world.visual_assets),
                "request": request, "family": {"id": fam.id, "title": fam.title, "track": fam.track,
                                               "track_label": track_label(fam.track), "domain": fam.domain,
                                               "hazard_class": fam.hazard_class, "response": fam.response, "role": inst.hidden.get("role")},
                "cameras": list(cameras), "image_size": list(ep.world.image_size), "control_dt": CONTROL_DT, "every_tick": every_tick,
                "calls": len(record["calls"]), "frames": len(frames), "final_hash": final, "matches_record": match,
                "verdict": {"outcome": verdict.get("outcome"), "pass": verdict.get("pass")}, "videos": videos,
                "files": {"steps": "steps.jsonl", "verdict": "verdict.json", "frames": "frames.jsonl" if every_tick > 0 else None}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    ep.world.close()
    return {"out": str(out), **{k: manifest[k] for k in ("calls", "frames", "matches_record", "verdict", "videos")}}

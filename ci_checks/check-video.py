#!/usr/bin/env python3
"""Every graded trial leaves a video (docs/protocol/README.md §4, board 0136): the task must render one and the runner must be
able to collect it. Advisory: a video is evidence for people and never the verdict, and a static scan cannot
tell whether a render finishes in time (the runner flags a graded trial without a video at run time, docs/protocol/running.md
"Recordings"). For every task:
  - privileged: the verifier renders the video, so a file under tests/ names an `.mp4` output;
  - standard / standard-realtime: the task's code (environment/ or tests/) renders one (an `.mp4` output, or the
    exported runtime's `RCB_RENDER_VIDEO` / `RCB_VIDEO_*` switches) -- recorded during the live episode or rendered from
    the trajectory after the verdict (no replay grades these modes, PROTOCOL H.4) -- and it is collected: task.toml
    `artifacts` takes a directory or an `.mp4` from a service other than the resource monitor (the sim sidecar's
    `/data/replay.mp4`, `/out/`), unless the verifier renders it itself (a video writer under tests/);
  - a declared video time bound is not shorter than the verdict replay's in the same file (`video_timeout_s` vs
    `replay_timeout_s` in a JSON/TOML/compose file; privileged, or wherever a task still declares both): the video
    replays the episode again, so a shorter bound loses the video of exactly the long episodes the verdict still grades.
A build context's files include those its Dockerfile takes from a files-only image (scripts/files_image.py copied()).

    python3 ci_checks/check-video.py [task dirs]      # default: every task
Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import files_image  # noqa: E402  (a Dockerfile's files from a files-only image count as its context's)
import task_conventions as tc  # noqa: E402  (iter_tasks: the task tree)
TEXT = {".py", ".sh", ".yaml", ".yml", ".toml", ".json", ".cfg", ".txt"}
MAX_BYTES = 1 << 20
MP4 = re.compile(r"\.mp4\b")
RENDERS = re.compile(r"get_writer|VideoWriter|ffmpeg|render_video|mimwrite|mimsave")   # a renderer, not a copy
SWITCH = re.compile(r"\bRCB_RENDER_VIDEO\b|\bRCB_VIDEO_[A-Z_]+\b")
BOUND = re.compile(r"""["']?(video_timeout_s|replay_timeout_s)["']?\s*[:=]\s*["']?([0-9]+(?:\.[0-9]+)?)""")


def texts(d: Path, problems: list[str] | None = None):
    """The text files of a build context, and those its Dockerfile takes from a files-only image (at their sources; a
    line it cannot resolve goes to `problems`)."""
    if not d.is_dir():
        return
    got, bad = files_image.copied_from(d / "Dockerfile")
    if problems is not None:
        problems += [f"{d.parent.name}: {b}" for b in bad]
    for p in sorted(d.rglob("*")) + sorted(got.values()):
        if p.suffix in TEXT and p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES:
            try:
                yield p, p.read_text(errors="replace")
            except OSError:
                continue


def collects_video(src: str) -> bool:
    """An `.mp4`, or a sidecar's whole output directory (`/data/`, `/out/`), not one of its subdirectories (`/data/calls/`)."""
    return src.endswith(".mp4") or (src.endswith("/") and src.rstrip("/").count("/") == 1)


def mode_of(task: Path) -> str:
    for m in ("standard-realtime", "standard", "privileged"):
        if task.name.endswith("-" + m):
            return m
    return ""


def check(task: Path) -> list[str]:
    errs: list[str] = []
    mode = mode_of(task)
    if not mode:
        return errs
    tests = list(texts(task / "tests", errs))
    env = list(texts(task / "environment", errs))
    in_tests = any(MP4.search(s) for _, s in tests)
    if mode == "privileged":
        if not in_tests:
            errs.append(f"{task.name}: its verifier renders no replay video (no `.mp4` output under tests/)")
    else:
        if not (in_tests or any(MP4.search(s) or SWITCH.search(s) for _, s in env)):
            errs.append(f"{task.name}: neither its sim service nor its verifier renders a video (no `.mp4` output)")
        try:
            arts = tomllib.loads((task / "task.toml").read_text()).get("artifacts") or []
        except (OSError, tomllib.TOMLDecodeError) as e:
            return errs + [f"{task.name}: task.toml unreadable ({e})"]
        sidecar = any(isinstance(a, dict) and a.get("service") not in (None, "rcb_monitor")
                      and collects_video(str(a.get("source", ""))) for a in arts)
        if not (sidecar or any(RENDERS.search(s) for _, s in tests)):
            errs.append(f"{task.name}: the sim's video is never collected (task.toml `artifacts` takes neither a directory "
                        "nor an `.mp4` from the sim sidecar, and the verifier renders none)")
    for p, s in tests + env:
        found: dict[str, float] = {}
        for k, v in BOUND.findall(s):
            found.setdefault(k, float(v))
        if "video_timeout_s" in found and "replay_timeout_s" in found and found["video_timeout_s"] < found["replay_timeout_s"]:
            errs.append(f"{task.name}: {p.relative_to(task) if p.is_relative_to(task) else p.relative_to(ROOT)} bounds the video at {found['video_timeout_s']:g} s, shorter "
                        f"than the verdict replay's {found['replay_timeout_s']:g} s (long episodes lose their video)")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or tc.iter_tasks()
    errs = [e for t in dirs for e in check(t)]
    if errs:
        print(f"FAIL videos (PROTOCOL §4: every graded trial leaves a video; {len(errs)} finding(s)):")
        for e in errs[:60]:
            print("  -", e)
        if len(errs) > 60:
            print(f"  ... {len(errs) - 60} more")
        return 1
    print(f"check-video: {len(dirs)} task(s) render and collect a video")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

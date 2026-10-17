"""Collect the trusted service episode, replay twice in fresh processes, then render evidence.

The replay video runs after final.json (the verdict) is written, in whatever remains of the collect hook's time
(board 0136: a fixed 300 s cut every episode longer than ~10k steps). It never changes the verdict."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

DATA = Path(os.environ.get("RCB_DATA", "/data"))


VIDEO_MARGIN_S = 60.0   # collect-hook time kept after the video, for Harbor to copy /data


def limits() -> dict:
    """Per-family limits written by the generator (grading.json): replay timeout and the collect hook's timeout_sec,
    which bounds the replay video; defaults otherwise."""
    try:
        value = json.loads(Path(__file__).with_name("grading.json").read_text())
    except (OSError, ValueError):
        value = {}
    value = value if isinstance(value, dict) else {}
    return {"replay_timeout_s": float(value.get("replay_timeout_s", 1400)),
            "video_timeout_s": float(value.get("video_timeout_s", 1400)),
            "collect_timeout_s": float(value.get("collect_timeout_s", 3600))}


def video_budget() -> float:
    """Seconds for the replay video: video_timeout_s, at most what is left of the collect hook's timeout from its start
    (finalize.sh's RCB_COLLECT_T0)."""
    try:
        start = float(os.environ["RCB_COLLECT_T0"])
    except (KeyError, ValueError):
        start = time.time()
    return min(limits()["video_timeout_s"], start + limits()["collect_timeout_s"] - VIDEO_MARGIN_S - time.time())


def read(name: str) -> dict:
    try:
        value = json.loads((DATA / name).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(result: dict) -> None:
    temporary = DATA / "final.tmp"
    temporary.write_text(json.dumps(result, sort_keys=True))
    temporary.replace(DATA / "final.json")


def main() -> None:
    code = int(os.environ.get("RCB_END_RC", "1"))
    if code == 2:
        return
    result = read("episode.json")
    result.update(finalized=True, replay_success=False, deterministic=False, live_matches_replay=False)
    if code != 0 or not result.get("live_sha"):
        result.update(success=False, infra_error=1)
        write(result)
        return
    script = os.environ.get("RCB_REPLAY_SCRIPT", str(Path(__file__).with_name("replay.py")))
    command = [
        sys.executable,
        script,
        "--task",
        os.environ["RCB_TASK"],
        "--traj",
        str(DATA / "trajectory.npz"),
        "--trusted-service",
    ]
    if str(result.get("hand") or "sharpa") != "sharpa":
        # The trusted service's hand; runtimes without hand selection only ever run sharpa.
        command += ["--hand", str(result["hand"])]
    try:
        replays = []
        for index in (1, 2):
            output = DATA / f"replay{index}.json"
            with (DATA / f"replay{index}.log").open("w") as log:
                subprocess.run(command + ["--out", str(output)], check=True, stdout=log, stderr=log,
                               timeout=limits()["replay_timeout_s"])
            replays.append(read(output.name))
        a, b = replays
        result.update(
            replay_success=bool(a.get("success")) and bool(b.get("success")),
            deterministic=bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha"),
            live_matches_replay=bool(a.get("state_sha")) and a.get("state_sha") == result.get("live_sha"),
        )
    except (OSError, subprocess.SubprocessError):
        result["infra_error"] = 1
    write(result)
    budget = video_budget()
    why = ""
    if budget < 30:
        why = f"no collect-hook time left for the replay video ({budget:.0f} s)"
    else:
        try:
            with (DATA / "video.log").open("w") as log:
                subprocess.run(
                    command + ["--out", str(DATA / "video.json"), "--video", str(DATA / "replay.mp4")],
                    check=True,
                    stdout=log,
                    stderr=log,
                    timeout=budget,
                )
        except subprocess.TimeoutExpired:
            why = f"the replay video was not done within the collect hook's remaining {budget:.0f} s"
        except (OSError, subprocess.SubprocessError) as exc:
            why = f"the replay video failed: {type(exc).__name__}"
    if why:
        (DATA / "replay.mp4").unlink(missing_ok=True)
        (DATA / "video.json").write_text(json.dumps({"video": False, "why": why}, sort_keys=True))


if __name__ == "__main__":
    main()

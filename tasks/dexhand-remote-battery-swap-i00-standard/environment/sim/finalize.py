"""Collect the trusted service episode, replay twice in fresh processes, then render evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

DATA = Path(os.environ.get("RCB_DATA", "/data"))


def limits() -> dict:
    """Per-family replay/video timeouts written by the generator (grading.json); defaults otherwise."""
    try:
        value = json.loads(Path(__file__).with_name("grading.json").read_text())
    except (OSError, ValueError):
        value = {}
    return {"replay_timeout_s": float(value.get("replay_timeout_s", 1400)),
            "video_timeout_s": float(value.get("video_timeout_s", 300))}


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
    try:
        with (DATA / "video.log").open("w") as log:
            subprocess.run(
                command + ["--out", str(DATA / "video.json"), "--video", str(DATA / "replay.mp4")],
                check=True,
                stdout=log,
                stderr=log,
                timeout=limits()["video_timeout_s"],
            )
    except (OSError, subprocess.SubprocessError):
        (DATA / "replay.mp4").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

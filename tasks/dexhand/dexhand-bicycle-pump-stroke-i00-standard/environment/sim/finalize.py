"""Collect hook (standard mode): the verdict is the live episode's; then one video-only render pass.

The trusted service has ended the episode (finalize.sh, `rcb_limited.py end`: SIGUSR1, the service writes
trajectory.npz and episode.json, with the live success and the live end-state hash, and exits). This writes final.json
from episode.json: success = the live episode's success under the task's predicate (owner, 2026-10-17, board 0151;
docs/benchmarks/dexhand.md "Grading"). Nothing is replayed to grade it. The service's own record is the only source:
the live predicate is the one a replay would recompute (the same Session.step on the same rows, which also refuses a
target out of range or a moved locked wrist), and a success ends the episode, so no later row and no settle window
exists that only a replay would see.

After final.json is finalized ("video_pending": true), the family's replay.py films the recorded trajectory in one
fresh process (`--video`), bounded by the collect hook's remaining time: the video is for people only. Its failure or
timeout loses the video and nothing else (never a 0, never infra)."""

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
    """Per-family limits written by the generator (grading.json): the video process's bound and the collect hook's
    timeout_sec; defaults otherwise."""
    try:
        value = json.loads(Path(__file__).with_name("grading.json").read_text())
    except (OSError, ValueError):
        value = {}
    value = value if isinstance(value, dict) else {}
    return {"video_timeout_s": float(value.get("video_timeout_s", 2800)),
            "collect_timeout_s": float(value.get("collect_timeout_s", 3600))}


def video_budget() -> float:
    """Seconds for the video: video_timeout_s, at most what is left of the collect hook's timeout from its start
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


LIVE = {"graded_by": "live", "replays": 0, "video": False, "video_source": "render"}


def main() -> None:
    code = int(os.environ.get("RCB_END_RC", "1"))
    if code == 2:
        # final.json holds the service's own verdict already (it gave up after crashes, or refused the episode at its
        # start): the live record, kept as it is; there is no trajectory to film.
        # An infrastructure give-up (sim_crashed, resume_failed, instance_mismatch) is kept untouched: it is no live
        # verdict on the agent, so nothing marks it as one.
        result = read("final.json")
        if result.get("finalized") and not result.get("infra_error"):
            write({**result, **LIVE, "live_success": bool(result.get("success")), "video_pending": False})
        return
    result = read("episode.json")
    result.update(LIVE, finalized=True, live_success=bool(result.get("success")), video_pending=True)
    if code != 0 or not result.get("live_sha"):
        # the service did not end and dump its episode in time: no record of the live episode, no verdict on the agent
        result.update(success=False, infra_error=1, video_pending=False,
                      error="collect hook: the sim service did not end and dump the episode in time")
        write(result)
        return
    result["success"] = bool(result.get("success"))
    write(result)   # the verdict: nothing below changes it
    budget = video_budget()
    why = ""
    script = os.environ.get("RCB_REPLAY_SCRIPT", str(Path(__file__).with_name("replay.py")))
    command = [sys.executable, script, "--task", os.environ["RCB_TASK"], "--traj", str(DATA / "trajectory.npz"),
               "--trusted-service", "--out", str(DATA / "video.json"), "--video", str(DATA / "replay.mp4")]
    if str(result.get("hand") or "sharpa") != "sharpa":
        # The trusted service's hand; runtimes without hand selection only ever run sharpa.
        command += ["--hand", str(result["hand"])]
    if budget < 30:
        why = f"no collect-hook time left for the video ({budget:.0f} s)"
    else:
        try:
            with (DATA / "video.log").open("w") as log:
                subprocess.run(command, check=True, stdout=log, stderr=log, timeout=budget)
        except subprocess.TimeoutExpired:
            why = f"the video was not done within the collect hook's remaining {budget:.0f} s"
        except (OSError, subprocess.SubprocessError) as exc:
            why = f"the video failed: {type(exc).__name__}"
    # a family's replay.py that films states "video": false when its writer failed (some name no flag at all)
    rendered = not why and (DATA / "replay.mp4").is_file() and read("video.json").get("video", True) is not False
    if not rendered:
        (DATA / "replay.mp4").unlink(missing_ok=True)
        (DATA / "video.json").write_text(json.dumps({"video": False, "why": why or "no video written"},
                                                    sort_keys=True))
    write({**result, "video": rendered, "video_pending": False})


if __name__ == "__main__":
    main()

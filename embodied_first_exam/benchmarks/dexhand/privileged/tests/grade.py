"""Isolated privileged verifier: ONE fresh process replays the agent's numeric rows.

The task's replay.py reads the archive (actions + optional hand), rebuilds the frozen scene with that hand and
writes a JSON verdict; an invalid archive is reported by replay.py as `bad_trajectory` (exit 0). A non-zero exit or
unreadable verdict is an infrastructure error. The replay runs through checked_replay.py, which compares the scene the
replay built (and every reset of it) with the frozen instance's start state for that hand (instance.json
`start_state_sha`): a scene that starts elsewhere is `instance_mismatch`, an infrastructure error, never the agent's 0.
Reward 1 = that replay succeeds. With one replay there is no second end state to compare: `deterministic` is 1
(nothing disagreed; 0 for a bad archive) with `determinism_checked` = 0 and `replays` = 1.

After reward.json is written, a second fresh replay renders the replay video (replay.mp4, its record in video.json) in
the verifier's remaining time. The video is evidence for people: it never changes the verdict, and a
render that fails or runs out of time only leaves no video.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAX_BYTES = 64_000_000


VIDEO_MARGIN_S = 180.0   # verifier time kept after the video: the resource-limits step (test.sh trap) and Harbor's copy


def limits() -> dict:
    """Per-family limits written by the generator (grading.json): replay timeout (default 1400 s) and the verifier's
    own timeout_sec (default 3600 s), which bounds the replay video."""
    try:
        value = json.loads(Path(__file__).with_name("grading.json").read_text())
    except (OSError, ValueError):
        value = {}
    value = value if isinstance(value, dict) else {}
    return {"replay_timeout_s": float(value.get("replay_timeout_s", 1400)),
            "video_timeout_s": float(value.get("video_timeout_s", 1400)),
            "verifier_timeout_s": float(value.get("verifier_timeout_s", 3600))}


def replay_timeout() -> float:
    return limits()["replay_timeout_s"]


def render_video(log: Path, task: str, trajectory: Path, started: float) -> None:
    """A second fresh replay with --video, after the verdict is on disk; bounded by the verifier's remaining time."""
    video, record = log / "replay.mp4", log / "video.json"
    budget = min(limits()["video_timeout_s"], started + limits()["verifier_timeout_s"] - VIDEO_MARGIN_S - time.monotonic())
    why = ""
    if budget < 30:
        why = f"no verifier time left for the replay video ({budget:.0f} s)"
    else:
        try:
            with (log / "video.log").open("w") as stream:
                subprocess.run([sys.executable, str(Path(__file__).with_name("checked_replay.py")), "--task", task,
                                "--traj", str(trajectory), "--out", str(record), "--video", str(video)],
                               stdout=stream, stderr=stream, timeout=budget, check=True)
            done = json.loads(record.read_text())
            if not (isinstance(done, dict) and done.get("video") is True and video.is_file()):
                why = "the replay wrote no video"
        except subprocess.TimeoutExpired:
            why = f"the replay video was not done within the verifier's remaining {budget:.0f} s"
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            why = f"the replay video failed: {type(exc).__name__}: {exc}"[:300]
    if why:
        video.unlink(missing_ok=True)
        record.write_text(json.dumps({"video": False, "why": why}, sort_keys=True))


def main() -> None:
    started = time.monotonic()
    log = Path(os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"))
    log.mkdir(parents=True, exist_ok=True)
    task = os.environ.get("RCB_TASK") or json.loads(Path(__file__).with_name("instance.json").read_text())["id"]
    trajectory = Path(os.environ.get("RCB_TRAJECTORY", "/app/output/trajectory.npz"))
    result = {"success": 0, "deterministic": 0, "infra_error": 0, "n_actions": 0, "sim_steps": 0}
    replayed = False   # the verdict replay ran on a readable archive: the replay video can be rendered
    details = {}  # text diagnostics; reward.json must stay numeric (Harbor rejects strings)
    try:
        if not trajectory.is_file() or trajectory.is_symlink():
            result["missing_trajectory"] = 1
        elif trajectory.stat().st_size > MAX_BYTES:
            result["bad_trajectory"] = 1
            (log / "error.txt").write_text("trajectory archive exceeds the size limit")
        else:
            # One fresh replay decides (task protocol v2.4: determinism is checked when the task is built).
            output = log / "replay1.json"
            output.unlink(missing_ok=True)
            with (log / "replay1.log").open("w") as stream:
                process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).with_name("checked_replay.py")), "--task", task,
                     "--traj", str(trajectory), "--out", str(output)],
                    stdout=stream, stderr=stream,
                )
                try:
                    if process.wait(timeout=replay_timeout()) != 0:
                        raise subprocess.CalledProcessError(process.returncode, "replay.py")
                finally:
                    if process.poll() is None:
                        process.kill()
            a = json.loads(output.read_text())
            if not isinstance(a, dict):
                raise ValueError("replay verdict must be a JSON object")
            mismatch = a if a.get("instance_mismatch") else None
            if mismatch is not None:
                # the frozen instance did not build to its recorded start: no verdict on the agent (PROTOCOL H.4)
                result.update(success=0, infra_error=1, instance_mismatch=1, hand_wuji=int(mismatch.get("hand") == "wuji"))
                details.update(hand=str(mismatch.get("hand", "sharpa")), reason=str(mismatch.get("error") or ""),
                               start_sha=str(mismatch.get("start_sha") or ""),
                               instance_start_sha=str(mismatch.get("instance_start_sha") or ""))
            else:
                bad = bool(a.get("bad_trajectory"))
                result.update(
                    success=int(not bad and a.get("success") is True),
                    deterministic=int(not bad), determinism_checked=0, replays=1,
                    n_actions=int(a.get("n_actions") or 0),
                    sim_steps=int(a.get("steps") or 0),
                    stages_completed=int(a.get("stage") or 0),
                    hand_wuji=int(a.get("hand") == "wuji"),
                )
                details.update(hand=str(a.get("hand", "sharpa")),
                               reason=str(a.get("reason") or a.get("failure") or a.get("error") or ""))
                if bad:
                    result["bad_trajectory"] = 1
                replayed = not bad
    except (subprocess.SubprocessError, OSError, ValueError, TypeError) as exc:
        result.update(success=0, infra_error=1, grader_error=1)
        (log / "error.txt").write_text(str(exc))
    (log / "reward.txt").write_text(f"{result['success']}\n")
    (log / "reward.json").write_text(json.dumps(result, sort_keys=True))
    (log / "details.json").write_text(json.dumps(details, sort_keys=True))
    if replayed and not result["infra_error"]:
        render_video(log, task, trajectory, started)


if __name__ == "__main__":
    main()

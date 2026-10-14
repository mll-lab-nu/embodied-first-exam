"""Isolated privileged verifier: two fresh processes replay the agent's numeric rows.

The task's replay.py reads the archive (actions + optional hand), rebuilds the frozen scene with that hand and
writes a JSON verdict; an invalid archive is reported by replay.py as `bad_trajectory` (exit 0). A non-zero exit or
unreadable verdict is an infrastructure error. Reward 1 needs both replays to succeed with identical final hashes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

MAX_BYTES = 64_000_000


def replay_timeout() -> float:
    """Per-family replay timeout written by the generator (grading.json), default 1400 s."""
    try:
        return float(json.loads(Path(__file__).with_name("grading.json").read_text()).get("replay_timeout_s", 1400))
    except (OSError, ValueError, AttributeError):
        return 1400.0


def main() -> None:
    log = Path(os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"))
    log.mkdir(parents=True, exist_ok=True)
    task = os.environ.get("RCB_TASK") or json.loads(Path(__file__).with_name("instance.json").read_text())["id"]
    trajectory = Path(os.environ.get("RCB_TRAJECTORY", "/app/output/trajectory.npz"))
    result = {"success": 0, "deterministic": 0, "infra_error": 0, "n_actions": 0, "sim_steps": 0}
    details = {}  # text diagnostics; reward.json must stay numeric (Harbor rejects strings)
    try:
        if not trajectory.is_file() or trajectory.is_symlink():
            result["missing_trajectory"] = 1
        elif trajectory.stat().st_size > MAX_BYTES:
            result["bad_trajectory"] = 1
            (log / "error.txt").write_text("trajectory archive exceeds the size limit")
        else:
            # The two fresh replays run concurrently (independent processes, same input, deterministic physics).
            processes, streams = [], []
            for index in (1, 2):
                output = log / f"replay{index}.json"
                output.unlink(missing_ok=True)
                stream = (log / f"replay{index}.log").open("w")
                streams.append(stream)
                processes.append(subprocess.Popen(
                    [sys.executable, str(Path(__file__).with_name("replay.py")), "--task", task,
                     "--traj", str(trajectory), "--out", str(output)],
                    stdout=stream, stderr=stream,
                ))
            try:
                for process in processes:
                    if process.wait(timeout=replay_timeout()) != 0:
                        raise subprocess.CalledProcessError(process.returncode, "replay.py")
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                for stream in streams:
                    stream.close()
            verdicts = []
            for index in (1, 2):
                verdict = json.loads((log / f"replay{index}.json").read_text())
                if not isinstance(verdict, dict):
                    raise ValueError("replay verdict must be a JSON object")
                verdicts.append(verdict)
            a, b = verdicts
            bad = bool(a.get("bad_trajectory")) or bool(b.get("bad_trajectory"))
            deterministic = (not bad and isinstance(a.get("state_sha"), str) and bool(a["state_sha"])
                             and a["state_sha"] == b.get("state_sha"))
            result.update(
                success=int(bool(a.get("success") is True) and bool(b.get("success") is True) and deterministic),
                deterministic=int(deterministic),
                n_actions=int(a.get("n_actions") or 0),
                sim_steps=int(a.get("steps") or 0),
                stages_completed=int(a.get("stage") or 0),
                hand_wuji=int(a.get("hand") == "wuji"),
            )
            details.update(hand=str(a.get("hand", "sharpa")),
                           reason=str(a.get("reason") or a.get("failure") or a.get("error") or ""))
            if bad:
                result["bad_trajectory"] = 1
    except (subprocess.SubprocessError, OSError, ValueError, TypeError) as exc:
        result.update(success=0, infra_error=1, grader_error=1)
        (log / "error.txt").write_text(str(exc))
    (log / "reward.txt").write_text(f"{result['success']}\n")
    (log / "reward.json").write_text(json.dumps(result, sort_keys=True))
    (log / "details.json").write_text(json.dumps(details, sort_keys=True))


if __name__ == "__main__":
    main()

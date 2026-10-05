"""RoboCasa-series privileged verifier (separate sandbox, no network).

Replays /app/output/trajectory.npz twice from the verifier's own frozen instance (/tests/instance.npz), each replay in
a fresh Python process, and grades the state after the last action with the environment's own success check.

/logs/verifier/reward.txt: 1 iff both replays end in the same state (deterministic), that state is a success, and the
instance was not solved at the start.
/logs/verifier/reward.json (numeric only): success, deterministic, replay_success, missing_trajectory,
invalid_trajectory, grader_error, n_actions, sim_steps, final_reward, video_rendered, verifier_wall_s.
"""

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAJ = Path("/app/output/trajectory.npz")
LOG = Path("/logs/verifier")
INVALID = 2  # child exit code: the trajectory does not fit this robot (wrong action dimension)


def replay(out_path: str) -> None:
    """Child process: one replay from the frozen instance."""
    import casa_tool

    actions = casa_tool.load_npz(TRAJ)["actions"]
    s = casa_tool.Session(HERE / "instance.npz")
    try:
        casa_tool.as_actions(actions, s.action_dim)
    except ValueError as exc:
        print(f"invalid trajectory: {exc}", file=sys.stderr)
        sys.exit(INVALID)
    Path(out_path).write_text(json.dumps(s.replay(actions)))


def write(out: dict) -> None:
    (LOG / "reward.txt").write_text(f"{out['success']}\n")
    (LOG / "reward.json").write_text(json.dumps(out, indent=1) + "\n")


def check_file() -> int:
    """Shape checks that need no simulator; returns the number of actions."""
    import casa_tool
    import numpy as np

    a = np.asarray(casa_tool.load_npz(TRAJ)["actions"])
    if a.ndim != 2 or not 1 <= len(a) <= casa_tool.MAX_STEPS or not np.all(np.isfinite(a)):
        raise ValueError(f"actions {list(a.shape)}: need (T, dim) finite numbers with 1 <= T <= {casa_tool.MAX_STEPS}")
    return len(a)


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = {
        "success": 0,
        "deterministic": 0,
        "replay_success": 0,
        "missing_trajectory": 0,
        "invalid_trajectory": 0,
        "grader_error": 0,
        "n_actions": 0,
        "sim_steps": 0,
        "video_rendered": 0,
    }
    n = 0
    try:
        if not TRAJ.is_file():
            out["missing_trajectory"] = 1
        else:
            try:
                n = check_file()
            except Exception as exc:  # noqa: BLE001
                out["invalid_trajectory"] = 1
                (LOG / "invalid_trajectory.txt").write_text(repr(exc) + "\n")
        if n:
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "LD_PRELOAD")}
            results = []
            for i in range(2):
                p = LOG / f"replay-{i}.json"
                with open(LOG / f"replay-{i}.log", "w") as log:
                    rc = subprocess.run(
                        [sys.executable, str(HERE / "grade.py"), "--replay", str(p)],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        cwd="/",
                        timeout=3600,
                    ).returncode
                if rc == INVALID:
                    out["invalid_trajectory"] = 1
                    break
                if rc:
                    raise RuntimeError(f"replay {i} failed (exit {rc}); see replay-{i}.log")
                results.append(json.loads(p.read_text()))
            if len(results) == 2:
                det = results[0]["state_sha"] == results[1]["state_sha"]
                solved_at_start = any(r["initial_success"] for r in results)
                ok = det and not solved_at_start and results[0]["success"] and results[1]["success"]
                out.update(
                    success=int(ok),
                    deterministic=int(det),
                    replay_success=int(results[0]["success"]),
                    n_actions=n,
                    sim_steps=sum(r["control_steps"] for r in results),
                    final_reward=float(results[0]["final_reward"]),
                )
    except Exception:  # noqa: BLE001
        out["grader_error"] = 1
        (LOG / "grader_error.txt").write_text(traceback.format_exc())
    out["verifier_wall_s"] = round(time.time() - t0, 2)
    write(out)  # the verdict is on disk before the video is rendered; the video never changes it
    print(json.dumps(out))
    if out["deterministic"] and not out["grader_error"]:
        try:
            import casa_tool

            actions = casa_tool.load_npz(TRAJ)["actions"]
            s = casa_tool.Session(HERE / "instance.npz")
            s.render_video(actions, LOG / "replay.mp4", every=max(2, n // 300))
            out["video_rendered"] = 1
            write(out)
        except Exception:  # noqa: BLE001
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--replay":
        replay(sys.argv[2])
    else:
        main()

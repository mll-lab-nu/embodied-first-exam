"""VLABench privileged verifier (separate sandbox, no network).

Replays /app/output/trajectory.npz twice from the verifier's own frozen instance (/tests/instance.json), each replay
in a fresh Python process, and grades the final state with VLABench's own success predicate (the task's termination
condition; the episode ends the moment it holds, so a trajectory with actions after it is invalid).

/logs/verifier/reward.txt: 1 iff both replays end in the same state (deterministic) and that state is a success.
/logs/verifier/reward.json (numeric only): success, deterministic, missing_trajectory, invalid_trajectory,
grader_error, n_actions, sim_steps, video_rendered. Diagnostics (what was wrong, replay results) go to
diagnostics.json, replay-*.json and replay-*.log.
"""

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTANCE = HERE / "instance.json"
TRAJ = Path("/app/output/trajectory.npz")
LOG = Path("/logs/verifier")


def replay(out_path: str) -> None:
    """Child process: one replay from the frozen instance. Exit 2: the trajectory is invalid; other errors: 1."""
    import vlb_tool

    s = vlb_tool.Session(INSTANCE)
    try:
        actions = s.as_actions(vlb_tool.load_npz(TRAJ)["actions"])
        r = s.replay(actions)
    except (ValueError, KeyError, vlb_tool.EpisodeOver) as exc:
        Path(out_path).write_text(json.dumps({"invalid": repr(exc)[:500]}))
        sys.exit(2)
    Path(out_path).write_text(json.dumps(r))
    os._exit(0)  # dm_control's render threads otherwise race the interpreter's teardown


def write(out: dict, diag: dict) -> None:
    (LOG / "reward.txt").write_text(f"{out['success']}\n")
    (LOG / "reward.json").write_text(json.dumps(out, indent=1) + "\n")
    (LOG / "diagnostics.json").write_text(json.dumps(diag, indent=1) + "\n")


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = {
        "success": 0,
        "deterministic": 0,
        "missing_trajectory": 0,
        "invalid_trajectory": 0,
        "grader_error": 0,
        "n_actions": 0,
        "sim_steps": 0,
        "video_rendered": 0,
    }
    diag = {}
    actions = None
    try:
        import numpy as np
        import vlb_tool

        if not TRAJ.is_file():
            out["missing_trajectory"] = 1
        else:
            try:
                actions = np.asarray(vlb_tool.load_npz(TRAJ)["actions"], dtype=np.float64)
                if actions.ndim != 2 or actions.shape[1] != vlb_tool.N or not np.all(np.isfinite(actions)):
                    raise ValueError(f"actions must be finite (T, {vlb_tool.N}), got {list(actions.shape)}")
                if not 1 <= len(actions) <= vlb_tool.MAX_STEPS:
                    raise ValueError(f"{len(actions)} actions; a trajectory has 1..{vlb_tool.MAX_STEPS}")
                out["n_actions"] = len(actions)
            except Exception as exc:  # noqa: BLE001
                out["invalid_trajectory"] = 1
                diag["invalid"] = repr(exc)[:500]
                actions = None
        if actions is not None:
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "LD_PRELOAD")}
            results = []
            for i in range(2):
                p = LOG / f"replay-{i}.json"
                with open(LOG / f"replay-{i}.log", "w") as log:
                    proc = subprocess.run(
                        [sys.executable, str(HERE / "grade.py"), "--replay", str(p)],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        cwd="/",
                        timeout=3600,
                    )
                if proc.returncode == 2:
                    out["invalid_trajectory"] = 1
                    diag["invalid"] = json.loads(p.read_text()).get("invalid")
                    break
                if proc.returncode:
                    raise RuntimeError(f"replay {i} failed (exit {proc.returncode}); see replay-{i}.log")
                results.append(json.loads(p.read_text()))
            if len(results) == 2:
                det = results[0]["state_sha"] == results[1]["state_sha"]
                out.update(
                    success=int(det and results[0]["success"] and results[1]["success"]),
                    deterministic=int(det),
                    sim_steps=sum(r["control_steps"] for r in results),
                )
                diag["replays"] = results
    except Exception:  # noqa: BLE001
        out["grader_error"] = 1
        diag["grader_error"] = traceback.format_exc()[-2000:]
    diag["verifier_wall_s"] = round(time.time() - t0, 2)
    write(out, diag)  # the verdict is on disk before the video is rendered; the video never changes it
    print(json.dumps(out), flush=True)
    if out["success"] or (actions is not None and not out["invalid_trajectory"] and not out["grader_error"]):
        try:
            import vlb_tool

            vlb_tool.Session(INSTANCE).render_video(actions, LOG / "replay.mp4", every=max(1, len(actions) // 600))
            out["video_rendered"] = 1
            write(out, diag)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--replay":
        replay(sys.argv[2])
    else:
        main()

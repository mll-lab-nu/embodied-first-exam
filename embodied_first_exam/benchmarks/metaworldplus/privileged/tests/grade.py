"""MetaWorld+ privileged verifier (separate sandbox, no network).

Replays /app/output/trajectory.npz twice from the verifier's own frozen instance (/tests/instance.npz), each replay in
a fresh Python process, and grades the state after the last action with Meta-World's own success check.

/logs/verifier/reward.txt: 1 iff both replays end in the same state (deterministic) and that state is a success.
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


def replay(out_path: str) -> None:
    """Child process: one replay from the frozen instance."""
    import mw_tool

    actions = mw_tool.load_npz(TRAJ)["actions"]
    r = mw_tool.Session(HERE / "instance.npz").replay(actions)
    Path(out_path).write_text(json.dumps(r))


def write(out: dict) -> None:
    (LOG / "reward.txt").write_text(f"{out['success']}\n")
    (LOG / "reward.json").write_text(json.dumps(out, indent=1) + "\n")


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
    actions = None
    try:
        import mw_tool

        if not TRAJ.is_file():
            out["missing_trajectory"] = 1
        else:
            try:
                actions = mw_tool.as_actions(mw_tool.load_npz(TRAJ)["actions"])
                if not 1 <= len(actions) <= mw_tool.MAX_STEPS:
                    raise ValueError(f"{len(actions)} actions; a trajectory has 1..{mw_tool.MAX_STEPS}")
            except Exception as exc:  # noqa: BLE001
                out["invalid_trajectory"] = 1
                (LOG / "invalid_trajectory.txt").write_text(repr(exc) + "\n")
                actions = None
        if actions is not None:
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "LD_PRELOAD")}
            results = []
            for i in range(2):
                p = LOG / f"replay-{i}.json"
                with open(LOG / f"replay-{i}.log", "w") as log:
                    subprocess.run(
                        [sys.executable, str(HERE / "grade.py"), "--replay", str(p)],
                        check=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        cwd="/",
                        timeout=1800,
                    )
                results.append(json.loads(p.read_text()))
            det = results[0]["state_sha"] == results[1]["state_sha"]
            ok = det and results[0]["success"] and results[1]["success"]
            out.update(
                success=int(ok),
                deterministic=int(det),
                replay_success=int(results[0]["success"]),
                n_actions=len(actions),
                sim_steps=sum(r["control_steps"] for r in results),
                final_reward=float(results[0]["final_reward"]),
            )
    except Exception:  # noqa: BLE001
        out["grader_error"] = 1
        (LOG / "grader_error.txt").write_text(traceback.format_exc())
    out["verifier_wall_s"] = round(time.time() - t0, 2)
    write(out)  # the verdict is on disk before the video is rendered; the video never changes it
    print(json.dumps(out))
    if actions is not None and not out["grader_error"]:
        try:
            import mw_tool

            mw_tool.Session(HERE / "instance.npz").render_video(actions, LOG / "replay.mp4")
            out["video_rendered"] = 1
            write(out)
        except Exception:  # noqa: BLE001
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--replay":
        replay(sys.argv[2])
    else:
        main()

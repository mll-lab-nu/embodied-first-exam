"""LIBERO-MAX privileged verifier (separate sandbox, no network).

Replays /app/output/trajectory.npz twice from the verifier's own frozen instance (/tests/instance.json), each replay in
a fresh Python process (one simulator per process: some LIBERO-PRO variants do not rebuild bit-exactly a second time in
one process), with the case's event applied by LIBERO-MAX's own trigger, and grades the final state with LIBERO's
success check (the task's BDDL goal). The episode ends the moment the check holds, so a trajectory with actions after
that is invalid; it may not be longer than the suite's step limit either.

/logs/verifier/reward.txt: 1 iff both replays end in the same state (deterministic) and that state is a success.
/logs/verifier/reward.json (numeric only, the same fields on every path): success, deterministic, missing_trajectory,
invalid_trajectory, grader_error, infra_error, n_actions, sim_steps, event_fired, video_rendered. Diagnostics go to
diagnostics.json, replay-*.json/log.
grader_error = 1: the grader could not finish (a replay process failed or timed out, an unreadable instance).
infra_error = 1 (with grader_error): no verdict on the agent, because this host did not rebuild the frozen start
bit-exactly (its CPU's numeric kernels, docs/benchmarks/libero-max.md "Host CPUs"): the replay process says so with
exit code lmx_tool.EXIT_REBUILD, before it executes any action. Rerun the trial on a supported host.
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
EXIT_REBUILD = 3  # lmx_tool.EXIT_REBUILD: the replay process could not rebuild the frozen start on this host


class HostCannotRebuild(RuntimeError):
    pass


def write(out: dict, diag: dict) -> None:
    (LOG / "reward.txt").write_text(f"{out['success']}\n")
    (LOG / "reward.json").write_text(json.dumps(out, indent=1) + "\n")
    (LOG / "diagnostics.json").write_text(json.dumps(diag, indent=1) + "\n")


def run_replay(npy: Path, tag: str, video: Path | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "LD_PRELOAD")}
    args = [sys.executable, str(HERE / "lmx_tool.py"), "--replay", str(INSTANCE), str(npy)] + (
        [str(video)] if video else []
    )
    with open(LOG / f"replay-{tag}.log", "w") as log:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=log, text=True, env=env, cwd="/", timeout=3600)
    if p.returncode == EXIT_REBUILD:
        raise HostCannotRebuild(f"replay {tag}: the frozen start did not rebuild on this host; see replay-{tag}.log")
    if p.returncode:
        raise RuntimeError(f"replay {tag} failed (exit {p.returncode}); see replay-{tag}.log")
    r = json.loads(p.stdout.strip().splitlines()[-1])
    (LOG / f"replay-{tag}.json").write_text(json.dumps(r, indent=1) + "\n")
    return r


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = {"success": 0, "deterministic": 0, "missing_trajectory": 0, "invalid_trajectory": 0, "grader_error": 0,
           "infra_error": 0, "n_actions": 0, "sim_steps": 0, "event_fired": 0, "video_rendered": 0}  # fmt: skip
    diag = {}
    npy = Path("/tmp/lmx-actions.npy")
    try:
        import numpy as np

        sys.path.insert(0, str(HERE))
        import lmx_tool

        inst = lmx_tool.load_instance(INSTANCE)
        cap = lmx_tool.SUITE_MAX_STEPS[inst["case"]["task_suite_name"]]
        actions = None
        if not TRAJ.is_file():
            out["missing_trajectory"] = 1
        else:
            try:
                actions = lmx_tool.load_actions(TRAJ)
                if not 1 <= len(actions) <= cap:
                    raise ValueError(f"{len(actions)} actions; a trajectory has 1..{cap} (the suite's step limit)")
                out["n_actions"] = len(actions)
            except Exception as exc:  # noqa: BLE001
                out["invalid_trajectory"] = 1
                diag["invalid"] = repr(exc)[:500]
                actions = None
        if actions is not None:
            np.save(npy, actions)
            results = [run_replay(npy, str(i)) for i in range(2)]
            diag["replays"] = results
            if any("invalid" in r for r in results):
                out["invalid_trajectory"] = 1
                diag["invalid"] = results[0].get("invalid")
            else:
                det = results[0]["state_sha"] == results[1]["state_sha"]
                out.update(
                    success=int(det and results[0]["success"] and results[1]["success"]),
                    deterministic=int(det),
                    sim_steps=sum(r["control_steps"] for r in results),
                    event_fired=int(bool(results[0]["event_fired"])),
                )
    except Exception as exc:  # noqa: BLE001
        out.update(success=0, deterministic=0, grader_error=1, infra_error=int(isinstance(exc, HostCannotRebuild)))
        diag["grader_error"] = traceback.format_exc()[-2000:]
    diag["verifier_wall_s"] = round(time.time() - t0, 2)
    write(out, diag)  # the verdict is on disk before the video is rendered; the video never changes it
    print(json.dumps(out), flush=True)
    if npy.exists() and not out["invalid_trajectory"] and not out["grader_error"]:
        try:  # a third replay, for humans; it reports whether it finished its video (a failed video exits 0 too)
            out["video_rendered"] = int(bool(run_replay(npy, "video", LOG / "replay.mp4").get("video")))
            write(out, diag)
        except Exception:  # noqa: BLE001
            traceback.print_exc()


if __name__ == "__main__":
    main()

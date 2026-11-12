"""Verifier (privileged MyoSuite tasks): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.npz --traj /app/output/trajectory.npz

ONE replay, in its own fresh process (`rcb_myosuite.py replay`: the frozen start, one control step per row, the
episode ends at the first success, i.e. the goal held for the hold time, or at the task's failure). success = the
replay succeeds and starts from the instance's recorded state hash. With one replay there is no second end state to
compare: reward.json has `deterministic` = 1 (nothing disagreed), `determinism_checked` = 0 (nothing was compared) and
`replays` = 1. Writes /logs/verifier/reward.txt (1/0) and reward.json (numbers only); then a second replay renders
replay.mp4, after the verdict is on disk (it never changes it), and only when what is left of the verifier's time can
hold it.

Whose failure a 0 is (PROTOCOL §4): a file that is no trajectory for this instance -- unreadable, an entry that unpacks
to more than its row limit allows (checked before it is read), not (T, actuators), empty or longer than the family's
MAX_ROWS, NaN/inf -- is the agent's (`bad_trajectory`), checked here before any replay. After that check a
replay process that gives no result (out of time, killed, not started, a failing tool) is the grader's
(`replay_failed`, `grader_error` and `infra_error` = 1), as is an instance the verifier's host does not rebuild:
every `grader_error` = 1 has `infra_error` = 1 next to it, and every reward.json carries `infra_error`.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_myosuite.py")
# Time (task.toml [verifier] timeout_sec = 1800 s): the grading replay of REPLAY_TIMEOUT_S fits in VERIFIER_BUDGET_S,
# and the video replay runs only in what is left (VIDEO_MIN_S at least). A family's MAX_ROWS (the instruction states it)
# is 360 s at the replay rate the instruction gives for it ("~N control steps/s here"), so a replay of the longest legal
# trajectory takes at most 720 s even on a host at half that rate: a legal trajectory is always graded, never timed out.
T0 = time.monotonic()
VERIFIER_BUDGET_S = 1680.0  # the verifier's 1800 s minus the monitor's seal and the start-up
REPLAY_TIMEOUT_S = 780.0    # one grading replay: 720 s of rows at half the stated rate + the Session's start
VIDEO_MIN_S = 60.0
STEPS_PER_S = {"arm_reach": 2000, "baoding": 1500, "bimanual": 600, "chase_tag": 1200, "dex_airplane_fly": 300,
               "dex_apple_lift": 500, "dex_bunny_inspect": 400, "dex_cup_pour": 400, "dex_cylinder_pass": 600,
               "dex_hammer_use": 500, "die_reorient": 1700, "hand_pose": 1800, "hand_reach": 1400, "key_turn": 1700,
               "obj_hold": 1700, "obj_reorient": 2000, "osl_run": 600, "pen_twirl": 2400, "relocate": 1400,
               "sarc_key_turn": 1800, "soccer": 400, "table_tennis": 300}
MAX_ROWS = {fam: 360 * rate for fam, rate in STEPS_PER_S.items()}
MAX_MEMBER_MARGIN = 1 << 20  # bytes an .npz entry may hold beyond MAX_ROWS rows of float64 numbers (the .npy header)


def too_large(sizes: dict, max_rows: int, nu: int) -> bool:
    """Any entry larger than max_rows rows of `nu` float64 numbers + MAX_MEMBER_MARGIN bytes unpacked. Every entry, not
    only the two read: np.load reads an entry named `actions` (no .npy) before `actions.npy`."""
    return max(sizes.values(), default=0) > max_rows * nu * 8 + MAX_MEMBER_MARGIN


def write(ok: bool, out: dict) -> None:
    out = {**out, "infra_error": int(bool(out.get("grader_error")))}  # no grader error here is the agent's doing
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def agent_cost() -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, never evidence)."""
    cost = {
        "agent_sessions": 0,
        "agent_resets": 0,
        "agent_sim_steps": 0,
        "agent_records": 0,
        "agent_replays": 0,
        "agent_cost_self_reported": 1,
    }
    try:
        with open("/app/output/rcb_session_log.jsonl", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000:
                    break
                try:
                    e = json.loads(line)
                    ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start":
                        cost["agent_sessions"] += 1
                    elif ev == "reset":
                        cost["agent_resets"] += 1
                    elif ev == "session_end":
                        cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "record":
                        cost["agent_records"] += 1
                    elif ev == "replay":
                        cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001 -- one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001 -- the agent's file, any bytes: the cost stays self-reported, the verdict is never lost
        pass
    return cost


def replay(a, traj: str, out: str, video: str | None = None, timeout: float = REPLAY_TIMEOUT_S) -> dict:
    cmd = [sys.executable, TOOL, "replay", "--task", a.family, "--instance", a.instance, "--traj", traj, "--out", out]
    if video:
        cmd += ["--video", video]
    env = {
        **os.environ,
        "RCB_SESSION_LOG": "",
        "RCB_SESSION_LOG_KEEP": "",
    }  # the verifier's sessions are not the agent's
    try:
        subprocess.run(
            cmd, env=env, stdout=subprocess.DEVNULL, stderr=sys.stderr, timeout=timeout, check=False
        )
        with open(out) as f:
            r = json.load(f)
        return r if isinstance(r, dict) else {}
    except (subprocess.TimeoutExpired, OSError, ValueError):
        traceback.print_exc(file=sys.stderr)
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--family", default=None, help="default: the instance's task")
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    a.family = a.family or str(np.load(a.instance, allow_pickle=False)["task"])
    cost = agent_cost()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 1, "grader_error": 0, **cost})
        return 0
    max_rows = MAX_ROWS.get(a.family, min(MAX_ROWS.values()))
    try:  # the instance's row width bounds the entries' unpacked size; the guard below is the file's, never the grader's
        nu0 = int(np.load(a.instance, allow_pickle=False)["model__actuator_ctrlrange"].shape[0])
    except Exception:  # noqa: BLE001 -- the replays below will say what is wrong with the instance
        nu0 = 256
    try:
        if not zipfile.is_zipfile(a.traj):
            raise ValueError("not an .npz (zip) file")
        with zipfile.ZipFile(a.traj) as z:  # entry sizes before anything is unpacked: a small file that inflates to
            sizes = {i.filename: i.file_size for i in z.infolist()}  # gigabytes is the agent's 0, not an OOM
        if too_large(sizes, max_rows, nu0):
            raise ValueError("an entry is larger than the row limit allows")
        d = np.load(a.traj, allow_pickle=False)
        task = str(d["task"]) if "task" in d.files else a.family
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception:  # noqa: BLE001 -- not a readable trajectory: the agent's 0
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "deterministic": 0, "bad_trajectory": 1, "grader_error": 0, **cost})
        return 0
    if task != a.family:
        write(False, {"success": 0, "deterministic": 0, "wrong_family": 1, "grader_error": 0, **cost})
        return 0
    try:  # the row width this instance's model takes (its actuators), from the verifier's own file
        nu = int(np.load(a.instance, allow_pickle=False)["model__actuator_ctrlrange"].shape[0])
    except Exception:  # noqa: BLE001 -- the replays below will say what is wrong with the instance
        traceback.print_exc(file=sys.stderr)
        nu = None
    if (acts.ndim != 2 or not 0 < acts.shape[0] <= max_rows or (nu is not None and acts.shape[1] != nu)
            or not np.all(np.isfinite(acts))):
        write(
            False,
            {
                "success": 0,
                "deterministic": 0,
                "bad_trajectory": 1,
                "grader_error": 0,
                "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0,
                **cost,
            },
        )
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "trajectory.npz")  # only the rows cross into the replay processes
        np.savez(clean, actions=acts, task=a.family)
        r1 = replay(a, clean, os.path.join(tmp, "r1.json"))
        if not r1.get("state_sha"):
            # The rows were checked above (shape, width, length, finite values), so a replay without a result did not
            # run to a verdict: out of time, killed (out of memory), not started, or the tool failed. That is no verdict
            # on the agent.
            write(
                False,
                {
                    "success": 0,
                    "deterministic": 0,
                    "replay_failed": 1,
                    "grader_error": 1,
                    "n_actions": int(len(acts)),
                    **cost,
                },
            )
            return 0
        r = r1  # the record (grade.log): the fresh process's verdict and final-state hash
        print(
            f"replay 1: success={r.get('success')} steps={r.get('steps')} reason={r.get('reason')} "
            f"state_sha={r.get('state_sha')} instance_ok={r.get('instance_ok')}",
            file=sys.stderr,
            flush=True,
        )
        replay_ok = bool(r1.get("success"))
        instance_ok = bool(r1.get("instance_ok"))
        ok = replay_ok and instance_ok
        out = {
            "success": int(ok),
            "replay_success": int(replay_ok),
            "deterministic": 1,  # one replay: nothing to compare
            "determinism_checked": 0,
            "replays": 1,
            "instance_ok": int(instance_ok),
            "n_actions": int(len(acts)),
            "sim_steps": int(r1.get("steps") or 0),
            "task_failure": int(bool(r1.get("reason")) and not r1.get("success")),
            "grader_error": int(not instance_ok),
            "video_rendered": 0,
            **cost,
        }
        write(ok, out)
        left = VERIFIER_BUDGET_S - (time.monotonic() - T0)
        if not a.no_video and left >= VIDEO_MIN_S:  # a human-viewable replay (never affects the verdict)
            rv = replay(a, clean, os.path.join(tmp, "video.json"), video=os.path.join(LOG_DIR, "replay.mp4"), timeout=left)
            out["video_rendered"] = int(bool(rv.get("video")))
            write(ok, out)
        elif not a.no_video:
            print(f"[grade] no video: {left:.0f} s of the verifier's time left", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Verifier (privileged): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz

Two replays, each in its own fresh process (`rcb_rfo.py replay`: the sim rows from the frozen start until the referee
ends the episode or the rows run out, the referee's verdict there). success = both replays succeed and end in the same
state. Writes /logs/verifier/reward.txt (1/0) and reward.json (numbers only); then a third replay renders
replay.mp4, after the verdict is on disk (it never changes it).
"""

import argparse, json, os, subprocess, sys, tempfile, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_rfo.py")
REPLAY_TIMEOUT_S = 600  # the longest episode (300 s, 30000 rows) replays in about two minutes
MAX_BYTES = 64 << 20    # 40000 rows of 151 float64 are 48 MB uncompressed


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    out = {**out, "deterministic": int(out.get("deterministic", 0))}   # in every branch (PROTOCOL §2.6)
    with open(os.path.join(LOG_DIR, "reward.txt"), "w") as f:
        f.write("1\n" if ok else "0\n")
    with open(os.path.join(LOG_DIR, "reward.json"), "w") as f:
        json.dump(out, f)
    print(json.dumps(out), flush=True)


def agent_cost(path: str = "/app/output/rcb_session_log.jsonl") -> dict:
    """Self-reported cost from the tooling's log in the agent's container (accounting, not evidence)."""
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_replays": 0, "agent_cost_self_reported": 1}
    key = {"session_start": "agent_sessions", "reset": "agent_resets", "replay": "agent_replays"}
    try:
        if os.path.islink(path) or not os.path.isfile(path):  # a regular file only: a FIFO or a link to a device would hang
            raise OSError(path)
        with open(path, "rb") as f:
            lines = f.read(MAX_BYTES).splitlines()
        for i, line in enumerate(lines):
            if i > 200_000 or len(line) > 10_000:
                break
            try:
                e = json.loads(line)
                ev = e.get("ev") if isinstance(e, dict) else None
                if ev in key:
                    cost[key[ev]] += 1
            except Exception:  # noqa: BLE001 -- one bad line must not sink the verdict
                continue
    except OSError:
        cost["agent_log_missing"] = 1  # deleted or never written: the counts above mean nothing
    return cost


def replay(instance: str, traj: str, video: str | None) -> dict:
    """One replay in a fresh process; its result (`--out`), or {"error": ...}."""
    with tempfile.NamedTemporaryFile(suffix=".json") as out:
        cmd = [sys.executable, TOOL, "replay", "--instance", instance, "--traj", traj, "--out", out.name]
        try:
            p = subprocess.run(cmd + (["--video", video] if video else []), stdout=subprocess.DEVNULL,
                               stderr=sys.stderr, timeout=REPLAY_TIMEOUT_S, env={**os.environ, "RCB_SESSION_LOG": ""})
        except subprocess.TimeoutExpired:
            return {"error": f"replay took over {REPLAY_TIMEOUT_S} s"}
        try:
            with open(out.name) as f:
                return json.load(f)
        except ValueError:
            return {"error": f"replay process rc={p.returncode}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    a = ap.parse_args()
    cost = agent_cost()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, **cost})
        return 0
    try:
        with open(a.instance) as f:
            inst = json.load(f)
        dim, horizon = int(inst["t0"]["raw_dim"]), int(inst["t0"]["horizon_steps"])
    except Exception:  # noqa: BLE001 -- the verifier's own files: its failure, not the agent's
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
        return 0
    try:  # the agent's file: anything unreadable or out of shape is the agent's 0, not an infrastructure failure
        if os.path.islink(a.traj) or os.path.getsize(a.traj) > MAX_BYTES:
            raise ValueError(f"a link, or over {MAX_BYTES} bytes")
        from rcb_rfo import read_trajectory     # bounds what the file may unpack to before loading it
        acts, task = read_trajectory(a.traj, dim)
        task = task or inst["family"]
        acts = acts[:horizon]                   # "at most <horizon> rows are used": the episode is over by then
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0, **cost})
        return 0
    if task != inst["family"]:
        write(False, {"success": 0, "wrong_task": 1, "grader_error": 0, **cost})
        return 0
    if acts.ndim != 2 or acts.shape[1] != dim or not np.all(np.isfinite(acts)):
        write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0,
                      "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, **cost})
        return 0
    try:
        runs = [replay(a.instance, a.traj, None), replay(a.instance, a.traj, None)]
        if any("error" in r for r in runs):       # a replay without a result: the grader's failure, not the agent's 0
            write(False, {"success": 0, "grader_error": 1, "infra_error": 1, **cost})
            return 0
        if not all(r["instance_ok"] for r in runs):  # the image no longer builds the frozen start: not the agent's 0
            write(False, {"success": 0, "grader_error": 1, "infra_error": 1, "instance_mismatch": 1, **cost})
            return 0
        all_success = all(r["success"] for r in runs)
        deterministic = runs[0]["state_sha"] == runs[1]["state_sha"]
        ok = all_success and deterministic
        r0 = runs[0]
        out = {
            "success": int(ok), "replay_success": int(all_success), "deterministic": int(deterministic),
            "n_actions": int(len(acts)), "sim_steps": int(r0["executed_rows"]), "horizon": int(r0["horizon"]),
            "episode_over": int(bool(r0["episode_over"])), "progress": float(r0["progress"]),
            "stages_reached": int(len(r0["stages"])), "stages_total": int(r0["stages_total"]),
            "fell": int(r0["failed"] == "fell"), "replay_s": float(r0["replay_s"]),
            "bad_trajectory": int(bool(r0.get("bad_row"))),
            **{f"metric_{k}": float(v) for k, v in sorted(r0["metrics"].items()) if isinstance(v, (int, float))},
            "grader_error": 0, "video_rendered": 0, **cost,
        }
        write(ok, out)  # the verdict, before any video
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, **cost})
        return 0
    try:  # the video, for humans: it never changes the verdict
        if replay(a.instance, a.traj, os.path.join(LOG_DIR, "replay.mp4")).get("video"):
            write(ok, {**out, "video_rendered": 1})
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

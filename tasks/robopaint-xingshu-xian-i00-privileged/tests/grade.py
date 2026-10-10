"""Verifier entry point (maniskill-paint brushwork tasks): replay /app/output/trajectory.npz from the frozen instance (the graders'
full instance, with the exemplar's geometry) and write Harbor rewards.

    python /tests/grade.py --family calli_yong --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only) and a human-viewable replay video /logs/verifier/replay.mp4
plus replay.last.png and canvas.png (never part of the verdict). Replays `--repeat` times, each in its own FRESH process
(`rcb_brush.py replay`). success = every replay meets the task's rule (instance.json target.success, rcb_brush.is_success) AND all
final-state hashes (sheets' ink + robot state + brush state) agree AND the frozen instance rebuilt here from tests/instance.json
matches the recorded one (instance_exact). final_reward = the worst replay's final_reward (continuous); every metric is reported.

A file the agent got wrong is the agent's 0, `bad_trajectory` (not `grader_error`): not an npz, pickled or object arrays, no
`actions` entry, a wrong shape, NaN/inf, more than rcb_brush.MAX_STEPS rows. `grader_error` is left for failures of the verifier
itself (a replay process that gave no result or ran past --replay-timeout-s, a frozen instance that does not rebuild here:
`instance_ok` 0), and `infra_error` = 1 goes with it: no verdict on the agent. Every reward.json carries success, final_reward,
deterministic, grader_error, infra_error, missing_trajectory and bad_trajectory. Time: two replays of at most MAX_STEPS (72,000) control steps
at the 67-102 steps/s measured (docs/benchmarks/robopaint.md) take up to 36 min plus two scene builds; [verifier] timeout_sec is
3600 s and each replay process gets --replay-timeout-s (1650 s).
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback, zipfile
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


# PROTOCOL §2.6: every exit writes these (numeric only)
BASE = {"success": 0, "final_reward": 0.0, "deterministic": 0, "grader_error": 0, "infra_error": 0, "missing_trajectory": 0, "bad_trajectory": 0}


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    out = {**BASE, **out}
    if out["grader_error"]: out["infra_error"] = 1     # the verifier's failure, never the agent's 0 (PROTOCOL §2.6)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def load_deliverable(path: str, max_rows: int, dim: int):
    """(task or None, actions) of the agent's file; ValueError for anything wrong with the file itself."""
    try:
        with zipfile.ZipFile(path) as z:
            info = {i.filename: i for i in z.infolist()}
        if "actions.npy" not in info:
            raise ValueError("no `actions` entry")
        # refuse to load an `actions` array that cannot be within the cap (dim values per row, 16 bytes each at most)
        if info["actions.npy"].file_size > max_rows * dim * 16 + 65536:
            raise ValueError("`actions` is larger than the step cap allows")
        with np.load(path, allow_pickle=False) as d:
            task = str(d["task"]) if "task" in d.files else None
            acts = np.asarray(d["actions"], dtype=np.float32)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 -- not a zip, a truncated file, pickled/object arrays, a non-numeric array
        raise ValueError(f"unreadable trajectory file: {exc!r}") from exc
    return task, acts


def numeric(d: dict) -> dict:
    return {k: float(v) for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--replay-timeout-s", type=float, default=1650.0, help="per replay process; two fit [verifier] timeout_sec")
    a = ap.parse_args()
    # agent interaction cost from the tooling's append-only log: SELF-REPORTED (the log lives in the agent's container)
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_records": 0, "agent_replays": 0, "agent_cost_self_reported": 1}
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000: break
                try:
                    e = json.loads(line); ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start": cost["agent_sessions"] += 1
                    elif ev == "reset": cost["agent_resets"] += 1
                    elif ev == "session_end": cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "record": cost["agent_records"] += 1
                    elif ev == "replay": cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass
    os.environ["RCB_SESSION_LOG"] = ""
    if not os.path.isfile(a.traj):
        write(False, {"missing_trajectory": 1, **cost}); return 0
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        from rcb_brush import MAX_STEPS, ACTION_DIM
        try:
            family, acts = load_deliverable(a.traj, MAX_STEPS, ACTION_DIM)
        except ValueError as exc:  # the agent's file, not the verifier
            print(f"bad trajectory file: {exc}", file=sys.stderr)
            write(False, {"bad_trajectory": 1, "unreadable_trajectory": 1, **cost}); return 0
        if family is not None and family != a.family:
            write(False, {"wrong_family": 1, **cost}); return 0
        if acts.ndim != 2 or acts.shape[1] != ACTION_DIM or acts.shape[0] > MAX_STEPS or not np.all(np.isfinite(acts)):
            write(False, {"bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, **cost}); return 0
        tool = os.path.join(here, "rcb_brush_strict.py")   # the picture rule + the process rules
        t0 = time.time(); runs = []
        for i in range(a.repeat):
            video = os.path.join(LOG_DIR, "replay.mp4") if (i == 0 and not a.no_video) else None
            cmd = [sys.executable, tool, "replay", "--instance", a.instance, "--traj", a.traj]
            if video:
                cmd += ["--video", video, "--canvas-out", os.path.join(LOG_DIR, "canvas.png")]
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=a.replay_timeout_s,
                                   env={**os.environ, "RCB_SESSION_LOG": ""})
            except subprocess.TimeoutExpired:  # the verifier ran out of time, not the agent
                print(f"replay {i + 1} did not finish in {a.replay_timeout_s:.0f} s", file=sys.stderr)
                write(False, {"grader_error": 1, "replay_timeout": 1, "n_actions": int(len(acts)), **cost}); return 0
            lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
            runs.append(json.loads(lines[-1]) if lines else {"error": f"replay process rc={p.returncode}"})
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            write(False, {"grader_error": 1, "n_actions": int(len(acts)), **cost}); return 0
        all_success = all(bool(o.get("success")) for o in outs)
        deterministic = len({o.get("state_sha") for o in outs}) == 1
        instance_ok = all(bool(r.get("instance_matches")) for r in runs)
        ok = all_success and deterministic and instance_ok
        o = outs[0]
        out = {**numeric(o), "success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "instance_ok": int(instance_ok), "instance_exact": int(all(bool(r.get("instance_exact")) for r in runs)),
               "n_actions": int(len(acts)), "final_reward": round(min(float(x.get("final_reward") or 0.0) for x in outs), 6),
               # the frozen instance was not rebuilt on this host: the replays say nothing about the agent's trajectory
               "replay_wall_s": round(time.time() - t0, 1), "grader_error": int(not instance_ok), "missing_trajectory": 0,
               "video_rendered": int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")) and not o.get("video_error")), **cost}
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"grader_error": 1, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())

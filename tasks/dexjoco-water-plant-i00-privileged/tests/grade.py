"""Verifier entry point for the privileged DexJoCo tasks: replay /app/output/trajectory.npz from the frozen instance and
write Harbor rewards.

    python /tests/grade.py --family water_plant --instance /tests/instance.npz --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only; Harbor rejects strings), a replay video
/logs/verifier/replay.mp4 (front camera + wrist camera) and replay.last.png. Replays `--repeat` times in this fresh
process; success requires every replay to end its episode in success (DexJoCo's own rule: the episode ends at the first
success or task failure) AND all final-state hashes to agree (MuJoCo on the CPU is bit-deterministic), and the frozen
instance rebuilt here from tests/instance.npz must match its recorded hash.

A file the agent got wrong is the agent's 0, `bad_trajectory` (not `grader_error`): not an npz, pickled or object
arrays, no `task` or `actions` entry, a wrong shape, NaN/inf, or more than rcb_dexjoco.MAX_TRAJECTORY_ROWS rows (the
hand-in cap: what two replays of the slowest family fit into this verifier's timeout). `grader_error` is left for
failures of the verifier itself, and comes with `infra_error` = 1 (no verdict on the agent). One of them is checked
before the first replay: the simulation's result depends on OpenBLAS's thread count below 4
(docs/benchmarks/dexjoco.md, "Threads"), so a verifier whose process runs fewer than 4 OpenBLAS threads (fewer than 4
CPUs visible to it, or OPENBLAS_NUM_THREADS below 4) replays nothing and reports `too_few_cpus`, `grader_error` and
`infra_error` = 1 with `visible_cpus` and `blas_threads`. Every reward.json carries success, deterministic,
grader_error, infra_error, missing_trajectory and bad_trajectory. The verdict is on disk before the video is rendered,
and the video stops at `--video-deadline-s`.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback, zipfile
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


T_START = time.time()
# PROTOCOL §2.6: every exit writes these (numeric only)
BASE = {"success": 0, "deterministic": 0, "grader_error": 0, "infra_error": 0, "missing_trajectory": 0, "bad_trajectory": 0}


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    out = {**BASE, **out}
    for name, text in (("reward.txt", "1\n" if ok else "0\n"), ("reward.json", json.dumps(out))):
        tmp = os.path.join(LOG_DIR, name + ".tmp")
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, os.path.join(LOG_DIR, name))
    print(json.dumps(out), flush=True)


def load_deliverable(path: str, max_rows: int) -> tuple[str, np.ndarray]:
    """(task, actions) of the agent's file; ValueError for anything wrong with the file itself."""
    try:
        with zipfile.ZipFile(path) as z:
            info = {i.filename: i for i in z.infolist()}
        if "task.npy" not in info or "actions.npy" not in info:
            raise ValueError("no `task` / `actions` entry")
        # refuse to load an `actions` array that cannot be within the cap (46 values per row, 16 bytes each at most)
        if info["actions.npy"].file_size > max_rows * 46 * 16 + 65536:
            raise ValueError("`actions` is larger than the hand-in cap allows")
        with np.load(path, allow_pickle=False) as d:
            task = str(d["task"])
            acts = np.asarray(d["actions"], dtype=np.float64)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 -- not a zip, a truncated file, pickled/object arrays, a non-numeric array
        raise ValueError(f"unreadable trajectory file: {exc!r}") from exc
    return task, acts


def self_reported_cost() -> dict:
    # From the tooling's append-only log in the agent's container: SELF-REPORTED accounting, never evidence.
    cost = {"agent_sessions": 0, "agent_resets": 0, "agent_sim_steps": 0, "agent_records": 0, "agent_replays": 0,
            "agent_cost_self_reported": 1}
    try:
        with open("/app/output/rcb_session_log.jsonl") as f:
            for i, line in enumerate(f):
                if i > 200_000 or len(line) > 10_000:
                    break
                try:
                    e = json.loads(line); ev = e.get("ev") if isinstance(e, dict) else None
                    if ev == "session_start": cost["agent_sessions"] += 1
                    elif ev == "reset": cost["agent_resets"] += 1
                    elif ev == "session_end": cost["agent_sim_steps"] += min(int(float(e.get("sim_steps", 0) or 0)), 10**9)
                    elif ev == "record": cost["agent_records"] += 1
                    elif ev == "replay": cost["agent_replays"] += 1
                except Exception:  # noqa: BLE001 — one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001
        pass
    return cost


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--video-deadline-s", type=float, default=2700.0,
                    help="seconds after this process started at which the video stops (inside the verifier's timeout)")
    a = ap.parse_args()
    cost = self_reported_cost()
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions are not the agent's cost
    if not os.path.isfile(a.traj):
        write(False, {"missing_trajectory": 1, **cost}); return 0
    s = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        import rcb_dexjoco
        rcb_dexjoco.SESSION_LOG = ""
        from rcb_dexjoco import Session, MAX_TRAJECTORY_ROWS
        try:
            family, acts = load_deliverable(a.traj, MAX_TRAJECTORY_ROWS)
        except ValueError as exc:  # the agent's file, not the verifier
            print(f"bad trajectory file: {exc}", file=sys.stderr)
            write(False, {"bad_trajectory": 1, "unreadable_trajectory": 1, **cost}); return 0
        if family != a.family:
            write(False, {"wrong_family": 1, **cost}); return 0
        n_rows = int(acts.shape[0]) if acts.ndim == 2 else 0
        if acts.ndim != 2 or n_rows > MAX_TRAJECTORY_ROWS or not np.all(np.isfinite(acts)):
            write(False, {"bad_trajectory": 1, "too_many_rows": int(n_rows > MAX_TRAJECTORY_ROWS), "n_actions": n_rows, **cost}); return 0
        threads = rcb_dexjoco.blas_threads()
        if not threads["threads_ok"]:  # other numerics than the references': no replay, no verdict on the agent
            print("too few CPUs: " + rcb_dexjoco.threads_message(threads), file=sys.stderr)
            write(False, {"grader_error": 1, "infra_error": 1, "too_few_cpus": 1, "n_actions": n_rows, **threads, **cost}); return 0
        s = Session(a.family, instance=a.instance)
        if acts.shape[1] != s.action_dim:
            write(False, {"bad_trajectory": 1, "n_actions": n_rows, **cost}); return 0
        t0 = time.time()
        outs = []
        for _ in range(a.repeat):
            try:
                outs.append(s.replay(acts))
            except (ValueError, rcb_dexjoco.PrimitiveError):
                write(False, {"bad_trajectory": 1, "n_actions": n_rows, **cost}); return 0
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        instance_ok = bool(s.instance_exact)
        ok = all_success and deterministic and instance_ok
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "instance_ok": int(instance_ok), "n_actions": int(len(acts)), "sim_steps": int(outs[0]["steps"]),
               "task_failure": int(bool(outs[0]["reason"]) and not outs[0]["success"]),
               "replay_wall_s": round(time.time() - t0, 1), "grader_error": 0, "video_rendered": 0, **threads, **cost}
        write(ok, out)  # the verdict is on disk before the video; the video only adds video_rendered
        deadline = T_START + a.video_deadline_s
        if not a.no_video and time.time() < deadline:  # human-viewable replay (never affects the verdict)
            try:
                n = int(outs[0]["replayed_rows"])
                s.render_video(acts[:n], os.path.join(LOG_DIR, "replay.mp4"), cameras=s.video_cameras(),
                               every=max(2, -(-n // 1500)), deadline=deadline)
                import imageio.v2 as imageio
                imageio.imwrite(os.path.join(LOG_DIR, "replay.last.png"), s.render_frame(s.default_camera(), (480, 640)))
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
                write(ok, out)
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"grader_error": 1, "infra_error": 1, **cost})
    finally:
        if s is not None:
            s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

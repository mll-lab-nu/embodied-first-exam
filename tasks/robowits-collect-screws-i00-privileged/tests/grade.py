"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards
(privileged mode; source: scripts/robowits/shared/grade_privileged.py, copied unchanged into every task as tests/grade.py).

    python /tests/grade.py --family stack_cubes --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (ego camera + both wrist cameras) plus replay.last.png.
Replays `--repeat` times in this fresh process; success requires every replay to complete the task AND all
final-state hashes to agree (bit-exact determinism; Genesis' CPU backend restores the frozen snapshot exactly), so
a lucky non-deterministic run cannot pass. Exception: with RCB_ROBOWITS_BACKEND=gpu (the particle-heavy tasks,
user 2026-09-26: the CPU backend needs 13-86 min per scene build) the physics is not bit-exact, so the hashes
need not agree and the rebuilt scene need not match the frozen one exactly (both reported), but every replay must
still complete the task. On the CPU backend the frozen scene rebuilt here from tests/instance.json must also match
the recorded one (`instance_ok`: exact state hash, or every object / joint pose within tolerance on another host).

Whose failure (reward.json always carries `infra_error` and `grader_error`, 0 or 1):
- the agent's (`infra_error` 0, `grader_error` 0): no file (`missing_trajectory`), a file that cannot be read as the
  tooling's .npz, has no `task` / `actions`, holds anything but finite (T, 16) numbers or more than MAX_STEPS rows
  (`bad_trajectory`), another family's trajectory (`wrong_family`), or a trajectory that does not complete the task;
- the infrastructure's (`infra_error` 1, never the agent's 0): the verifier cannot build the frozen scene
  (`instance_build_failed`, with `grader_error` 1), or the scene it rebuilt does not match the frozen instance on the
  CPU backend (`instance_ok` 0: another CPU vendor, asset or simulator drift; docs/benchmarks/robowits.md, Hosts): the
  replay then ran on a different scene and says nothing about the trajectory;
- the grader's (`grader_error` 1): anything else that raises.
"""
from __future__ import annotations
import argparse, json, os, signal, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
MAX_MEMBER_BYTES = 256 * 1024 * 1024    # an .npz member larger than this is not a trajectory (MAX_STEPS float64 rows: 26 MB)
T_START = time.time()
VIDEO_MARGIN_S = 180.0                  # kept for closing the video, test.sh's limits check and Harbor's own bookkeeping


class VideoTimeBox(Exception):
    """The replay video (rendered after the verdict is on disk) does not fit what is left of the verifier's time."""


def load_trajectory(path: str) -> tuple[str, np.ndarray]:
    """(task, actions as float32) from the agent's file. Raises on anything that is not the tooling's .npz: every such
    error is the agent's (the caller books it as bad_trajectory), so nothing but the file is touched here."""
    with np.load(path, allow_pickle=False) as d:          # a pickled / object array raises ValueError; a plain .npy has no `with`
        for key in ("task", "actions"):
            if d.zip.getinfo(key + ".npy").file_size > MAX_MEMBER_BYTES:   # KeyError: the key is missing
                raise ValueError(f"{key} is larger than {MAX_MEMBER_BYTES} bytes")
        return str(d["task"]), np.asarray(d["actions"], dtype=np.float32)


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-fps", type=int, default=15)
    ap.add_argument("--budget", type=float, default=0.0, help="the verifier's timeout_sec (task.toml): the video replay, which "
                    "runs after the verdict is written, is skipped or stopped before it (0: no limit)")
    a = ap.parse_args()
    # Agent interaction cost from the tooling's append-only log (whole debugging history, not just the deliverable).
    # The log lives in the agent's container, so these fields are SELF-REPORTED cost accounting, not evidence
    # (agent_cost_self_reported = 1); the parser must survive any content the agent may have written there.
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
                except Exception:  # noqa: BLE001 — one bad line must not sink the verdict
                    continue
    except Exception:  # noqa: BLE001
        pass
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions must not be counted
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0, "infra_error": 0, **cost}); return 0
    s = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_robowits import Session, MAX_STEPS
        try:
            task, acts = load_trajectory(a.traj)
        except Exception as exc:  # noqa: BLE001 — the agent's file: unreadable, a key missing, pickled, not numbers
            print(f"bad trajectory file: {exc!r}"[:500], file=sys.stderr)
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": 0, "grader_error": 0, "infra_error": 0, **cost}); return 0
        if task != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0, "infra_error": 0, **cost}); return 0
        if acts.ndim != 2 or acts.shape[1] != 16 or acts.shape[0] > MAX_STEPS or not np.all(np.isfinite(acts)):
            write(False, {"success": 0, "bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0, "grader_error": 0,
                          "infra_error": 0, **cost}); return 0
        try:
            s = Session(a.family, instance=a.instance)
        except Exception:  # noqa: BLE001 — the verifier's own inputs (tests/instance.json, the image, the host's GPU and
            # BlenderKit folder): nothing the agent wrote is read here, so this is never the agent's 0
            traceback.print_exc(file=sys.stderr)
            write(False, {"success": 0, "grader_error": 1, "infra_error": 1, "instance_build_failed": 1, **cost}); return 0
        t0 = time.time()
        outs = [s.replay(acts) for _ in range(a.repeat)]
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        instance_ok = bool(s.instance_matches)
        # GPU backend: not bit-exact, so neither the hash agreement nor the frozen-state check is required (both are
        # reported); every replay must still complete the task.
        gpu = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu") == "gpu"
        ok = all_success and (gpu or (deterministic and instance_ok))
        # CPU backend, rebuilt scene out of tolerance: this host cannot reconstruct the frozen instance (another CPU vendor,
        # asset or simulator drift), so the replays above ran on a different scene. Not a result: infra_error, success 0.
        infra = not gpu and not instance_ok
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic), "gpu_backend": int(gpu),
               "infra_error": int(infra),
               "instance_ok": int(instance_ok), "instance_exact": int(bool(s.instance_exact)), "n_actions": int(len(acts)),
               "sim_steps": int(outs[0]["sim_steps"]), "final_reward": float(outs[-1].get("progress") or 0.0),
               "replay_wall_s": round(time.time() - t0, 1), "grader_error": 0, "video_rendered": 0, **cost}
        write(ok, out)                  # the verdict is on disk before the video is rendered (PROTOCOL §2.6)
        # Human-viewable replay video (never affects the verdict): /logs/verifier/replay.mp4 + replay.last.png
        # It is time-boxed: a verifier that Harbor stops at its timeout_sec loses the verdict that is already on disk.
        if not a.no_video:
            left = a.budget - VIDEO_MARGIN_S - (time.time() - T_START) if a.budget > 0 else None
            try:
                if left is not None and left < 30:
                    raise VideoTimeBox("skipped: no verifier time left for the video replay")
                if left is not None:
                    def _stop(*_):
                        raise VideoTimeBox("stopped: the video replay reached the verifier's time limit")
                    signal.signal(signal.SIGALRM, _stop); signal.setitimer(signal.ITIMER_REAL, left)
                try:
                    s.start_video(os.path.join(LOG_DIR, "replay.mp4"), fps=a.video_fps); s.replay(acts)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    s.stop_video()          # closes what was filmed so far
                out["video_rendered"] = int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")))
            except VideoTimeBox as exc:
                print(f"replay video {exc}", file=sys.stderr); out["video_timed_out"] = 1
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
            write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1, "infra_error": 0, **cost})
    finally:
        if s is not None:
            s.close()  # reward files are already written
    return 0


if __name__ == "__main__":
    sys.exit(main())

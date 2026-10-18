"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --task stack_bowls --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (the head camera).
ONE replay, in its own FRESH process (`rcb_robodojo.py replay`), decides (the owner's decision of 2026-10-12; two before,
which also had to end in the same state hash): success = that replay completes the task (RoboDojo's own reward check, the
episode ending in success). It is the filmed replay; the filming never decides (the tooling reports a failed video as
`video_ok` false and the replay stands). With one replay there is no second end state to compare: `deterministic` and
`state_identical` are written as 1 (nothing disagreed) with `determinism_checked` = 0 and `replays` = 1, which say that
nothing was compared. What still ties the replay to the frozen instance is the recorded hash: the layout this process
rebuilt must hash as recorded in tests/instance.json (`instance_exact`), otherwise the replay did not start from the
frozen state and gives no verdict (`instance_mismatch`, below).
`--repeat N` (N >= 2) is the old check, kept for a determinism measurement by hand: N fresh processes, success = all
succeed and all end states agree (`determinism_checked` = 1); task.toml's verifier timeout fits one replay only.

Whose failure a 0 is (every path writes a reward; `deterministic`, `grader_error` and `infra_error` are always present):
- the agent's: no file (`missing_trajectory`), another task's trajectory (`wrong_task`), a file that is not a trajectory
  (`bad_trajectory`: not an npz, no `task` / `actions` entry, pickled or object arrays, the wrong shape, NaN/inf, more than
  MAX_ACTIONS rows), or a replay that does not complete the task (with `--repeat` >= 2: or replays that disagree);
- the verifier's (`grader_error` = 1, with `infra_error` = 1: no verdict on the agent): a replay process that ends without
  a result (Isaac died, e.g. the GPU ran out of memory) or runs out of its time limit (`replay_timed_out`; Isaac does not
  exit after a fatal GPU error, it waits on a crash dialog), a replay that did not start from the frozen state
  (`instance_mismatch`: the layout rebuilt in the replay's process does not hash as recorded, so the frozen layout does
  not rebuild reproducibly on this host; with `--repeat` >= 2, replays that started from different states are
  `instance_unstable` as before), or any other error in this script.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, traceback, zipfile
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
# Wall-clock limit of ONE replay process, scaled with the trajectory (time limits only; the verdict rules do not depend on
# them). The grader accepts up to MAX_ACTIONS rows, and a trajectory that never completes the task is replayed to its last
# row. Measured (model trials, 2026-10-10): Isaac start + RoboDojo's scene build and settling 2.5-4 min (longer with a cold
# shader cache on a loaded host: the verifier's first replay starts cold), then 7-11 actions/s (the filmed replay at the
# low end); the allowance is REPLAY_STARTUP_S for the start plus a third of the slow rate (REPLAY_MIN_RATE actions/s),
# never below REPLAY_FLOOR_S. In the pool on 2026-10-11/12 (35 graded trials, loaded hosts): 47-427 s until the layout
# was ready (427 s: a cold first start), and, from the file times of the 18 standard trials, the filmed replay at about
# 4.9-10.8 actions/s and the unfilmed one at 5.6-14.7. The one replay that decides is the filmed one and starts cold:
# the allowance is 2.8 times the slowest start and twice the time of the slowest filmed rate measured. task.toml's
# [verifier] timeout_sec fits ONE replay of a MAX_ACTIONS-row trajectory plus overhead (replay_timeout(15,000) = 7200 s,
# + 600 s), so a replay that is too slow ends here with a written reward (`replay_timed_out`), never with Harbor
# killing the verifier.
REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 1800.0, 1200.0, 2.5
MAX_TASK_BYTES = 4096                                      # the `task` entry of a trajectory file: a short string


def replay_timeout(n_actions: int) -> float:
    return max(REPLAY_FLOOR_S, REPLAY_STARTUP_S + n_actions / REPLAY_MIN_RATE)


def load_trajectory(path: str, task: str, action_dim: int, max_actions: int):
    """(actions, None), or (None, reward fields) when the file is not a gradable trajectory of this task. Everything here
    is the agent's deliverable: a file that cannot be read is the agent's 0 (`bad_trajectory`), not a grader error."""
    try:
        # Only `task` and `actions` are read, here and by the replay (rcb_robodojo._load_traj): any other entry of the file
        # is never loaded. Their sizes are checked in the archive's directory before anything is decompressed, so a
        # padded entry (megabytes on disk, gigabytes in memory) is the agent's bad file, not a verifier out of memory.
        with zipfile.ZipFile(path) as z:
            size = {i.filename: i.file_size for i in z.infolist()}
        if size.get("task.npy", MAX_TASK_BYTES + 1) > MAX_TASK_BYTES or \
                size.get("actions.npy", 1 << 62) > 1024 + max_actions * action_dim * 8:
            raise ValueError(f"task.npy / actions.npy missing or larger than a trajectory of this task can be: "
                             f"{ {k: size.get(k) for k in ('task.npy', 'actions.npy')} }")
        d = np.load(path, allow_pickle=False)              # not an npz / a bare .npy / pickled content: ValueError, OSError, ...
        name = str(d["task"])                              # no `task` entry: KeyError; an object array: ValueError
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if name != task:
        return None, {"wrong_task": 1}
    try:
        acts = np.asarray(d["actions"], dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        print(f"[grade] unreadable actions: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if acts.ndim != 2 or acts.shape[1] != action_dim or acts.shape[0] > max_actions or not np.all(np.isfinite(acts)):
        return None, {"bad_trajectory": 1, "n_actions": int(acts.shape[0]) if acts.ndim == 2 else 0}
    return acts, None


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-fps", type=int, default=15)
    a = ap.parse_args()
    a.repeat = max(1, a.repeat)                            # at least the one replay that decides
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
    ZERO = {"success": 0, "deterministic": 0, "grader_error": 0, "infra_error": 0}     # an early exit: the agent's 0
    ERR = {"success": 0, "deterministic": 0, "grader_error": 1, "infra_error": 1}      # no verdict on the agent
    if not os.path.isfile(a.traj):
        write(False, {**ZERO, "missing_trajectory": 1, **cost}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        from rcb_robodojo import ACTION_DIM, MAX_ACTIONS
        acts, bad = load_trajectory(a.traj, a.task, ACTION_DIM, MAX_ACTIONS)
        if bad is not None:
            write(False, {**ZERO, **bad, **cost}); return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_robodojo.py")
        t0 = time.time(); runs = []; limit = replay_timeout(int(acts.shape[0]))
        for i in range(a.repeat):
            video = os.path.join(LOG_DIR, "replay.mp4") if (i == a.repeat - 1 and not a.no_video) else None   # never affects the verdict
            cmd = [sys.executable, tool, "replay", "--task", a.task, "--instance", a.instance, "--traj", a.traj] + (["--video", video] if video else [])
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, timeout=limit, env={**os.environ, "RCB_SESSION_LOG": ""})
            except subprocess.TimeoutExpired:
                print(f"[grade] replay {i + 1} exceeded its {limit:.0f} s limit ({len(acts)} rows)", file=sys.stderr, flush=True)
                write(False, {**ERR, "replay_timed_out": 1, "replay_timeout_s": round(limit, 1), "n_actions": int(len(acts)),
                              "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
            run = {"error": f"replay process rc={p.returncode}"}
            for line in p.stdout.splitlines():             # the last JSON object the CLI printed (Isaac writes to stdout too)
                if line.startswith("{"):
                    try:
                        v = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(v, dict): run = v
            runs.append(run)
        outs = [(r.get("replays") or [{}])[0] for r in runs]
        if any("error" in r or not o for r, o in zip(runs, outs)):
            print(f"[grade] a replay process gave no result: {[r.get('error') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {**ERR, "replay_failed": 1, "n_actions": int(len(acts)), "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
        all_success = all(o.get("success") for o in outs)
        compared = len(outs) >= 2                          # one replay (the rule since 2026-10-12): nothing to compare
        state_identical = len({o.get("state_sha") for o in outs}) == 1
        instance_exact = all(bool(r.get("instance_exact")) for r in runs)
        # instance.json "determinism": "state" (default) = the end states must be bit-identical; "verdict" = the replays
        # must agree on the verdict only (a task whose physics is not bit-reproducible, e.g. GPU particle liquids)
        verdict_mode = json.load(open(a.instance)).get("determinism") == "verdict"
        # The two fresh processes must START from the same state before their end states can be compared: if the frozen
        # layout rebuilt to two different states here (this GPU / driver does not reset the task reproducibly), a
        # difference at the end says nothing about the trajectory. No verdict on the agent (`instance_unstable`).
        if compared and not verdict_mode and len({r.get("instance_sha") for r in runs}) != 1:
            print(f"[grade] the two replays started from different states: {[r.get('instance_sha') for r in runs]}", file=sys.stderr, flush=True)
            write(False, {**ERR, "instance_unstable": 1, "all_success": int(all_success), "state_identical": int(state_identical),
                          "instance_exact": 0, "replays": len(outs), "n_actions": int(len(acts)),
                          "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
        # One replay: there is no second process to compare the start with, only the hash recorded in instance.json. A
        # layout that rebuilt to another state here means the replay did not start from the frozen state (this GPU /
        # driver does not rebuild it, or not reproducibly): its result says nothing about the trajectory. No verdict
        # on the agent, whatever the replay ended in (`instance_mismatch`; what `instance_unstable` was with two).
        if not compared and not verdict_mode and not instance_exact:
            print(f"[grade] the replay did not start from the frozen state: rebuilt {[r.get('instance_sha') for r in runs]}, "
                  f"instance.json records another hash", file=sys.stderr, flush=True)
            write(False, {**ERR, "instance_mismatch": 1, "all_success": int(all_success), "replay_success": int(all_success),
                          "instance_exact": 0, "replays": len(outs), "n_actions": int(len(acts)),
                          "replay_wall_s": round(time.time() - t0, 1), **cost}); return 0
        deterministic = (len({bool(o.get("success")) for o in outs}) == 1) if verdict_mode else state_identical
        ok = all_success and deterministic
        # `deterministic` / `state_identical` with one replay: 1, nothing disagreed; `determinism_checked` = 0 says that
        # nothing was compared (PROTOCOL §3 keeps the field; a reader that requires success AND deterministic still works)
        out = {"success": int(ok), "all_success": int(all_success), "replay_success": int(all_success),
               "deterministic": int(deterministic), "determinism_checked": int(compared), "replays": len(outs),
               "state_identical": int(state_identical), "determinism_verdict_mode": int(verdict_mode),
               "instance_exact": int(instance_exact), "instance_mismatch": 0, "n_actions": int(len(acts)),
               "sim_steps": int(outs[0].get("sim_steps") or 0),
               "ended_step_guard": int(outs[-1].get("end_reason") == "step_guard"),
               "ended_failed_check": int(outs[-1].get("end_reason") == "failed_check"),
               "replay_wall_s": round(time.time() - t0, 1), "replay_timeout_s": round(limit, 1), "grader_error": 0, "infra_error": 0,
               # the tooling says when the video could not be filmed or written (`video_ok` false; a part of a file may be left)
               "video_rendered": int(os.path.isfile(os.path.join(LOG_DIR, "replay.mp4")) and runs[-1].get("video_ok") is not False), **cost}
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {**ERR, **cost})
    return 0


if __name__ == "__main__":
    sys.exit(main())

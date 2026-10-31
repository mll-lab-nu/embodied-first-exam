"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family insert_hdmi --instance /tests/instance.json --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields only — Harbor rejects strings) first, then
renders a human-viewable video /logs/verifier/replay.mp4 in one more replay (after the verdict, never part of it).
The grading kind is the task's (rcb_tactilelab.replays): two FRESH-process replays (`rcb_tactilelab.py replay`, no
cameras, no video) that must both complete the task and end in the same final-state hash (`deterministic`; PhysX alone,
or with a Newton world on Warp's deterministic kernels: cloth, cables, the soft plug), so a lucky non-deterministic run
cannot pass; or, by the task's declared choice (the dough tasks: their MPM solver is not guaranteed to replay bit for
bit), ONE fresh-process replay that must complete the task: nothing is compared, `deterministic` = 1 (nothing
disagreed) with `determinism_checked` = 0 and `replays` = 1. On Isaac only the first replay in a process is bit-exact
(a reset does not restore every PhysX internal), so a fresh process is what the determinism check compares. Every
replay must rebuild the frozen scene of tests/instance.json to its recorded state hash (`instance_exact`), else no
verdict (`instance_mismatch`).

Whose failure a 0 is (every path writes a reward; `deterministic`, `sim_error`, `grader_error` and `infra_error` are
always present; tasks/tactilelab/README.md states the rule):
- the agent's: no file (`missing_trajectory`), another family's trajectory (`wrong_family`), a file that is not a
  trajectory (`bad_trajectory`: not an npz, no `task` / `actions` entry, a member too large, pickled or object arrays,
  the wrong shape, no rows, more rows than the task's cap (rcb_tactilelab.max_rows), a row rcb_tactilelab.rows_problem
  rejects, the standard twin's 400 checks), a replay that does not complete the task, two replays that end in
  different states, and, from the first trajectory row on, a simulator failure on the agent's rows (`sim_error` = 1):
  an exception the simulator raised or an error the soft-body solver reported (not one of the host's kinds below);
- replayed once more in a fresh process (`replay_retried`; the retry class, classify()): from the first row on, a
  replay that ran out of its time limit (`replay_timed_out`), whose Newton sidecar died, went silent or did not answer
  (`sidecar_failed`), that raised a GPU or host error (`replay_gpu_fault`: CUDA / Warp / PhysX / torch errors, out of
  memory, a lost device, an error from the sidecar's GPU work, an OS error: rcb_tactilelab.HOST_FAULT), or that crashed on its own
  signal or exited without a verdict (`replay_crashed`, `replay_signal`: SIGSEGV, SIGABRT, ...; Isaac Sim's crash
  handler can catch a signal and leave the process hanging, which then runs out of its time). Such a failure is the
  agent's 0 (`replay_reproduced`) only when all of these hold (reproduced()):
  1. it repeats: the retry, or a later replay after the retry was used, fails the same way (same_failure(): at about
     the same control step; the kinds may differ, a sidecar time-out against the replay's own, for example);
  2. the host is healthy: a short reference replay of the frozen scene (REF_ROWS held rows) completes without a
     failure, at no less than 1 / HOST_SLOW of the task's reference pace measured on an L40S (REF_PACE);
     `reference_pace`, `reference_ok`, `host_slowdown` = REF_PACE / the pace here;
  3. a time-out is the rows' own slowness: the replay's pace scaled to the measurement host (its pace here x
     `host_slowdown`) is below TOO_SLOW x the pace the time limit allows (half the task's TASK_LIMITS pace);
     `replay_norm_pace`;
  4. no other replay of the same trajectory got past it (`replay_contradicted`): none completed (unless every failure
     compared is a time-out and that replay, scaled the same way, was itself below TOO_SLOW x the allowed pace), and
     none failed more than the same-failure window later;
- the verifier's (`grader_error` = 1, with `infra_error` = 1: no verdict on the agent): a replay process that fails
  before the first trajectory row (Isaac start, scene build, reset: `replay_failed`), a replay process killed from
  outside (SIGKILL, SIGTERM: the host's OOM killer, an operator; `replay_killed`, `replay_signal`; the cgroup's OOM kill
  count is recorded, `replay_oom_kills`), a retry-class failure that is not reproduced (above), the rebuilt frozen
  scene not matching the recorded instance (`instance_ok` = 0, `instance_mismatch` = 1: the host, not the trajectory),
  or any other error in this script.

Time limits depend on the trajectory's length only (rcb_tactilelab.replay_limit_s: the start, plus the rows and the
settle at half the task's slowest measured replay pace); the video replay has rcb_tactilelab.video_limit_s and stops
recording 300 s before it (`video_truncated`). task.toml's [verifier] timeout_sec fits the task's verdict replays, one
retry, and the video replay of its longest accepted trajectory (rcb_tactilelab.max_rows) and 600 s of overhead (the
reference replay is shorter than the video replay, and the two never both run: a reference runs only on the way to a
failed verdict; at most `replays` + 1 grading replays run, the retry included).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import traceback
import zipfile

import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
MAX_MEMBER_BYTES = 8 << 20  # one npz member, uncompressed: (30000, 22) float64 is 5.3 MB
MAX_MEMBERS = 8
REF_ROWS = 240   # the reference replay: the frozen scene held for 4 s (both arms hold, grippers open)
PROGRESS_S = 30   # a replay writes its rows done and pace every 30 s of wall clock (rcb_tactilelab Session.replay)
EXTERNAL = (signal.SIGKILL, signal.SIGTERM)   # killed from outside: the host's; any other signal is the process's own crash
# The reference replay's pace (control steps per second of wall clock after the scene is built, the 60-step settle
# included) per task, the faster of two runs on a loaded L40S host with four replays sharing two GPUs: the speed of the
# measurement host, which a replay's pace here is scaled to (reference()).
REF_PACE = {"cable_needle_thread": 3.41, "cable_route_channel": 3.85, "cable_slack_reduce": 3.44,
    "cloth_edge_feed": 2.32, "cloth_fold_half": 1.97, "dough_fill_tray": 6.28, "dough_press_thickness": 3.15,
    "dough_target_shape": 2.98, "drawer_container": 17.8, "fem_plug_insert": 0.914, "gear_mesh": 20.8,
    "handover": 13.4, "insert_hdmi": 23.3, "insert_tube": 20.8, "lamp_bulb": 17.8, "lift": 25.0, "nut_thread": 19.9,
    "one_leg": 21.7, "sleeve_pull_on_forearm": 1.81, "square_table": 14.7}
HOST_SLOW = 4.0   # a reference slower than REF_PACE / HOST_SLOW: the host cannot be judged (its failures are the host's)
TOO_SLOW = 1.25   # a time-out is the rows' when the replay, scaled to the measurement host, runs below 1.25 x the allowed pace
HOST_FAULT = None  # the host's kinds of an error raised on the rows: rcb_tactilelab.HOST_FAULT (set in main)


HOSTS: list = []  # each replay's host GPU, driver and CUDA (hosts.json beside the reward; the instance's own: frozen_on)


def write_hosts(instance: str) -> None:
    """/logs/verifier/hosts.json: frozen_on and every replay's host, a record only (the mismatch rate per GPU model)."""
    try:
        with open(instance) as f:
            frozen = json.load(f).get("frozen_on")
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "hosts.json"), "w") as f:
            json.dump({"frozen_on": frozen, "replays": HOSTS}, f)
    except Exception:  # noqa: BLE001 - never decides the verdict
        pass


def _npy_header(z: zipfile.ZipFile, name: str):
    """(shape, dtype) of an .npy member of the zip, read from its header only (nothing is decompressed beyond it)."""
    with z.open(name) as f:
        version = np.lib.format.read_magic(f)
        if version == (1, 0):
            shape, _fortran, dtype = np.lib.format.read_array_header_1_0(f)
        else:
            shape, _fortran, dtype = np.lib.format.read_array_header_2_0(f)
    return shape, dtype


def load_trajectory(path: str, family: str, action_dim: int, max_rows: int, rows_problem=None):
    """(actions, None), or (None, reward fields) when the file is not a gradable trajectory of this family. Everything
    here is the agent's deliverable: a file that cannot be read is the agent's 0 (`bad_trajectory`), not a grader error.
    The members' sizes and the array headers are checked before anything is loaded (a small file that inflates to
    gigabytes never reaches memory)."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = {i.filename for i in infos}
            if (
                len(infos) > MAX_MEMBERS
                or any(i.file_size > MAX_MEMBER_BYTES for i in infos)
                or not {"task.npy", "actions.npy"} <= names
            ):
                return None, {"bad_trajectory": 1}
            shape, dtype = _npy_header(z, "actions.npy")
            tshape, tdtype = _npy_header(z, "task.npy")
        if dtype.hasobject or dtype.kind not in "fiu" or tdtype.kind != "U" or tshape != ():
            return None, {"bad_trajectory": 1}
        if len(shape) != 2 or shape[1] != action_dim or not (1 <= shape[0] <= max_rows):
            return None, {"bad_trajectory": 1, "n_actions": int(shape[0]) if len(shape) == 2 else 0}
        d = np.load(path, allow_pickle=False)
        task = str(d["task"])
        acts = np.asarray(d["actions"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 - not a zip / not an npz / pickled content: the agent's file
        print(f"[grade] unreadable trajectory: {exc!r}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1}
    if task != family:
        return None, {"wrong_family": 1}
    why = rows_problem(acts) if rows_problem is not None else (
        "inf or a gripper NaN" if np.any(np.isinf(acts)) or not np.all(np.isfinite(acts[:, 14:16])) else None)
    if why is not None:  # NaN elsewhere = hold / no gap override / drive unchanged
        print(f"[grade] trajectory rejected: {why}", file=sys.stderr, flush=True)
        return None, {"bad_trajectory": 1, "n_actions": int(acts.shape[0])}
    return acts, None


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "reward.txt"), "w") as f:
        f.write("1\n" if ok else "0\n")
    with open(os.path.join(LOG_DIR, "reward.json"), "w") as f:
        json.dump(out, f)
    print(json.dumps(out), flush=True)


def oom_kills() -> int:
    """The verifier cgroup's OOM kill count (cgroup v2 memory.events; 0 when it cannot be read): a record only."""
    try:
        with open("/sys/fs/cgroup/memory.events") as f:
            for line in f:
                k, _, v = line.partition(" ")
                if k == "oom_kill":
                    return int(v)
    except Exception:  # noqa: BLE001
        pass
    return 0


def run_replay(tool: str, a, idx: str, limit: float, video: str | None = None, traj: str | None = None) -> dict:
    """One fresh-process replay. Returns its --result record plus `rc`, `timed_out`, `proc_wall_s`, `eff_pace` (control
    steps per second from its first row to its end or its kill: a replay that hangs is slow by this measure) and
    `oom_kills` (the cgroup's OOM kills while it ran)."""
    res_path = os.path.join("/tmp", f"rcb_replay_{idx}.json")
    state_path = os.path.join("/tmp", f"rcb_state_{idx}.npy")
    for p in (res_path, state_path):
        if os.path.exists(p):
            os.remove(p)
    cmd = [sys.executable, tool, "replay", "--task", a.family, "--instance", a.instance, "--traj", traj or a.traj,
           "--result", res_path]
    if video:
        cmd += ["--video", video, "--fps", str(a.video_fps), "--video-deadline-s", str(max(60.0, limit - 300.0))]
    else:
        cmd += ["--final-state", state_path]
    t0 = time.time()
    oom0 = oom_kills()
    timed_out, rc = False, None
    try:
        p = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr, timeout=limit,
                           env={**os.environ, "RCB_SESSION_LOG": ""})
        rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    t_end = time.time()
    rec: dict = {}
    try:
        with open(res_path) as f:
            rec = json.load(f)
        mtime = os.path.getmtime(res_path)
    except Exception:  # noqa: BLE001 - no record: the process died before it wrote one
        rec, mtime = {}, t_end
    rec.update(rc=rc, timed_out=timed_out, proc_wall_s=round(t_end - t0, 1), state_path=state_path,
               oom_kills=max(0, oom_kills() - oom0))
    if rec.get("phase") == "done":
        rec["eff_pace"] = round(float(rec.get("sim_steps") or 0) / max(float(rec.get("wall_s") or 0.0), 1e-6), 3)
    elif rec.get("phase") == "agent":   # the first row ran at mtime - agent_wall_s (the last progress record)
        t_first = mtime - float(rec.get("agent_wall_s") or 0.0)
        rec["eff_pace"] = round(float(rec.get("rows_done") or 0) / max(t_end - t_first, 1.0), 3)
    HOSTS.append({"replay": idx, "host": rec.get("host"), "phase": rec.get("phase"),
                  "instance_matches": rec.get("instance_matches"), "instance_exact": rec.get("instance_exact")})
    write_hosts(a.instance)
    return rec


def host_fault(rec: dict) -> bool:
    """An error raised during the rows that is one of the host's kinds (HOST_FAULT)."""
    return bool(rec.get("sim_error")) and HOST_FAULT.search(str(rec["sim_error"])) is not None


def classify(rec: dict) -> str:
    """'instance_mismatch'; 'infra' (no agent row ran, or the process was killed from outside); 'retry' (from the first
    row on: a time-out, a Newton sidecar failure, a GPU or host error, an own-signal crash or an exit without a
    verdict: replayed once more, reproduced() decides); 'sim_error' (the agent's: an error the simulator raised on the
    rows that is not one of the host's kinds); 'done'."""
    phase = rec.get("phase")
    if rec.get("instance_matches") is False:  # the CLI stops before the first row when the scene is not the instance
        return "instance_mismatch"
    if phase not in ("agent", "done"):  # Isaac start, scene build, reset: no agent row has run
        return "infra"
    if rec.get("sidecar_failure"):  # the sidecar died / went silent while the rows ran
        return "retry"
    if phase == "done":  # the verdict is on disk (a signal or a hang while the app shuts down afterwards changes nothing)
        if rec.get("sim_error"):
            return "retry" if host_fault(rec) else "sim_error"
        return "done"
    if rec.get("timed_out"):  # the limit is a function of the trajectory's length only
        return "retry"
    rc = rec.get("rc")
    if isinstance(rc, int) and rc < 0 and -rc in EXTERNAL:  # SIGKILL / SIGTERM: the OOM killer, an operator
        return "infra"
    return "retry"  # crashed on its own signal (SIGSEGV, SIGABRT, ...) or exited without a verdict while the rows ran


def position(rec: dict) -> tuple[int, bool]:
    """(control step, exact) of a retry-class failure: a sidecar failure's step, the step at which an error was raised;
    else (a time-out, a crash) the rows done at its last progress record, a lower bound (exact = False)."""
    if rec.get("sidecar_failure") and rec.get("sidecar_at") is not None:
        return int(rec["sidecar_at"]), True
    if rec.get("phase") == "done":
        return int(rec.get("sim_steps") or 0), True
    return int(rec.get("rows_done") or 0), False


def window(a: int, b: int, settle: int, pace: float, exact: bool) -> float:
    """How far apart two failures may be and still be the same: SETTLE_STEPS when both steps are exact, else a quarter,
    120 rows, or the rows of two progress intervals at `pace` (a replay records its rows every PROGRESS_S; one that
    hangs stops recording, possibly before its first record)."""
    return float(settle) if exact else max(120.0, 0.25 * max(a, b), 2 * PROGRESS_S * pace)


def same_failure(r1: dict, r2: dict, settle: int, pace: float) -> bool:
    """Two retry-class replays failed the same way: at about the same control step (window()), whatever the kinds."""
    (a, ea), (b, eb) = position(r1), position(r2)
    return abs(a - b) <= window(a, b, settle, pace, ea and eb)


def reference(tool: str, a, M) -> dict:
    """A short replay of the frozen scene (REF_ROWS rows that hold both arms with the grippers open): the host's health
    and speed. 'ok' when it completes without a failure at no less than REF_PACE / HOST_SLOW; `host_slowdown` =
    REF_PACE / its pace here (the factor a replay's pace here is scaled by to the measurement host)."""
    path = os.path.join("/tmp", "rcb_reference.npz")
    rows = np.full((REF_ROWS, M.ACTION_DIM), np.nan)
    rows[:, 14:16] = 0.0
    np.savez(path, task=np.array(a.family), actions=rows)
    rec = run_replay(tool, a, "ref", M.replay_limit_s(a.family, REF_ROWS), traj=path)
    pace = float(rec.get("sim_steps") or 0) / max(float(rec.get("wall_s") or 0.0), 1e-6)
    ref = float(REF_PACE.get(a.family) or M.TASK_LIMITS.get(a.family, (0, 1.0))[1])
    ok = (rec.get("phase") == "done" and not rec.get("sidecar_failure") and not rec.get("sim_error")
          and pace >= ref / HOST_SLOW)
    slow = ref / pace if pace > 0 else float("inf")
    print(f"[grade] reference replay: ok={ok} pace={pace:.2f} (measured on an L40S: {ref:.2f}, at least "
          f"{ref / HOST_SLOW:.2f}) {json.dumps(rec)}", file=sys.stderr, flush=True)
    return {"reference_ok": int(ok), "reference_pace": round(pace, 3), "reference_l40s_pace": round(ref, 3),
            "host_slowdown": round(slow, 3) if np.isfinite(slow) else -1.0}


def reproduced(f1: dict, f2: dict, others: list, ref: dict, M, family: str) -> dict:
    """Whether the retry-class failures f1 and f2 (same_failure) are the rows' (the module docstring's rules 2-4), with
    the fields that explain it. `others`: every other replay of the same trajectory so far."""
    allowed = 0.5 * float(M.TASK_LIMITS.get(family, (0, 1.0))[1])   # the pace the time limit allows
    slow = float(ref.get("host_slowdown") or 0.0)
    norm = lambda r: float(r.get("eff_pace") or 0.0) * max(slow, 0.0)   # noqa: E731 - scaled to the measurement host
    out = {"replay_norm_pace": round(max(norm(f1), norm(f2)), 3), "replay_allowed_pace": round(allowed, 3)}
    if not ref.get("reference_ok"):
        return {**out, "reproduced": False}
    timeouts = [r for r in (f1, f2) if r.get("timed_out")]
    if any(norm(r) >= TOO_SLOW * allowed for r in timeouts):
        return {**out, "reproduced": False, "replay_not_too_slow": 1}
    only_timeouts = len(timeouts) == 2
    (p1, e1), (p2, e2) = position(f1), position(f2)
    far = max(p1, p2) + window(p1, p2, M.SETTLE_STEPS, max(float(r.get("eff_pace") or 0.0) for r in (f1, f2)), e1 and e2)
    for o in others:
        k = classify(o)
        if k == "done" and not (only_timeouts and norm(o) < TOO_SLOW * allowed):
            return {**out, "reproduced": False, "replay_contradicted": 1}
        if k == "retry" and not only_timeouts and position(o)[0] > far:
            return {**out, "reproduced": False, "replay_contradicted": 1}
    return {**out, "reproduced": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--repeat", type=int, default=0, help="replays (0: the task's grading kind, rcb_tactilelab.replays; "
                    "2 on a one-replay task is a determinism measurement by hand)")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--video-fps", type=int, default=15)
    a = ap.parse_args()
    os.environ["RCB_SESSION_LOG"] = ""  # the verifier's own sessions must not be counted
    ZERO = {"success": 0, "deterministic": 0, "sim_error": 0, "grader_error": 0, "infra_error": 0, "replays": 0}
    ERR = {**ZERO, "grader_error": 1, "infra_error": 1}  # no verdict on the agent
    if not os.path.isfile(a.traj):
        write(False, {**ZERO, "missing_trajectory": 1})
        return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the verifier's own copy of the tooling
        import rcb_tactilelab as M

        global HOST_FAULT
        HOST_FAULT = M.HOST_FAULT
        repeat = int(a.repeat) or M.replays(a.family)
        acts, bad = load_trajectory(a.traj, a.family, M.ACTION_DIM, M.max_rows(a.family), M.rows_problem)
        if bad is not None:
            write(False, {**ZERO, **bad})
            return 0
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rcb_tactilelab.py")
        t0 = time.time()
        limit = M.replay_limit_s(a.family, len(acts))
        a.video_limit_s = M.video_limit_s(a.family, len(acts))
        base = {"n_actions": int(len(acts)), "replay_timeout_s": round(limit, 1)}
        recs, history, retried, extra, first_fail, ref = [], [], False, {}, None, None

        def decide(f1: dict, f2: dict) -> None:
            """f2 failed in the retry class after f1 did: mark f2 reproduced (the agent's) or host_unreliable."""
            nonlocal ref, extra
            pace = max(float(r.get("pace") or r.get("eff_pace") or 0.0) for r in (f1, f2))
            pace = max(pace, float(M.TASK_LIMITS.get(a.family, (0, 1.0))[1]))
            if not same_failure(f1, f2, M.SETTLE_STEPS, pace):
                f2["host_unreliable"] = True   # failed again, differently: not the rows
                return
            if ref is None:
                ref = reference(tool, a, M)
            d = reproduced(f1, f2, [h for h in history if h is not f1 and h is not f2], ref, M, a.family)
            extra = {**ref, **{k: (int(v) if isinstance(v, bool) else v) for k, v in d.items() if k != "reproduced"}}
            f2["reproduced"] = d["reproduced"]
            f2["host_unreliable"] = not d["reproduced"]

        while len(recs) < repeat:
            i = len(recs)
            rec = run_replay(tool, a, str(i), limit)
            history.append(rec)
            kind = classify(rec)
            print(f"[grade] replay {i + 1}: {kind} {json.dumps(rec)}", file=sys.stderr, flush=True)
            if kind == "retry":
                if retried:  # a second retry-class failure after the retry was used: compared with the first one
                    decide(first_fail, rec)
                else:
                    retried, first_fail = True, rec
                    rec2 = run_replay(tool, a, f"{i}r", limit)
                    history.append(rec2)
                    kind2 = classify(rec2)
                    print(f"[grade] replay {i + 1}, again: {kind2} {json.dumps(rec2)}", file=sys.stderr, flush=True)
                    if kind2 == "retry":
                        decide(rec, rec2)
                    rec = rec2  # this replay counts in place of the failed one
            recs.append(rec)
            if classify(rec) != "done" or not rec.get("success"):
                break  # the verdict is settled (an infra failure, the agent's failure, or a failed replay)
        kinds = [classify(r) for r in recs]
        common = {**base, "replays": len(recs), "replay_wall_s": round(time.time() - t0, 1), "replay_retried": int(retried),
                  "replay_oom_kills": int(sum(int(h.get("oom_kills") or 0) for h in history)), **extra}

        def failure_fields(r: dict) -> dict:
            to, sc, gpu = bool(r.get("timed_out")), bool(r.get("sidecar_failure")), host_fault(r)
            sig = -r["rc"] if isinstance(r.get("rc"), int) and r["rc"] < 0 else 0
            killed = bool(sig) and sig in EXTERNAL and not (to or sc)
            crashed = r.get("phase") == "agent" and not (to or sc or killed)
            return {"replay_timed_out": int(to), "sidecar_failed": int(sc), "replay_gpu_fault": int(gpu and not sc),
                    "replay_crashed": int(crashed), "replay_killed": int(killed), "replay_signal": int(sig),
                    "replay_rows_done": int(r.get("rows_done") or 0), "replay_pace": float(r.get("pace") or 0.0),
                    "replay_eff_pace": float(r.get("eff_pace") or 0.0), "sidecar_at": int(r.get("sidecar_at") or 0),
                    "sim_steps": int(r.get("sim_steps") or 0)}

        bad = [r for r, k in zip(recs, kinds) if k in ("infra", "retry")]
        if bad and not bad[0].get("reproduced"):
            r = bad[0]
            ff = failure_fields(r)
            if r.get("sidecar_failure"):
                print(f"[grade] Newton sidecar failure: {r.get('sidecar_failure')}", file=sys.stderr, flush=True)
            if r.get("sim_error"):
                print(f"[grade] a host-kind error on the rows: {r.get('sim_error')}", file=sys.stderr, flush=True)
            write(False, {**ERR, **common, **ff, "replay_failed": int(not any(
                ff[k] for k in ("replay_timed_out", "sidecar_failed", "replay_gpu_fault", "replay_crashed", "replay_killed")))})
            return 0
        if bad:  # the same failure twice on a healthy host, nothing contradicting it: the rows cause it, the agent's 0
            r = bad[0]
            print("[grade] the replay failed the same way twice on a healthy host, and no replay of the trajectory got "
                  f"past it: the agent's result {json.dumps(extra)}", file=sys.stderr, flush=True)
            write(False, {**ZERO, **common, **failure_fields(r), "sim_error": 1, "replay_reproduced": 1})
            return 0
        if "instance_mismatch" in kinds:
            write(False, {**ERR, **common, "instance_ok": 0, "instance_mismatch": 1})
            return 0
        if "sim_error" in kinds:
            r = recs[kinds.index("sim_error")]
            print(f"[grade] simulator error on the agent's actions: {r.get('sim_error')}", file=sys.stderr, flush=True)
            write(False, {**ZERO, **common, "sim_error": 1, "replay_crashed": 0, "replay_signal": 0,
                          "sim_steps": int(r.get("sim_steps") or 0)})
            return 0
        all_success = all(bool(r.get("success")) for r in recs) and len(recs) == repeat
        hashes = {r.get("state_sha") for r in recs}
        checked = len(recs) >= 2
        deterministic = len(hashes) == 1 if checked else True   # one replay: nothing disagreed (determinism_checked 0)
        spread = 0.0
        if len(recs) >= 2:
            try:
                st = [np.load(r["state_path"], allow_pickle=False) for r in recs]
                spread = max(float(np.max(np.abs(s - st[0]))) if s.shape == st[0].shape else float("inf")
                             for s in st[1:])
            except Exception:  # noqa: BLE001 - a diagnostic
                spread = -1.0
        ok = all_success and deterministic
        out = {
            **ZERO,
            **common,
            "success": int(ok),
            "all_success": int(all_success),
            "deterministic": int(deterministic),
            "determinism_checked": int(checked),
            "replay_spread": spread if np.isfinite(spread) else -1.0,
            "instance_ok": 1,
            "instance_exact": int(all(bool(r.get("instance_exact")) for r in recs)),
            "sim_steps": int(recs[0].get("sim_steps") or 0),
        }
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {**ERR})
        return 0
    # the video: one more replay filmed by the third-person video camera, after the verdict is written (never part of it)
    if not a.no_video:
        video = os.path.join(LOG_DIR, "replay.mp4")
        try:
            rec = run_replay(tool, a, "video", float(a.video_limit_s), video=video)
            out["video_rendered"] = int(os.path.isfile(video) and os.path.getsize(video) > 0)
            out["video_truncated"] = int(bool(rec.get("video_truncated")) or rec.get("phase") != "done")
            out["video_state_match"] = int(rec.get("state_sha") is not None and rec.get("state_sha") == recs[0].get("state_sha"))
            out["video_wall_s"] = float(rec.get("proc_wall_s") or 0.0)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            out["video_rendered"] = 0
        with open(os.path.join(LOG_DIR, "reward.json"), "w") as f:  # the same verdict, with the video's fields
            json.dump(out, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

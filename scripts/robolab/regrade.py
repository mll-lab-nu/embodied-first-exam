#!/usr/bin/env python3
"""Re-grade recorded RoboLab trials with the current success term (2026-10-14: "the gripper" = both Robotiq fingers,
the on-table term of take_measuring_spoon_out and cooking_clear_plate, the 30-step settle hold) from their recorded
trajectories, instead of re-running them (docs/benchmarks/robolab.md, Re-grading).

    python3 scripts/robolab/regrade.py JOBS_DIR [JOBS_DIR ...] [--out regrade.jsonl] [--parallel 2] [--families a,b]
    python3 scripts/robolab/regrade.py --traj PATH.npz --family banana_in_bowl [--traj ...]

Host side (needs docker and the image ghcr.io/mll-lab-nu/eai-robolab:<images/robolab/VERSION>, an RTX-class GPU):
finds every RoboLab trial under JOBS_DIR (a Harbor jobs tree), takes its recorded trajectory (privileged:
artifacts/app/output/trajectory.npz; standard: the sidecar's verifier/trajectory.npz or artifacts/data/trajectory.npz,
else artifacts/data/journal.f64) and its recorded verdict (verifier/reward.json `success`), and replays each one in a
FRESH Isaac process (on Isaac only the first replay of a process is exact) with the current task's own tooling copy
(tasks/robolab-<family>-i00-privileged/tests/rcb_robolab.py and the frozen instance). It reports
  old_verdict  whether RoboLab's upstream term with the one-finger contact (upstream's "gripper" = the left inner finger)
               held at some control step of the recorded rows: the verdict before 2026-10-14;
  new_verdict  the current verdict: the current term (both fingers; on-table where it applies) holds at some step of the
               rows or of the 30-step settle hold after them;
  steps        the control step where each first held.
Output: one JSON line per trial (--out) and a table on stdout. One fresh replay per trial (the graders run two and
compare their state hashes; Isaac's CPU PhysX repeats a first replay exactly, so the second adds no verdict here).

Same host class as the recording. A trial is graded on the host it ran on (docs/benchmarks/robolab.md, Grading and
determinism: across hosts the final state can differ in the last bits). The tool prints this host's CPU and GPU and
marks a trial `inconclusive` when its recorded verdict was a success but the old rule does not hold here.

Standard trials: the re-grade is conservative. Under the current rule a success that did not fire would not have ended
the episode, and the agent could have gone on to release and succeed; the re-grade only says what the recorded episode
shows. Its label is "re-graded under 2026-10-14 rules (conservative)". Privileged re-grades are close to exact: the
deliverable is the trajectory, and only the settle hold after its last row is new."""
from __future__ import annotations
import argparse, json, os, pathlib, platform, re, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE      # inside the worker container the script is /regrade.py
VERSION = ROOT / "images/robolab/VERSION"
IMAGE = f"ghcr.io/mll-lab-nu/eai-robolab:{VERSION.read_text().strip() if VERSION.is_file() else 'unknown'}"
TRAJ_PATHS = {"privileged": ["artifacts/app/output/trajectory.npz"],
              "standard": ["verifier/trajectory.npz", "artifacts/data/trajectory.npz", "artifacts/data/journal.f64"]}


def host_info() -> str:
    cpu = "unknown"
    try:
        cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), cpu)
    except OSError:
        cpu = platform.processor() or cpu
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
                             timeout=20).stdout.strip().splitlines()[0]
    except Exception:  # noqa: BLE001
        gpu = "unknown"
    return f"CPU {cpu}; GPU {gpu}"


def task_name(d: pathlib.Path) -> str | None:
    """The full task name of a trial dir (board 0130 review M1): Harbor's result.json `task_name` or config.json
    `task.path`; None when neither is there (then the cut trial dir name is all there is)."""
    for f, get in (("result.json", lambda j: j.get("task_name")), ("config.json", lambda j: (j.get("task") or {}).get("path"))):
        try:
            v = get(json.loads((d / f).read_text()))
        except (OSError, ValueError, AttributeError):
            v = None
        if v:
            return pathlib.PurePosixPath(str(v)).name
    return None


def family_of(trial_name: str) -> str:
    base = trial_name.split("__")[0].removeprefix("robolab-")
    return base.split("-i0")[0].replace("-", "_")


def mode_of(trial_name: str) -> str:
    """privileged or standard from a Harbor trial dir name (<task>__<id>, the task name cut to 32 characters):
    standard when what follows the instance index is a prefix of -standard / -limited (the former name)."""
    m = re.search(r"-i\d\d(-[a-z]*)?$", trial_name.split("__")[0])
    suf = (m.group(1) or "") if m else ""
    return "standard" if suf and len(suf) > 1 and ("-standard".startswith(suf) or "-limited".startswith(suf)) else "privileged"


def find_trials(roots: list[str]) -> list[dict]:
    out = []
    for r in roots:
        for d in sorted(pathlib.Path(r).rglob("*")):
            if not d.is_dir() or not ((d / "result.json").is_file() or (d / "verifier").is_dir()):
                continue
            name = d.name.split("__")[0]
            if not name.startswith("robolab-"):
                continue
            full = task_name(d)                 # Harbor cuts the trial dir name to 32 characters: read the task's own name
            if full and not re.search(r"-i\d\d-(privileged|standard|limited)$", full):
                full = None
            if full is None and not (d / "verifier").is_dir():
                continue                        # a job dir (job-level result.json), not a trial
            mode = mode_of(full + "__x") if full else mode_of(d.name)
            traj = next((d / p for p in TRAJ_PATHS[mode] + TRAJ_PATHS["standard" if mode == "privileged" else "privileged"]
                         if (d / p).is_file()), None)
            rec = {}
            try:
                rec = json.loads((d / "verifier/reward.json").read_text())
            except (OSError, ValueError):
                pass
            out.append({"trial": str(d), "mode": mode, "traj": str(traj) if traj else None, "family_hint": family_of(full or d.name), "task": full,
                        "recorded_success": rec.get("success")})
    return out


def worker(tests: str, family: str, traj: str, out_path: str) -> None:
    """In the image, one fresh process: replay the rows with the current tooling, the upstream one-finger term watched at
    every step, then the settle hold."""
    import inspect
    sys.path.insert(0, tests)
    os.environ["RCB_SESSION_LOG"] = ""
    import numpy as np
    from rcb_robolab import Session, ACTION_DIM
    if traj.endswith(".f64"):
        acts = np.fromfile(traj, dtype=np.float64).reshape(-1, ACTION_DIM).astype(np.float32)
    else:
        with np.load(traj, allow_pickle=False) as d:
            acts = np.asarray(d["actions"], dtype=np.float32)
    s = Session(family, instance=os.path.join(tests, "instance.json"), depth=False)
    func, params = s.upstream_term
    old_params = dict(params)
    sig = inspect.signature(func).parameters
    if "gripper_name" in sig:
        old_params["gripper_name"] = "gripper_left"        # upstream's one contact body: the left inner finger
    if "key" in sig:
        # board 0130 review M2: a stateful upstream term (objects_placed_in_container_in_order latches each object's first
        # placement under `key`); the old rule must keep its own latch, or its looser placements decide the new verdict
        old_params["key"] = "rcb_regrade_old_rule::" + str(params.get("key") or func.__name__)

    def old_holds() -> bool:
        v = func(s.env, **old_params)
        return bool(v[0].item()) if hasattr(v, "__getitem__") else bool(v)
    s.reset()
    old_step = new_step = None
    for i, a in enumerate(acts):
        done = s.step(a)
        if old_step is None and old_holds():
            old_step = i + 1
        if done:
            break
    if s.status()["success"]:
        new_step = s.n_steps
    settled = s.settle()
    st = s.status()
    if new_step is None and st["success"]:
        new_step = s.n_steps
    r = {"family": family, "n_actions": int(len(acts)), "instance_exact": bool(s.instance_exact), "instance_ok": bool(s.instance_matches),
         "old_verdict": old_step is not None and bool(s.instance_matches), "old_step": old_step,
         "new_verdict": bool(st["success"]) and bool(s.instance_matches), "new_step": new_step, "settle_steps": settled,
         "state_sha": st["state_sha"], "host": host_info()}
    with open(out_path, "w") as f:
        f.write(json.dumps(r) + "\n")
    s.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="*"); ap.add_argument("--traj", action="append", default=[])
    ap.add_argument("--family", default=None, help="the family of the --traj files")
    ap.add_argument("--out", default="regrade_robolab.jsonl"); ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--families", default=""); ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--cache-volume", default="", help="a docker volume for Isaac's Kit cache (faster starts after the first)")
    ap.add_argument("--worker", nargs=4, metavar=("TESTS", "FAMILY", "TRAJ", "OUT"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.worker:
        worker(*a.worker); return 0
    trials = find_trials(a.jobs) + [{"trial": t, "mode": "standard" if "std" in pathlib.Path(t).name else "privileged", "traj": t,
                                     "family_hint": a.family, "recorded_success": None} for t in a.traj]
    print(f"[regrade] this host: {host_info()}. Re-grade a trial on the host class it ran on.", file=sys.stderr)
    want = set(filter(None, a.families.split(",")))
    todo = [t for t in trials if t.get("traj") and t.get("family_hint") and (not want or t["family_hint"] in want)]
    results = [dict(t, error="no recorded trajectory or family") for t in trials if not (t.get("traj") and t.get("family_hint"))]

    def run(t: dict) -> dict:
        fam = t["family_hint"]
        tests = ROOT / "tasks" / f"robolab-{fam.replace('_', '-')}-i00-privileged" / "tests"
        if not tests.is_dir():
            return dict(t, error=f"no task {tests.parent.name}")
        with tempfile.TemporaryDirectory(prefix="rl_regrade_") as td:
            src = pathlib.Path(t["traj"]); dst = pathlib.Path(td) / f"traj{src.suffix}"; dst.write_bytes(src.read_bytes())
            vols = ["-v", f"{td}:/w", "-v", f"{tests}:/tests:ro", "-v", f"{pathlib.Path(__file__).resolve()}:/regrade.py:ro"]
            if a.cache_volume:
                vols += ["-v", f"{a.cache_volume}:/cache"]
            cmd = ["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "OMNI_KIT_ACCEPT_EULA=YES",
                   "--cpus", "4", "--memory", "20g", *vols, a.image, "python", "/regrade.py", "--worker", "/tests", fam, f"/w/{dst.name}", "/w/out.json"]
            with open(pathlib.Path(td) / "worker.log", "w") as log:
                p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
            out = pathlib.Path(td) / "out.json"
            if not out.is_file():
                return dict(t, error=f"worker rc={p.returncode}: {(pathlib.Path(td) / 'worker.log').read_text()[-500:]}")
            return {**t, **json.loads(out.read_text())}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, a.parallel)) as ex:
        results += list(ex.map(run, todo))
    for r in results:
        if r.get("recorded_success") is not None and "old_verdict" in r:
            r["reproduced"] = bool(r["old_verdict"]) == bool(r["recorded_success"])
            r["inconclusive"] = bool(r["recorded_success"]) and not r["old_verdict"]
        r["label"] = "re-graded under 2026-10-14 rules" + (" (conservative)" if r.get("mode") == "standard" else "")
    with open(a.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    for r in results:
        old = "-" if "old_verdict" not in r else ("PASS" if r["old_verdict"] else "fail")
        new = "-" if "new_verdict" not in r else ("PASS" if r["new_verdict"] else "fail")
        note = r.get("error") or ("INCONCLUSIVE: recorded success not reproduced on this host" if r.get("inconclusive") else
                                  f"old at step {r.get('old_step')}, new at step {r.get('new_step')} (settle {r.get('settle_steps')})")
        print(f"{r.get('family_hint') or '?':28s} {r.get('mode', '?'):10s} rec={r.get('recorded_success')!s:5s} old={old:4s} new={new:4s} "
              f"{pathlib.Path(r['trial']).name[-36:]:36s} {note[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

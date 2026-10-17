#!/usr/bin/env python3
"""Re-grade recorded RoboWits trials with the current verifier (the 2026-10-14 settle window and release clause) from
their recorded trajectories, instead of re-running them (docs/benchmarks/robowits.md, Re-grading).

    python3 scripts/robowits/regrade.py JOBS_DIR [JOBS_DIR ...] [--out regrade.jsonl] [--repeat 2] [--families a,b] [--parallel N]
    python3 scripts/robowits/regrade.py --traj PATH.npz [--traj ...]           # loose trajectory files

Host side (needs docker and the image ghcr.io/mll-lab-nu/eai-robowits:<images/robowits/VERSION>; the 12 BlenderKit
families also need $RCB_ROBOWITS_BLENDERKIT, as the tasks do): finds every RoboWits trial under JOBS_DIR (a Harbor jobs
tree: <job>/<trial>/...), takes its recorded trajectory (privileged: artifacts/app/output/trajectory.npz; standard: the
sidecar's verifier/trajectory.npz or artifacts/data/trajectory.npz, else artifacts/data/journal.f64) and its recorded
verdict (verifier/reward.json `success`), and runs, per family, ONE container with the current task's own grader copies
(tasks/robowits-<family>-i00-privileged/tests/: rcb_robowits.py and the frozen instance). Inside, every trajectory is
replayed from the frozen instance (`Session.replay`, exact in-process on Genesis' CPU backend, `--repeat` times) and gets
  old_verdict  RoboWits' predicate right after the last row (the verdict of the grader before 2026-10-14; standard: the
               live episode ended at the first call after which it held, so the recording ends there),
  new_verdict  the current verdict: the settle window after the last row (Session.settle_check: 1 s hold, then 2 s in
               which the predicate holds with the graded objects released and within 2 mm), deterministic, instance ok,
  why          the settle window's reason.
Output: one JSON line per trial (--out) and a table on stdout.

Same CPU vendor as the recording. Genesis' CPU backend is bit-exact only within one CPU vendor (docs/benchmarks/
robowits.md, Hosts), so a trajectory recorded on another vendor can end elsewhere. The tool prints this host's vendor,
compares the frozen instance's rebuild with the trial's recorded `instance_exact`, and marks a trial `reproduced = false`
(and `inconclusive`) when its recorded verdict was a success but the old rule does not hold on this host: such a trial
must be re-graded on a host of the vendor it ran on.

Standard trials: the re-grade is conservative. Under the current rule a failed settle window does not end the episode
and the agent could have gone on to a real success; the re-grade only says what the recorded episode shows. Its label
is "re-graded under 2026-10-14 rules (conservative)". Two families' texts changed too (stand_pages: the bar is already
in the eyelets; hold_cup: where the hidden target is), which the recorded agents did not read."""
from __future__ import annotations
import argparse, json, os, pathlib, platform, re, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE      # inside the worker container the script is /regrade.py
VERSION = ROOT / "images/robowits/VERSION"
IMAGE = f"ghcr.io/mll-lab-nu/eai-robowits:{VERSION.read_text().strip() if VERSION.is_file() else 'unknown'}"
TRAJ_PATHS = {"privileged": ["artifacts/app/output/trajectory.npz"],
              "standard": ["verifier/trajectory.npz", "artifacts/data/trajectory.npz", "artifacts/data/journal.f64"]}


def cpu_vendor() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("vendor_id"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def mode_of(trial_name: str) -> str:
    """privileged or standard from a Harbor trial dir name (<task>__<id>, the task name cut to 32 characters):
    standard when what follows the instance index is a prefix of -standard / -limited (the former name)."""
    m = re.search(r"-i\d\d(-[a-z]*)?$", trial_name.split("__")[0])
    suf = (m.group(1) or "") if m else ""
    return "standard" if suf and len(suf) > 1 and ("-standard".startswith(suf) or "-limited".startswith(suf)) else "privileged"


def find_trials(roots: list[str]) -> list[dict]:
    """Harbor trial dirs of RoboWits tasks: a dir holding config.json or result.json whose task name says robowits."""
    out = []
    for r in roots:
        for d in sorted(pathlib.Path(r).rglob("*")):
            if not d.is_dir() or not ((d / "result.json").is_file() or (d / "verifier").is_dir()):
                continue
            name = d.name.split("__")[0]
            if not name.startswith("robowits-"):
                continue
            mode = mode_of(d.name)
            traj = next((d / p for p in TRAJ_PATHS[mode] + TRAJ_PATHS["standard" if mode == "privileged" else "privileged"]
                         if (d / p).is_file()), None)
            rec = {}
            try:
                rec = json.loads((d / "verifier/reward.json").read_text())
            except (OSError, ValueError):
                pass
            out.append({"trial": str(d), "mode": mode, "traj": str(traj) if traj else None,
                        "recorded_success": rec.get("success"), "recorded_instance_exact": rec.get("instance_exact")})
    return out


def worker(tests: str, family: str, items_path: str, out_path: str, repeat: int) -> None:
    """In the image: one Session of the current tooling, every trajectory of this family replayed from it."""
    sys.path.insert(0, tests)
    os.environ["RCB_SESSION_LOG"] = ""
    import numpy as np
    from rcb_robowits import Session, ACTION_DIM
    s = Session(family, instance=os.path.join(tests, "instance.json"))
    head = {"family": family, "instance_exact": bool(s.instance_exact), "instance_ok": bool(s.instance_matches), "cpu_vendor": cpu_vendor()}
    for it in json.load(open(items_path)):
        r = {**it, **head}
        try:
            p = it["traj_in"]
            if p.endswith(".f64"):                       # the standard sidecar's journal: the executed rows
                acts = np.fromfile(p, dtype=np.float64).reshape(-1, ACTION_DIM).astype(np.float32)
            else:
                with np.load(p, allow_pickle=False) as d:
                    if str(d["task"]) not in (family, "t"):
                        raise ValueError(f"trajectory of {d['task']}, not {family}")
                    acts = np.asarray(d["actions"], dtype=np.float32)
            outs = [s.replay(acts) for _ in range(repeat)]
            det = len({o["state_sha"] for o in outs}) == 1
            o = outs[0]
            r.update(n_actions=int(len(acts)), old_verdict=bool(all(x["predicate"] for x in outs) and det and s.instance_matches),
                     new_verdict=bool(all(x["success"] for x in outs) and det and s.instance_matches), deterministic=det,
                     goal_at_end=bool(o.get("goal_at_end")), why=(o.get("settle") or {}).get("why"),
                     settle_max_move_mm=round(1000 * float((o.get("settle") or {}).get("max_move_m") or 0), 2))
        except Exception as exc:  # noqa: BLE001
            r["error"] = repr(exc)[:300]
        with open(out_path, "a") as f:
            f.write(json.dumps(r) + "\n")
    s.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="*"); ap.add_argument("--traj", action="append", default=[])
    ap.add_argument("--out", default="regrade_robowits.jsonl"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--families", default=""); ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--parallel", type=int, default=1, help="families re-graded at once (one container each: ~2 CPUs, 8 GB)")
    ap.add_argument("--worker", nargs=4, metavar=("TESTS", "FAMILY", "ITEMS", "OUT"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.worker:
        worker(*a.worker, a.repeat); return 0
    trials = find_trials(a.jobs) + [{"trial": t, "mode": "standard" if "std" in pathlib.Path(t).name else "privileged", "traj": t,
                                     "recorded_success": None, "recorded_instance_exact": None} for t in a.traj]
    vendor = cpu_vendor()
    print(f"[regrade] this host's CPU vendor: {vendor}. Re-grade a trial on the vendor it was recorded on (Genesis' CPU "
          f"backend is bit-exact within one vendor only).", file=sys.stderr)
    import numpy as np  # noqa: F401  (the trajectories' family is read here)
    by_fam: dict[str, list] = {}
    for t in trials:
        if not t["traj"]:
            t.update(error="no recorded trajectory in the trial dir"); by_fam.setdefault("?", []).append(t); continue
        if t["traj"].endswith(".f64"):
            fam = pathlib.Path(t["trial"]).name.split("__")[0].removeprefix("robowits-").split("-i0")[0].replace("-", "_")
        else:
            with np.load(t["traj"], allow_pickle=False) as d:
                fam = str(d["task"])
        by_fam.setdefault(fam, []).append(t)
    want = set(filter(None, a.families.split(",")))
    results: list = []

    def run_family(fam: str, items: list, td: str) -> list:
        if fam == "?" or (want and fam not in want):
            return [dict(t, family=fam) for t in items]
        tests = ROOT / "tasks" / f"robowits-{fam.replace('_', '-')}-i00-privileged" / "tests"
        if not tests.is_dir():
            return [dict(t, family=fam, error=f"no task {tests.parent.name}") for t in items]
        work = pathlib.Path(td) / fam; (work / "in").mkdir(parents=True)
        for k, t in enumerate(items):
            dst = work / "in" / f"{k}{pathlib.Path(t['traj']).suffix}"
            dst.write_bytes(pathlib.Path(t["traj"]).read_bytes()); t["traj_in"] = f"/w/in/{dst.name}"
        (work / "items.json").write_text(json.dumps(items))
        vols = ["-v", f"{work}:/w", "-v", f"{tests}:/tests:ro", "-v", f"{pathlib.Path(__file__).resolve()}:/regrade.py:ro"]
        bk = os.environ.get("RCB_ROBOWITS_BLENDERKIT")
        needs_bk = "RCB_ROBOWITS_BLENDERKIT" in (tests / "docker-compose.yaml").read_text() if (tests / "docker-compose.yaml").is_file() else False
        if needs_bk and not (bk and pathlib.Path(bk).is_dir() and any(pathlib.Path(bk).iterdir())):
            return [dict(t, family=fam, error="this family loads BlenderKit models: set RCB_ROBOWITS_BLENDERKIT to the model folder "
                                               "(images/robowits/NOTICE)") for t in items]
        if bk:
            vols += ["-v", f"{bk}:/opt/robowits/assets/blender_kit:ro"]
        cmd = ["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "QD_OFFLINE_CACHE=0",
               "--cpus", "2", "--memory", "8g", *vols, a.image, "python", "/regrade.py", "--repeat", str(a.repeat),
               "--worker", "/tests", fam, "/w/items.json", "/w/out.jsonl"]
        print(f"[regrade] {fam}: {len(items)} trajectories", file=sys.stderr, flush=True)
        with open(work / "worker.log", "w") as log:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=log)
        got = [json.loads(l) for l in (work / "out.jsonl").read_text().splitlines()] if (work / "out.jsonl").is_file() else []
        if not got:
            log_text = (work / "worker.log").read_text()
            errs = [l for l in log_text.splitlines() if "Error" in l or "error" in l]
            tail = (errs[-1] if errs else log_text[-600:])[:600]
            return [dict(t, family=fam, error=f"worker rc={p.returncode}: {tail}") for t in items]
        return got

    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory(prefix="rw_regrade_") as td, ThreadPoolExecutor(max(1, a.parallel)) as ex:
        for got in ex.map(lambda kv: run_family(kv[0], kv[1], td), sorted(by_fam.items())):
            results += got
    for r in results:
        r.pop("traj_in", None)
        if r.get("recorded_success") is not None and "old_verdict" in r:
            r["reproduced"] = bool(r["old_verdict"]) == bool(r["recorded_success"])
            r["inconclusive"] = bool(r["recorded_success"]) and not r["old_verdict"]
        if r.get("recorded_instance_exact") is not None and "instance_exact" in r and bool(r["recorded_instance_exact"]) != r["instance_exact"]:
            r["vendor_warning"] = "the frozen instance rebuilds differently here than on the recording host (another CPU vendor?)"
        r["label"] = "re-graded under 2026-10-14 rules" + (" (conservative)" if r.get("mode") == "standard" else "")
    with open(a.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    for r in results:
        old = "-" if "old_verdict" not in r else ("PASS" if r["old_verdict"] else "fail")
        new = "-" if "new_verdict" not in r else ("PASS" if r["new_verdict"] else "fail")
        note = r.get("error") or ("INCONCLUSIVE: recorded success not reproduced on this host" if r.get("inconclusive") else (r.get("why") or ""))
        print(f"{r.get('family', '?'):18s} {r.get('mode', '?'):10s} rec={r.get('recorded_success')!s:5s} old={old:4s} new={new:4s} "
              f"{pathlib.Path(r['trial']).name[-40:]:40s} {note[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Re-grade recorded RoboPaint trials under the 2026-10-14 process rules (docs/benchmarks/robopaint.md, Counted strokes in
calligraphy) from their recorded trajectories, instead of re-running them.

    python3 scripts/robopaint_strict/regrade.py JOBS_DIR [JOBS_DIR ...] [--out regrade_robopaint.jsonl] [--parallel N]
    python3 scripts/robopaint_strict/regrade.py --traj TASK=PATH.npz [--traj ...]       # loose trajectory files

Host side (needs docker, a GPU and the image ghcr.io/mll-lab-nu/eai-robopaint:<images/robopaint/VERSION>): finds every
RoboPaint trial under JOBS_DIR (a Harbor trial: the task from result.json / config.json or the trial dir's name; a dashboard
download: files/verifier/), takes its recorded trajectory (privileged: artifacts/app/output/trajectory.npz; standard: the
collect hook's verifier/trajectory.npz or artifacts/data/trajectory.npz) and its recorded verdict (verifier/reward.json
`success`), and runs, per pair, ONE container with the current privileged task's graders' copy (tasks/<pair>-privileged/
tests/: rcb_brush_strict.py, rcb_brush.py and the frozen instance with the rules). Inside, each trajectory is replayed once
from the frozen instance (rcb_brush_strict.Session.replay, as the verifiers replay it) and the same final state is scored
twice:
  old_verdict  with the rules before 2026-10-14: the instance's target.success without the counted-stroke keys
               (stroke_gap_mm, mark_min_width_mm, max_stroke_path_mm) and, in the calligraphy families, without the sweep
               rule's keys (max_scribble, max_scribble_share, scribble_min_mm), which the earlier calligraphy rules lacked;
               rcb_brush_strict then scores exactly as the earlier grader did (contacts counted, colouring-in rule);
  new_verdict  with the current rules (the current verifier's verdict);
  image_success the picture rule alone (the verdict of the versions before the process rules, 2026-10-04).
A trajectory recorded on another instance (its instance_sha) is not re-graded. The recorded verdict is compared with the rule it
was graded under (`recorded_under`: the picture rule alone before 2026-10-04, the process rules before this change, or the
current rules); a recorded success the replay does not reproduce is marked `inconclusive` (look at that trial before using
its re-grade).

Scope: only the 43 pairs on main at this change (RELEASED below, both modes, including their pre-v1.0 trial names: privileged
without a suffix, standard `-limited`) are re-graded. A trial of any other RoboPaint task (pruned or earlier targets, pairs
added later) is listed with `skipped` and the reason. Standard re-grades are conservative ("re-graded under 2026-10-14 rules
(conservative)"): the agent read the earlier instruction. Output: one JSON line per trial (--out) and a table on stdout."""
from __future__ import annotations
import argparse, json, os, pathlib, re, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE      # inside the worker container the script is /regrade.py
VERSION = ROOT / "images/robopaint/VERSION"
IMAGE = f"ghcr.io/mll-lab-nu/eai-robopaint:{VERSION.read_text().strip() if VERSION.is_file() else 'unknown'}"
# The 43 RoboPaint pairs on main at this change (2026-10-14): robopaint-<family>-<target>-iNN, each -privileged and -standard.
RELEASED_TARGETS = {
    "acrylic": "applesoranges bedroom bluehorses greatwave kajikazawa plumpark redfuji suddenshower sunflowers vision",
    "caoshu": "beiquelindanshui nangong siwushaonian wen zhen zhongtiangechuifen",
    "kaishu": "linfengguilong yongzibafa",
    "lettering": "aim business commendation diligence liberty virtue",
    "oil": "bathers cafeterrace cypresses irises milkmaid monalisa pearlearring saintevictoire starrynight temeraire wanderer",
    "xingshu": "feng he huifenghechang maolinxiuzhu nian shan xian yong",
}
RELEASED = sorted(f"robopaint-{f}-{t}-{'i01' if f == 'oil' else 'i00'}" for f, ts in RELEASED_TARGETS.items() for t in ts.split())
assert len(RELEASED) == 43
SPLIT_KEYS = ("stroke_gap_mm", "mark_min_width_mm", "max_stroke_path_mm")          # = rcb_brush_strict.SPLIT_KEYS
SWEEP_KEYS = ("max_scribble", "max_scribble_share", "scribble_min_mm")
TRAJ_PATHS = {"privileged": ["artifacts/app/output/trajectory.npz"],
              "standard": ["verifier/trajectory.npz", "artifacts/data/trajectory.npz"]}
NAME_RE = re.compile(r"robopaint-[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*?-i\d\d(?:-(?:privileged|standard|limited))?")


def split_name(task: str) -> tuple[str, str]:
    """(pair, mode) of a task name: -privileged / no suffix (pre-v1.0) = privileged; -standard / -limited = standard."""
    m = re.fullmatch(r"(robopaint-.+?-i\d\d)(?:-(privileged|standard|limited))?", task)
    if not m:
        return task, "?"
    return m.group(1), "privileged" if m.group(2) in (None, "privileged") else "standard"


def task_of(d: pathlib.Path) -> str | None:
    for f, get in (("result.json", lambda j: j.get("task_name")), ("config.json", lambda j: (j.get("task") or {}).get("path"))):
        try:
            v = get(json.loads((d / f).read_text()))
        except (OSError, ValueError, AttributeError):
            v = None
        if v:
            return pathlib.PurePosixPath(str(v)).name
    hits = [m.group(0) for m in NAME_RE.finditer(d.name)]     # a dashboard download names the task; Harbor cuts it at 32
    full = [h for h in hits if h.endswith(("-privileged", "-standard", "-limited"))]
    if full:
        return full[0]
    cut = d.name.split("__")[0]
    cands = [f"{b}-{m}" for b in RELEASED for m in ("privileged", "standard") if f"{b}-{m}".startswith(cut)]
    if len(cands) == 1:
        return cands[0]
    return hits[0] if hits else None


def record_of(d: pathlib.Path) -> dict:
    for f in (d / "verifier/reward.json", d / "files/verifier/reward.json"):
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            pass
    try:
        return json.loads((d / "trial.json").read_text()).get("reward") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def find_trials(roots: list[str]) -> list[dict]:
    seen, out = set(), []
    for r in roots:
        for f in sorted(pathlib.Path(r).rglob("*")):
            if f.name not in ("result.json", "trial.json", "verifier") or (f.name == "verifier" and not f.is_dir()):
                continue
            d = f.parent.parent if f.parent.name == "files" else f.parent
            if d in seen or not ((d / "trial.json").is_file() or any((d / x).is_dir() for x in ("verifier", "agent", "files"))):
                continue                                       # a Harbor job dir (its trials are below it)
            task = task_of(d)
            if not task or not task.startswith("robopaint-"):
                continue
            seen.add(d)
            pair, mode = split_name(task)
            traj = next((d / p for p in TRAJ_PATHS.get(mode, []) if (d / p).is_file()), None)
            rec = record_of(d)
            out.append({"trial": str(d), "task": task, "pair": pair, "mode": mode, "traj": str(traj) if traj else None,
                        "recorded": rec.get("success"),
                        "recorded_under": ("current" if "n_strokes_counted" in rec else "process rules" if "strict_ok" in rec
                                           else "picture rule")})
    return out


def worker(tests: str, items_path: str, out_path: str) -> None:
    """In the image: one Session of the current graders' copy; every trajectory of this pair replayed once, scored twice."""
    sys.path.insert(0, tests)
    os.environ["RCB_SESSION_LOG"] = ""
    import numpy as np
    import rcb_brush as B
    import rcb_brush_strict as ST
    B.Session = ST.Session
    s = ST.Session(instance=os.path.join(tests, "instance.json"), render=False, max_steps=None)
    cfg = dict(s.inst["target"]["success"])
    calli = all(k in cfg for k in SPLIT_KEYS)
    old_cfg = {k: v for k, v in cfg.items() if k not in SPLIT_KEYS + (SWEEP_KEYS if calli else ())}
    head = {"instance_exact": bool(s.instance_exact), "instance_sha": s.instance_sha, "counted_strokes_rule": calli}
    keys = ("success", "final_reward", "image_success", "strict_ok", "n_strokes", "n_strokes_counted", "n_marked_pieces",
            "longest_counted_stroke_mm", "max_stroke_path_mm", "strokes_counted_ok", "scribble_share", "scribble_ok",
            "colour_in", "path_mm", "mark_width_mm")
    for it in json.load(open(items_path)):
        r = {**it, **head}
        try:
            with np.load(it["traj_in"], allow_pickle=False) as d:
                acts = np.asarray(d["actions"], dtype=np.float32)
                sha = str(d["instance_sha"]) if "instance_sha" in d.files else None
            r["traj_instance_sha"] = sha
            if sha and sha != s.instance_sha:
                r["error"] = "the trajectory was recorded on another instance (instance_sha differs): not re-graded"
            elif acts.ndim != 2 or acts.shape[1] != B.ACTION_DIM or len(acts) > B.MAX_STEPS or not np.all(np.isfinite(acts)):
                r.update(old_verdict=False, new_verdict=False, why="bad_trajectory (as the verifier rules)")
            else:
                new = s.replay(acts)                      # the current rules (instance's target.success)
                s.inst["target"]["success"] = old_cfg
                try:
                    old = s.score()                       # the same final state under the rules before 2026-10-14
                finally:
                    s.inst["target"]["success"] = cfg
                ok = bool(s.instance_matches)
                r.update(n_actions=int(len(acts)), old_verdict=bool(old.get("success")) and ok,
                         new_verdict=bool(new.get("success")) and ok, image_success=bool(new.get("image_success")),
                         old={k: old[k] for k in keys if k in old}, new={k: new[k] for k in keys if k in new})
                if r["old_verdict"] and not r["new_verdict"]:
                    r["why"] = ", ".join(k for k in ("strokes_counted_ok", "scribble_ok") if new.get(k) == 0.0) or "rules"
        except Exception as exc:  # noqa: BLE001
            r["error"] = repr(exc)[:300]
        with open(out_path, "a") as f:
            f.write(json.dumps(r) + "\n")
    s.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="*", help="Harbor jobs trees or downloaded trial folders")
    ap.add_argument("--traj", action="append", default=[], metavar="TASK=PATH", help="a loose trajectory and its task name")
    ap.add_argument("--out", default="regrade_robopaint.jsonl"); ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--parallel", type=int, default=1, help="pairs re-graded at once (one container each: 2 CPUs, 8 GB)")
    ap.add_argument("--work", default="", help="keep the per-pair work dirs (logs) here instead of a temporary dir")
    ap.add_argument("--worker", nargs=3, metavar=("TESTS", "ITEMS", "OUT"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.worker:
        worker(*a.worker); return 0
    trials = find_trials(a.jobs)
    for spec in a.traj:
        task, _, path = spec.partition("=")
        pair, mode = split_name(task)
        trials.append({"trial": path, "task": task, "pair": pair, "mode": mode, "traj": path, "recorded": None})
    results, by_pair = [], {}
    for t in trials:
        if t["pair"] not in RELEASED:
            results.append({**t, "skipped": "not one of the 43 pairs on main at this change (the released set): not part of this re-grade"})
        elif not t["traj"] and t.get("recorded") is not None and not t["recorded"]:   # the rules only add conditions
            results.append({**t, "old_verdict": False, "new_verdict": False,
                            "why": "recorded failure without a trajectory: stays a failure"})
        elif not t["traj"]:
            results.append({**t, "error": "no recorded trajectory in the trial dir"})
        else:
            by_pair.setdefault(t["pair"], []).append(t)

    def run_pair(pair: str, items: list, td: pathlib.Path) -> list:
        tests = ROOT / "tasks" / f"{pair}-privileged" / "tests"
        if not tests.is_dir():
            return [dict(t, error=f"no task {tests.parent.name} in this checkout") for t in items]
        work = td / pair; (work / "in").mkdir(parents=True, exist_ok=True)
        for k, t in enumerate(items):
            dst = work / "in" / f"{k}.npz"
            dst.write_bytes(pathlib.Path(t["traj"]).read_bytes()); t["traj_in"] = f"/w/in/{dst.name}"
        (work / "items.json").write_text(json.dumps(items))
        (work / "out.jsonl").unlink(missing_ok=True)
        cmd = ["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "--cpus", "2", "--memory", "8g",
               "-e", "OMP_NUM_THREADS=2", "-e", "MKL_NUM_THREADS=2", "-v", f"{work}:/w", "-v", f"{tests}:/tests:ro",
               "-v", f"{pathlib.Path(__file__).resolve()}:/regrade.py:ro", a.image,
               "python", "/regrade.py", "--worker", "/tests", "/w/items.json", "/w/out.jsonl"]
        print(f"[regrade] {pair}: {len(items)} trajectories", file=sys.stderr, flush=True)
        with open(work / "worker.log", "w") as log:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        got = [json.loads(l) for l in (work / "out.jsonl").read_text().splitlines()] if (work / "out.jsonl").is_file() else []
        if len(got) < len(items):
            tail = (work / "worker.log").read_text()[-400:]
            done = {g["traj_in"] for g in got}
            got += [dict(t, error=f"worker rc={p.returncode}: {tail}") for t in items if t["traj_in"] not in done]
        return got

    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory(prefix="rp_regrade_") as tmp, ThreadPoolExecutor(max(1, a.parallel)) as ex:
        td = pathlib.Path(a.work or tmp)
        for got in ex.map(lambda kv: run_pair(kv[0], kv[1], td), sorted(by_pair.items())):
            results += got
    for r in results:
        r.pop("traj_in", None)
        if r.get("recorded") is not None and "old_verdict" in r:
            # the rules the record was graded under: the current ones (n_strokes_counted in its reward.json), the process
            # rules before this change (strict_ok), or the picture rule alone (records from before 2026-10-04)
            under = r.get("recorded_under", "process rules")
            then = {"current": r.get("new_verdict"), "picture rule": r.get("image_success")}.get(under, r["old_verdict"])
            r["reproduced"] = bool(then) == bool(r["recorded"])
            r["inconclusive"] = bool(r["recorded"]) and not then
        if "new_verdict" in r:
            r["label"] = "re-graded under 2026-10-14 rules" + (" (conservative)" if r.get("mode") == "standard" else "")
    with open(a.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    v = lambda x: "-" if x is None else ("PASS" if x else "fail")  # noqa: E731
    for r in results:
        note = r.get("skipped") or r.get("error") or \
            ("INCONCLUSIVE: recorded success not reproduced" if r.get("inconclusive") else r.get("why", ""))
        if r.get("recorded") is not None and r.get("recorded_under") != "process rules" and "old" in r:
            note = (note + "; " if note else "") + f"recorded under: {r['recorded_under']}"
        print(f"{r['task'][:46]:46s} {r.get('mode', '?'):10s} rec={v(r.get('recorded')):4s} old={v(r.get('old_verdict')):4s} "
              f"new={v(r.get('new_verdict')):4s} {pathlib.Path(r['trial']).name[-24:]:24s} {note[:90]}")
    n = [r for r in results if "new_verdict" in r]
    print(f"[regrade] {len(results)} trial(s): {len(n)} re-graded, {sum(1 for r in n if r['old_verdict'] and not r['new_verdict'])} "
          f"success(es) withdrawn, {sum(1 for r in results if 'skipped' in r)} skipped; {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

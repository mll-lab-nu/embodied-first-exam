#!/usr/bin/env python3
"""Re-grade recorded RoboWits trials with the current verifier (the 2026-10-14 settle window and release clause; for
standard trials the 2026-10-17 grading replay: one window, the one that ended the episode) from their recorded
trajectories, instead of re-running them (docs/benchmarks/robowits.md, Re-grading).

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
  new_verdict  the current verdict: ONE settle window (Session.settle_check: 1 s hold, then 2 s in which the predicate
               holds with the graded objects released and within 2 mm), deterministic, instance ok. Privileged: the
               window after the last row. Standard (replay_standard, the service's grading_replay since 2026-10-17): when
               the live episode ended on a settle window (reason "success", or the window at the end of the agent's
               phase), that window is the last `final_window` recorded rows and is checked again over them; at the step
               cap (reason "step_guard") there is no window (a failure); otherwise the window after the last row. The
               window's length and the reason come from the trial's episode log (verifier/episode.jsonl or
               artifacts/data/episode.jsonl), else artifacts/data/final.json, else the trajectory's meta,
  why          the settle window's reason.
Output: one JSON line per trial (--out) and a table on stdout.

Same CPU vendor as the recording. Genesis' CPU backend is bit-exact only within one CPU vendor (docs/benchmarks/
robowits.md, Hosts), so a trajectory recorded on another vendor can end elsewhere. The tool prints this host's vendor,
compares the frozen instance's rebuild with the trial's recorded `instance_exact`, and marks a trial `reproduced = false`
(and `inconclusive`) when its recorded verdict was a success but the old rule does not hold on this host: such a trial
must be re-graded on a host of the vendor it ran on.

Standard trials recorded with the settle window (from 2026-10-14) are re-graded exactly: the same window over the same
rows. Earlier standard trials (no live window: the episode ended at the first call after which the predicate held) are
re-graded conservatively with the window after their last row: under the current rule a failed window does not end the
episode and the agent could have gone on to a real success; the re-grade only says what the recorded episode shows.
Labels: privileged "re-graded under 2026-10-14 rules"; standard "re-graded under 2026-10-17 rules", with
" (conservative)" for a trial without a live window. Two families' texts changed too (stand_pages: the bar is already
in the eyelets; hold_cup: where the hidden target is), which the recorded agents did not read."""
from __future__ import annotations
import argparse, json, os, pathlib, platform, re, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE      # inside the worker container the script is /regrade.py
VERSION = ROOT / "images/robowits/VERSION"
IMAGE = f"ghcr.io/mll-lab-nu/eai-robowits:{VERSION.read_text().strip() if VERSION.is_file() else 'unknown'}"
TRAJ_PATHS = {"privileged": ["artifacts/app/output/trajectory.npz"],
              "standard": ["verifier/trajectory.npz", "artifacts/data/trajectory.npz", "artifacts/data/journal.f64"]}
RULES = {"privileged": "re-graded under 2026-10-14 rules", "standard": "re-graded under 2026-10-17 rules"}
WINDOW_ENDS = ("agent_exit", "timeout")      # reasons whose end-of-phase settle window is the last recorded rows


def episode_end(d: pathlib.Path, traj: pathlib.Path | None = None) -> dict:
    """How a standard episode ended: reason, final_window (the settle window that ended it: its length in recorded rows,
    None without one) and the live final state hash, from the trial's episode log, else final.json, else the trajectory's
    meta. The service logs `final_window` since 2026-10-17; before, it is the last settle event's `steps` when the episode
    ended with reason "success", or with "agent_exit" / "timeout" and that event came after the last call's."""
    out: dict = {"reason": None, "final_window": None, "live_sha": None, "end_source": None, "end_control_steps": None}
    fin = None
    for fp in (d / "artifacts/data/final.json", d / "final.json"):      # (the second: beside a loose trajectory)
        try:
            fin = json.loads(fp.read_text()); out["live_sha"] = fin.get("live_sha"); out["live_success"] = fin.get("success"); break
        except (OSError, ValueError):
            pass
    for log in (d / "verifier/episode.jsonl", d / "artifacts/data/episode.jsonl", d / "episode.jsonl"):
        try:
            evs = [json.loads(l) for l in log.read_text().splitlines() if l.strip().startswith("{")]
        except (OSError, ValueError):
            continue
        ends = [i for i, e in enumerate(evs) if e.get("ev") == "end"]
        if not ends:
            continue
        end = evs[ends[-1]]; out.update(reason=end.get("reason"), end_source=str(log.relative_to(d)),
                                        end_control_steps=end.get("control_steps"))
        if "final_window" in end:
            out["final_window"] = end["final_window"]; return out
        st = [i for i, e in enumerate(evs) if e.get("ev") == "settle"]
        calls = [i for i, e in enumerate(evs) if e.get("ev") in ("submit", "observe")]
        if st and (out["reason"] == "success" and evs[st[-1]].get("success") or
                   out["reason"] in WINDOW_ENDS and st[-1] > (calls[-1] if calls else -1)):
            out["final_window"] = int(evs[st[-1]].get("steps") or 0) or None
        return out
    if fin is not None:
        out.update(reason=fin.get("reason"), end_source="final.json")
        if "final_window" in fin:
            out["final_window"] = fin["final_window"]
        elif (fin.get("settle") or {}).get("steps") and fin["settle"].get("success") and out["reason"] in ("success", *WINDOW_ENDS):
            # only a window that passed is surely the one that ended the episode (a passed in-call window ends it with
            # reason "success"); a failed one may be an in-call window followed by more rows: conservative instead
            out["final_window"] = int(fin["settle"]["steps"])
        out["end_control_steps"] = fin.get("control_steps")
        return out
    if traj is not None and traj.suffix == ".npz":
        try:
            import numpy as np
            with np.load(traj, allow_pickle=False) as z:
                meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
            out.update(reason=meta.get("reason"), final_window=meta.get("final_window"), end_source="trajectory meta")
        except Exception:  # noqa: BLE001
            pass
    return out


def replay_standard(s, acts, window, reason: str | None) -> dict:
    """The standard service's grading replay (shared/server.py grading_replay, which this repeats on a Session of the
    current tooling): the recorded rows and ONE settle window. Returns success, settle, predicate (RoboWits' predicate
    right after the last recorded row) and state_sha (the state then)."""
    import numpy as np
    acts = np.asarray(acts, dtype=np.float32)
    if reason == "step_guard":
        st = s.replay(acts, settle=False)
        return {"success": False, "predicate": st["predicate"], "state_sha": st["state_sha_rows"], "goal_at_end": st["goal_at_end"],
                "settle": {"success": False, "why": "the episode ended at the step cap: graded without a settle window", "steps": 0, "max_move_m": 0.0}}
    w = int(window or 0)
    if not 0 < w <= len(acts):
        st = s.replay(acts)
        return {"success": st["success"], "predicate": st["predicate"], "state_sha": st["state_sha_rows"], "goal_at_end": st["goal_at_end"],
                "settle": st.get("settle")}
    s.reset()
    for a in acts[:len(acts) - w]:
        s.step(a)
    rows = list(acts[len(acts) - w:]); end: dict = {}

    def recorded_step(hold) -> bool:
        if not rows:
            return s.step(hold)
        guard = s.step(rows.pop(0))
        if not rows:
            g = s.goal(); end.update(state_sha=s.state_sha(), predicate=g["predicate"], goal_at_end=g["success"])
        return guard

    sc = s.settle_check(step=recorded_step)
    while rows:
        recorded_step(None)
    return {"success": sc["success"], "settle": sc, **end}


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
                        "recorded_success": rec.get("success"), "recorded_instance_exact": rec.get("instance_exact"),
                        **(episode_end(d, traj) if mode == "standard" else {})})
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
            if it.get("mode") == "standard":
                window = it.get("final_window")
                n_end = it.get("end_control_steps")
                short = int(n_end) - len(acts) if window and n_end is not None else 0
                if short:
                    # the rows are not the whole recorded episode (journal.f64 is flushed at checkpoints only, and none
                    # follows the end-of-phase window). The missing rows can only be the end of the window, all the held
                    # command, which the replay holds once the rows run out: exact with the window shortened by them;
                    # otherwise the window cannot be placed and the trial is graded conservatively
                    r["rows_mismatch"] = f"{len(acts)} rows, the episode ended at control step {n_end}"
                    window = r["final_window"] = (window - short) if 0 < short <= window else None
                    if window == 0:                  # the whole window is missing: s.replay runs it after the rows
                        window = None; r["final_window"] = None; r["window_after_rows_exact"] = True
                outs = [replay_standard(s, acts, window, it.get("reason")) for _ in range(repeat)]
            else:
                outs = [s.replay(acts) for _ in range(repeat)]
            det = len({o["state_sha"] for o in outs}) == 1
            o = outs[0]
            r.update(n_actions=int(len(acts)), old_verdict=bool(all(x["predicate"] for x in outs) and det and s.instance_matches),
                     new_verdict=bool(all(x["success"] for x in outs) and det and s.instance_matches), deterministic=det,
                     goal_at_end=bool(o.get("goal_at_end")), why=(o.get("settle") or {}).get("why"),
                     settle_steps=int((o.get("settle") or {}).get("steps") or 0),
                     settle_max_move_mm=round(1000 * float((o.get("settle") or {}).get("max_move_m") or 0), 2))
            if it.get("mode") == "standard" and it.get("live_sha") and not r.get("rows_mismatch"):   # (fewer rows: another state)
                r["replay_matches_live"] = o.get("state_sha") == it["live_sha"]
            if it.get("mode") == "standard" and (r.get("final_window") or r.get("window_after_rows_exact")) \
                    and it.get("live_success") is False and r["new_verdict"]:
                # the window that ended the episode is the live one: the service's verdict needs the live success too
                r["new_verdict"] = False; r["why"] = f"the live episode did not succeed ({it.get('reason')})"
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
    loose = [{"trial": t, "mode": "standard" if "std" in pathlib.Path(t).name else "privileged", "traj": t,
              "recorded_success": None, "recorded_instance_exact": None} for t in a.traj]
    for t in loose:     # a loose standard trajectory: its episode log / final.json beside it, else its meta
        if t["mode"] == "standard":
            t.update(episode_end(pathlib.Path(t["traj"]).parent, pathlib.Path(t["traj"])))
    trials = find_trials(a.jobs) + loose
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
        std = r.get("mode") == "standard"
        exact = r.get("final_window") or r.get("window_after_rows_exact") or r.get("reason") == "step_guard"   # as the service grades it
        r["label"] = RULES["standard" if std else "privileged"] + (" (conservative)" if std and not exact else "")
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

#!/usr/bin/env python3
"""Choose and freeze one instance per Panda Dynamic Scenes task (i00): the lowest-seed nominal instance whose recorded,
replay-checked reference rollout (the benchmark's own verified bank, current source) passes here, in eai-pandadyn:

  1. `rcb_pandadyn.py make-instance`: instance.json from the rollout's task, difficulty, seed and resolved parameters, with
     the hash of the scene this image builds from them (`initial_sha`); the rollout's rows as oracle_actions.npy (T, D);
  2. the rollout replayed here reproduces the physical state it recorded after EVERY control step, bit for bit (this
     image's physics is the physics the bank was verified on);
  3. `run-actions` (the oracle, through the tooling) succeeds, and two `replay`s, each a fresh process, succeed and end in
     the same state hash as the oracle run.
The rows stay float64 as recorded: rounded to float32 (what the shipped client's `submit` sends) they fail on some tasks
(4 of the first 13 tried: D04 seed 1, D07, D09, D11), so the standard oracle sends them as a float64 array part.

    python3 scripts/pandadyn/freeze.py --bank <panda-dynamic-scenes-25 checkout> --work <scratch dir>
    python3 scripts/pandadyn/freeze.py ... --only S02,D04 --jobs 6
Writes scripts/pandadyn/frozen/<code>-i00/{instance.json, oracle_actions.npy} and scripts/pandadyn/instances.json (the
choice, its provenance and the hashes). Provenance (the rollout's path in the benchmark checkout, its source digest) is
kept in instances.json only: instance.json, which the agent reads in privileged mode, never names where it came from.
A task in mk_tasks.BLAS_PIN (its start depends on the BLAS kernel; S06) is frozen with that OPENBLAS_CORETYPE, as its
containers run it; the bank recorded its rollout under another kernel, so step 2 is reported for it but not required."""
from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1].parent
HERE = ROOT / "scripts/pandadyn"
IMAGE = f"ghcr.io/mll-lab-nu/eai-pandadyn:{(ROOT / 'images/pandadyn/VERSION').read_text().strip()}"
sys.path.insert(0, str(HERE))
from mk_tasks import BLAS_PIN  # noqa: E402  (code -> OPENBLAS_CORETYPE: the tasks' containers set it, so freezing does too)

COMPARE = r'''
import sys, json, numpy as np
sys.path.insert(0, "/tools")
from rcb_pandadyn import Session
from panda_dynamics.props.primitives import body
d = sys.argv[1]
s = Session(d + "/instance.json", strict=True)
rec = np.load(d + "/actions.npz"); A = np.asarray(rec["actions"], dtype=np.float64).reshape(len(rec["actions"]), -1); X = rec["states"]
def pv(u):
    vals = [v for arm in u.arms.values() for v in (arm.robot.qpos, arm.robot.qvel)]
    for obj in u.objects.values():
        rb = body(obj); vals += [rb.entity_pose.p, rb.entity_pose.q, rb.linear_velocity, rb.angular_velocity]
    for f in u.fixtures.values():
        vals += [f.raw.qpos, f.raw.qvel]
    return np.concatenate([np.asarray(v.cpu() if hasattr(v, "cpu") else v, dtype=np.float32).reshape(-1) for v in vals])
worst, first = 0.0, None
for i, row in enumerate(A):
    s.step(row); e = float(np.max(np.abs(pv(s.u) - X[i])))
    if e > 0 and first is None: first = i
    worst = max(worst, e)
print(json.dumps({"steps": int(len(A)), "max_abs_diff": worst, "first_diff_step": first, "success": s.success()}))
'''


def make_candidates(bank: pathlib.Path) -> dict:
    """Per task code, the bank's rollouts that can be an instance: current source, the reference controller (mode
    `witness`), nominal, 1000 Hz physics, successful; lowest seed first (the bank's own reports/all_trials.jsonl)."""
    out: dict = {}
    for line in open(bank / "reports/all_trials.jsonl"):
        r = json.loads(line)
        if str(r.get("current_source")) != "True" or r.get("mode") != "witness" or r.get("difficulty") != "nominal":
            continue
        if str(r.get("physics_hz")) != "1000" or str(r.get("success")) != "True":
            continue
        code = r["task_id"].split("/")[1][:3]
        out.setdefault(code, []).append({"seed": int(r["seed"]), "trial": r["trial_path"], "replay": str(r.get("replay"))[:200],
                                         "task_source_digest": r["task_source_digest"], "duration_s": float(r["duration"])})
    return {c: sorted(v, key=lambda x: (x["seed"], x["trial"])) for c, v in sorted(out.items())}


def run(work: pathlib.Path, cmd: str, timeout: int = 1800, code: str = "") -> dict:
    tools = HERE / "shared"
    pin = ["-e", f"OPENBLAS_CORETYPE={BLAS_PIN[code]}"] if code in BLAS_PIN else []
    p = subprocess.run(["docker", "run", "--rm", "--gpus", "all", "--network", "none", "-e", "RCB_SESSION_LOG=", *pin, "-v", f"{work}:/w",
                        "-v", f"{tools}:/tools:ro", "-w", "/w", IMAGE, "bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    last = {}
    for line in p.stdout.splitlines():
        if line.startswith("{"):
            try:
                last = json.loads(line)
            except ValueError:
                pass
    if not last:
        last = {"error": f"rc={p.returncode}: {p.stderr[-600:]}"}
    return last


def try_candidate(code: str, c: dict, bank: pathlib.Path, work_root: pathlib.Path) -> dict:
    src = bank / pathlib.Path(c["trial"]).parent
    work = work_root / f"{code}-seed{c['seed']}"
    work.mkdir(parents=True, exist_ok=True)
    for f in ("trial.json", "actions.npz"):
        shutil.copy(src / f, work / f)
    (work / "compare.py").write_text(COMPARE)
    out = {"code": code, "seed": c["seed"], "trial": c["trial"], "task_source_digest": c["task_source_digest"]}
    mk = run(work, "python /tools/rcb_pandadyn.py make-instance --trial /w --out /w/instance.json --actions-out /w/oracle_actions.npy", code=code)
    if "initial_sha" not in mk:
        return {**out, "ok": False, "why": f"make-instance: {mk}"}
    cmp_ = run(work, "python /w/compare.py /w", code=code)
    out["recorded_state_check"] = cmp_
    if code not in BLAS_PIN and (cmp_.get("max_abs_diff") != 0.0 or not cmp_.get("success")):
        return {**out, "ok": False, "why": f"recorded states not reproduced: {cmp_}"}
    orc = run(work, "python /tools/rcb_pandadyn.py run-actions --instance /w/instance.json --actions /w/oracle_actions.npy --out /w/oracle_traj.npz", code=code)
    if not orc.get("success"):
        return {**out, "ok": False, "why": f"oracle run: {orc}"}
    reps = [run(work, "python /tools/rcb_pandadyn.py replay --instance /w/instance.json --traj /w/oracle_traj.npz", code=code) for _ in range(2)]
    shas = [((r.get("replays") or [{}])[0]).get("state_sha") for r in reps]
    ok = all(((r.get("replays") or [{}])[0]).get("success") and r.get("instance_matches") for r in reps) and len(set(shas + [orc["state_sha"]])) == 1
    inst = json.loads((work / "instance.json").read_text())
    A = (work / "oracle_actions.npy").read_bytes()
    return {**out, "ok": ok, "why": None if ok else f"replays: {reps}", "initial_sha": inst["initial_sha"], "final_sha": orc["state_sha"],
            "n_actions": int(orc["executed_rows"]), "sim_time_s": orc["sim_time_s"], "oracle_npy_sha256": hashlib.sha256(A).hexdigest(),
            "work": str(work)}


def freeze_task(code: str, cands: list, bank: pathlib.Path, work_root: pathlib.Path, max_tries: int) -> dict:
    tried = []
    for c in [c for c in cands if not str(c["replay"]).startswith("not_run")][:max_tries]:
        r = try_candidate(code, c, bank, work_root)
        tried.append({k: r.get(k) for k in ("seed", "ok", "why")})
        print(json.dumps({"code": code, "seed": c["seed"], "ok": r["ok"], "why": (r.get("why") or "")[:300]}), flush=True)
        if r["ok"]:
            return {**r, "tried": tried}
    return {"code": code, "ok": False, "tried": tried}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--candidates", default=None, help="candidates.json (default: <work>/candidates.json, made from the bank's report)")
    ap.add_argument("--only", default=""); ap.add_argument("--jobs", type=int, default=6); ap.add_argument("--max-tries", type=int, default=4)
    a = ap.parse_args()
    bank, work = pathlib.Path(a.bank), pathlib.Path(a.work)
    cpath = pathlib.Path(a.candidates or work / "candidates.json")
    if not cpath.exists():
        work.mkdir(parents=True, exist_ok=True); cpath.write_text(json.dumps(make_candidates(bank), indent=1))
    cands = json.loads(cpath.read_text())
    codes = [c for c in sorted(cands) if not a.only or c in a.only.split(",")]
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        results = dict(zip(codes, ex.map(lambda c: freeze_task(c, cands[c], bank, work, a.max_tries), codes)))
    reg_path = HERE / "instances.json"
    reg = json.loads(reg_path.read_text()) if reg_path.exists() else {"tasks": {}}
    for code, r in results.items():
        if not r["ok"]:
            print(f"FAILED {code}: {r['tried']}"); continue
        w = pathlib.Path(r["work"]); inst = json.loads((w / "instance.json").read_text())
        dest = HERE / "frozen" / f"{inst['task']}-i00"; dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(w / "instance.json", dest / "instance.json"); shutil.copy(w / "oracle_actions.npy", dest / "oracle_actions.npy")
        reg["tasks"][inst["task"]] = {"id": 0, "difficulty": inst["difficulty"], "seed": inst["seed"], "initial_sha": r["initial_sha"],
                                      "oracle_final_sha": r["final_sha"], "oracle_rows": r["n_actions"], "oracle_sim_time_s": r["sim_time_s"],
                                      "oracle_npy_sha256": r["oracle_npy_sha256"], "recorded_state_check": r["recorded_state_check"],
                                      "provenance": {"rollout": r["trial"], "task_source_digest": r["task_source_digest"]},
                                      "candidates_tried": r["tried"]}
    reg["image"] = IMAGE
    reg_path.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    bad = [c for c, r in results.items() if not r["ok"]]
    print(f"frozen {len(results) - len(bad)} / {len(results)}; failed: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

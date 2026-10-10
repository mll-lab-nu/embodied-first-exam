#!/usr/bin/env python3
"""Freeze the AutoBio instances and their reference trajectories. Runs INSIDE the eai-autobio image.

    # re-check what is committed (hashes of every instance, every reference trajectory in two fresh processes):
    docker run --rm -v $PWD/scripts/autobio:/w:ro ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) \
        python /w/make_facts.py --check
    # negative controls (half the reference, the reference reversed, random targets, idling, another task's reference):
    #   ... python /w/make_facts.py --controls
    # rebuild instances/ and oracles/ (needs an AutoBio checkout at the image's commit, WITH its experts):
    docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD/scripts/autobio:/w -v /path/to/AutoBio:/upstream:ro \
        ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) python /w/make_facts.py --upstream /upstream/autobio

Per family (seed 0):
- instances/<family>.json: what `rcb_autobio.py facts` reports from the image (model and initial-state hashes, the
  action layout, cameras, AutoBio's prompt) plus the reference's size and final-state hash.
- oracles/<family>.npz: the position targets AutoBio's own scripted expert sends from that instance, one row per 2 ms
  control step. The expert runs from the mounted checkout (the image has no experts), recorded at every physics step;
  the rows are clipped to the actuators' ranges, rounded to float32 (what the standard client sends, so both modes
  execute the same rows) and, for rule `first`, cut at the first step at which AutoBio's check holds.
Every reference is then replayed by the image's own (expert-free) code in two fresh processes: both must succeed and
end in the same state. Negative control: holding the initial targets for 10 s must not succeed.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TOOL = HERE / "shared" / "rcb_autobio.py"
SEED = 0
ENV = {**os.environ, "RCB_SESSION_LOG": "", "PYTHONPATH": str(HERE / "shared")}


def run(args: list, env: dict | None = None) -> str:
    r = subprocess.run([sys.executable, *map(str, args)], env=env or ENV, cwd="/tmp", capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(map(str, args))}\n{r.stderr[-3000:]}")
    return r.stdout


def last_json(text: str) -> dict:
    return json.loads([ln for ln in text.splitlines() if ln.startswith("{")][-1])


def record(family: str, out: str) -> None:
    """(subprocess, AUTOBIO_ROOT = a checkout with experts) Run AutoBio's expert; save the targets of every step."""
    import importlib

    import rcb_autobio as R

    mod, cls, _rule = R.FAMILIES[family]
    rows = []
    with R._in_root():
        T = getattr(importlib.import_module(mod), cls)
        e = T.Expert(T.load())
        e.task = family
        info = e.reset(seed=SEED)
        idx = np.asarray(info["action_indices"], dtype=int).ravel()
        step = e.manager.step

        def recorded():
            rows.append(e.data.ctrl[idx].copy())  # the targets in effect during this physics step
            step()

        e.manager.step = recorded
        try:
            e.execute()
        except AttributeError as exc:  # three experts end by closing a log writer that is not set up here
            if "finish" not in str(exc):
                raise
    np.save(out, np.asarray(rows, dtype=np.float64))


def cut(family: str, instance: str, raw: str, out: str) -> None:
    """(subprocess, the image's own AutoBio) Clip, round to float32, cut at the first success; negative control."""
    import rcb_autobio as R

    R.SESSION_LOG = ""
    s = R.Session(instance=instance)
    rows = np.clip(np.load(raw), s.lo, s.hi).astype(np.float32)
    over, under = rows.astype(np.float64) > s.hi, rows.astype(np.float64) < s.lo  # float32 rounding past a limit
    rows[over] = np.nextafter(rows[over], np.float32(-np.inf))
    rows[under] = np.nextafter(rows[under], np.float32(np.inf))
    t0 = time.time()
    st = s.replay(rows.astype(np.float64))
    rate = st["steps"] / max(time.time() - t0, 1e-9)
    if not st["success"]:
        raise SystemExit(f"{family}: AutoBio's expert does not succeed from the frozen instance: {st}")
    keep = rows[: st["steps"]] if s.rule == "first" else rows
    s.reset()
    s.step(s.command(), n=5000)
    idle = s.status()
    if idle["success"] or idle["score"] >= 1.0:
        raise SystemExit(f"{family}: holding the initial targets for 10 s succeeds: {idle}")
    np.savez_compressed(out, actions=keep)
    print(json.dumps({"reference_rows": int(len(keep)), "expert_rows": int(len(rows)), "steps_per_s": int(float(f"{rate:.1g}")),  # one significant digit: a wall-clock measurement
                      "idle_score_10s": float(idle["score"])}))
    s.close()


def verify(family: str, instance: str, oracle: str) -> dict:
    """Two fresh processes replay the reference with the image's own code."""
    with tempfile.TemporaryDirectory() as tmp:
        traj = os.path.join(tmp, "t.npz")
        np.savez(traj, actions=np.load(oracle)["actions"].astype(np.float64), task=family)
        a = last_json(run([TOOL, "replay", "--instance", instance, "--traj", traj]))
        b = last_json(run([TOOL, "replay", "--instance", instance, "--traj", traj]))
    ok = a["success"] and b["success"] and a["state_sha"] == b["state_sha"] and a["instance_ok"] and b["instance_ok"]
    if not ok:
        raise SystemExit(f"{family}: the reference does not replay to one successful state in two fresh processes:\n{a}\n{b}")
    return {"reference_steps": int(a["steps"]), "reference_sha": a["state_sha"], "reference_score": float(a["score"])}


def controls(family: str) -> None:
    """(subprocess, the image's own AutoBio) Wrong trajectories must not succeed; the reference must."""
    import rcb_autobio as R

    R.SESSION_LOG = ""
    s = R.Session(instance=str(HERE / "instances" / f"{family}.json"))
    ref = np.load(HERE / "oracles" / f"{family}.npz")["actions"].astype(np.float64)
    rng = np.random.default_rng(0)
    cases = {
        "reference": ref,
        "first_half": ref[: len(ref) // 2],
        "all_but_last_50": ref[:-50],
        "reversed": ref[::-1],
        "random_4s": rng.uniform(s.lo, s.hi, size=(2000, s.n_act)),
        "initial_targets_10s": np.tile(s.command(), (5000, 1)),
    }
    if s.rule == "final":  # judged where the rows end: once the goal state is reached, dropping later rows keeps it
        del cases["all_but_last_50"]
    for other in sorted(R.FAMILIES):  # another family's reference with the same number of entries
        o = HERE / "oracles" / f"{other}.npz"
        if other != family and o.exists():
            rows = np.load(o)["actions"].astype(np.float64)
            if rows.shape[1] == s.n_act and other.split("_")[0] != family.split("_")[0]:
                cases[f"reference_of_{other}"] = rows
                break
    out = {}
    for name, rows in cases.items():
        st = s.replay(rows)
        out[name] = {"success": bool(st["success"]), "score": round(float(st["score"]), 3), "steps": int(st["steps"]), "reason": st["reason"]}
    s.close()
    print(json.dumps(out))


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "_controls":
        controls(sys.argv[2])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "_record":
        record(sys.argv[2], sys.argv[3])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "_cut":
        cut(*sys.argv[2:6])
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", help="an AutoBio checkout's autobio/ directory at the image's commit, with its experts")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--controls", action="store_true", help="negative controls: wrong trajectories must not succeed")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    sys.path.insert(0, str(HERE / "shared"))
    import rcb_autobio as R

    bad = 0
    for fam in a.only or list(R.FAMILIES):
        inst, orc = HERE / "instances" / f"{fam}.json", HERE / "oracles" / f"{fam}.npz"
        if a.controls:
            c = last_json(run([__file__, "_controls", fam]))
            wrong = [k for k, v in c.items() if (k == "reference") != v["success"]]
            bad += bool(wrong)
            print(f"{'ok  ' if not wrong else 'FAIL'} {fam}: " + "; ".join(
                f"{k} {'1' if v['success'] else '0'}" + (f" (score {v['score']})" if 0 < v["score"] < 1 else "") for k, v in c.items()), flush=True)
            continue
        facts = last_json(run([TOOL, "facts", "--family", fam, "--seed", SEED]))
        if a.check:
            have = json.loads(inst.read_text())
            same = all(have.get(k) == facts.get(k) for k in facts)
            ref = verify(fam, str(inst), str(orc))
            good = same and all(have.get(k) == v for k, v in ref.items())
            bad += not good
            print(f"{'ok  ' if good else 'FAIL'} {fam}: model {facts['model_sha']} start {facts['init_sha']} "
                  f"reference {ref['reference_steps']} steps -> {ref['reference_sha']}", flush=True)
            continue
        if not a.upstream:
            raise SystemExit("--upstream <AutoBio checkout>/autobio (with experts) or --check")
        commit = facts["upstream"]["commit"]
        with tempfile.TemporaryDirectory() as tmp:
            raw, tmp_inst = os.path.join(tmp, "raw.npy"), os.path.join(tmp, "instance.json")
            json.dump(facts, open(tmp_inst, "w"))
            run([__file__, "_record", fam, raw], env={**ENV, "AUTOBIO_ROOT": a.upstream})
            (HERE / "oracles").mkdir(exist_ok=True)
            facts.update(last_json(run([__file__, "_cut", fam, tmp_inst, raw, orc])))
            facts.update(verify(fam, tmp_inst, str(orc)))
        facts["reference_source"] = f"AutoBio's scripted expert ({facts['upstream']['module']}.py @ {commit[:7]}), seed {SEED}"
        (HERE / "instances").mkdir(exist_ok=True)
        inst.write_text(json.dumps(facts, indent=1) + "\n")
        print(f"{fam}: model {facts['model_sha']} start {facts['init_sha']}; reference {facts['reference_rows']} rows "
              f"(expert {facts['expert_rows']}), success after {facts['reference_steps']} steps -> {facts['reference_sha']}; "
              f"~{facts['steps_per_s']} steps/s", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

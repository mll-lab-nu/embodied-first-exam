#!/usr/bin/env python3
"""Freeze the LabUtopia instances and their reference trajectories. Runs INSIDE the eai-labutopia image, with a GPU.

    I=ghcr.io/mll-lab-nu/eai-labutopia:$(cat images/labutopia/VERSION)
    # re-check what is committed (every instance, every reference trajectory in two fresh processes):
    docker run --rm --gpus all --shm-size 8g -v $PWD/scripts/labutopia:/w:ro $I python /w/make_facts.py --check
    # controls: parts of the reference and idling must not succeed; how often random motions and other families'
    # references reach the goal is counted:
    #   ... python /w/make_facts.py --controls
    # a replay that renders ends in the same state as one that does not:
    #   ... python /w/make_facts.py --rendered
    # rebuild instances/ and oracles/ (needs a LabUtopia checkout at the image's commit, WITH its controllers):
    docker run --rm --gpus all --shm-size 8g -v $PWD/scripts/labutopia:/w -v /path/to/LabUtopia:/upstream:ro $I \
        python /w/make_facts.py --upstream /upstream
    # which seeds LabUtopia's own controllers solve, and whether the rules here agree with their verdicts:
    #   ... python /w/make_facts.py --upstream /upstream --scan 0 1 2 3 4

Per family (the seed is families.json's):
- instances/<family>.json: what `rcb_labutopia.py facts` reports from the image (the placement hash, the start-state
  hash, the action layout, cameras, the rule) plus the reference's size and final-state hash.
- oracles/<family>.npz: the joint targets LabUtopia's own scripted controller sends from that instance, one row per
  1/60 s control step (9 position targets, 9 velocity targets, as PhysX holds them: float32). The controller runs from
  the mounted checkout (the image has none) on this tooling's Session, in LabUtopia's own order (state, controller,
  targets, physics step). The rows are cut at the first step at which the family's rule is met; where the rule asks for
  a condition to last and LabUtopia's controller has ended before, the last row is repeated until it is.
Every reference is then replayed by the image's own code in two fresh processes: both must succeed and end in the same
state. Negative control: holding the initial targets for 10 s must not succeed.
"""

import argparse
import concurrent.futures
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TOOL = HERE / "shared" / "rcb_labutopia.py"
ENV = {**os.environ, "RCB_SESSION_LOG": "", "PYTHONPATH": str(HERE / "shared"), "OMNI_KIT_ACCEPT_EULA": "YES", "ACCEPT_EULA": "Y"}
HOLD_EXTRA = 600  # control steps the last row may be repeated for (10 s)
RECORD_LIMIT = 12_000  # control steps a controller may take (200 s): LabUtopia's longest task limit is 5000 frames


def run(args: list, env: dict | None = None, check: bool = True) -> str:
    r = subprocess.run([sys.executable, *map(str, args)], env=env or ENV, cwd="/tmp", capture_output=True, text=True)
    if check and r.returncode != 0:
        fail = [ln for ln in r.stdout.splitlines() if "CUTFAIL" in ln or "py stderr" in ln]
        raise SystemExit(f"{' '.join(map(str, args))}\n" + ("\n".join(fail[-30:]) or (r.stdout + r.stderr)[-3000:]))
    return r.stdout


def tagged(text: str, tag: str) -> dict:
    """The JSON after the last `TAG ` in a process's output (Kit's own messages may leave colour codes before it)."""
    k = text.rfind(tag + " {")
    if k < 0:
        raise SystemExit(f"no {tag} line in:\n{text[-3000:]}")
    return json.loads(text[k + len(tag) + 1:].splitlines()[0])


def seeds() -> dict:
    return {k: int(v.get("seed", 0)) for k, v in json.loads((HERE / "families.json").read_text()).items() if not k.startswith("_")}


def record(family: str, seed: str, out: str) -> None:
    """(subprocess, LABUTOPIA_ROOT = a checkout with controllers) LabUtopia's controller on the Session; saves the
    targets of every step and reports both verdicts."""
    import rcb_labutopia as R

    R.SESSION_LOG = ""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"family": family, "seed": int(seed)}, f)
    s = R.Session(family, instance=f.name, cameras=False)
    s._stop_at_success = False  # run LabUtopia's controller to its own end: the two verdicts are compared
    with R._in_root():
        from factories.controller_factory import create_controller

        s.cfg.collector = {"type": "mock", "compression": None}  # LabUtopia's own no-op demonstration recorder
        np.random.seed(int(seed))  # a controller's own draws (the pour primitive draws its approach heights) are the seed's too
        random.seed(int(seed))
        ctrl = create_controller(s.cfg.controller_type, cfg=s.cfg, robot=s.robot)
        task = s.task
        task.frame_idx = R.SETTLE_STEPS - 1  # LabUtopia's task has been stepped this often when its first state comes
        # LabUtopia's pour primitive turns the wrist joint in velocity mode (it switches that drive's stiffness off). An
        # action here is targets only, no drive modes: while a joint is in that mode, its velocity target is executed
        # as a position target that advances at the commanded velocity (with the velocity target kept).
        integrated = {}

        def switch_dof_control_mode(dof_index, mode):
            if mode == "velocity":
                integrated.setdefault(int(dof_index), None)
            else:
                integrated.pop(int(dof_index), None)

        s.ctrl.switch_dof_control_mode = switch_dof_control_mode
        rows, trace, done, success, ended, n_integrated = [], [], False, False, "limit", 0
        while s.steps < RECORD_LIMIT:
            st = task.step()
            if task.need_reset():
                ended = "LabUtopia's frame limit for the task"
                break
            action, done, success = ctrl.step(st)
            if action is not None:
                s.ctrl.apply_action(action)
            if done:
                ended = "controller done"
                break
            row = s.command()
            for dof in integrated:
                if integrated[dof] is None:
                    integrated[dof] = float(s.joint_positions()[dof])
                integrated[dof] += row[R.N_DOF + dof] * R.CONTROL_DT
                row[dof] = integrated[dof]
            n_integrated += bool(integrated)
            row = s._row(row)  # as the Session executes it (float32)
            rows.append(row)
            s.step(row)
            if s.steps % 10 == 0:
                trace.append({"step": s.steps, **{k: v for k, v in s.rule.values().items() if isinstance(v, (int, float, bool, str))}})
        rows = np.asarray(rows, dtype=np.float64).reshape(-1, R.N_ACT)
        own = s.first_success_step
        extra = 0
        while own is None and extra < HOLD_EXTRA and len(rows):  # does the rule come true while the last targets are held?
            s.step(rows[-1])
            extra += 1
            own = s.first_success_step
    np.save(out, rows)
    lim = s.action_limits()
    print("RECORD " + json.dumps({
        "family": family, "seed": int(seed), "placement_sha": s.placement_sha, "init_sha": s.init_sha,
        "controller_rows": int(len(rows)), "controller_done": bool(done), "controller_success": bool(success), "ended": ended,
        "failure_reason": str(getattr(ctrl, "_last_failure_reason", "") or ""),
        "rule_first_success_step": own, "rule_state": s.rule.state(), "rule_values": {k: v for k, v in s.rule.values().items() if isinstance(v, (int, float, bool, str))},
        "float32_exact": bool(np.array_equal(rows, rows.astype(np.float32).astype(np.float64))),
        "outside_limits": int(((rows < lim[:, 0]) | (rows > lim[:, 1])).any(axis=1).sum()) if len(rows) else 0,
        "max_abs_velocity_target": float(np.abs(rows[:, R.N_DOF:]).max()) if len(rows) else 0.0,
        "velocity_mode_rows": int(n_integrated),
        "beyond_limits": {str(k): [float((lim[k, 0] - rows[:, k].min())), float((rows[:, k].max() - lim[k, 1]))] for k in range(R.N_ACT)
                          if len(rows) and (rows[:, k].min() < lim[k, 0] or rows[:, k].max() > lim[k, 1])},
        "trace": trace[-400:],
    }), flush=True)
    R.finish(0)


def cut(family: str, instance: str, raw: str, out: str) -> None:
    """(subprocess, the image's own LabUtopia) Replay, cut at the first success (holding the last row if the rule needs
    it); negative control."""
    import rcb_labutopia as R

    R.SESSION_LOG = ""
    s = R.Session(instance=instance, cameras=False)
    rows = np.load(raw)
    t0 = time.time()
    st = s.replay(rows)
    rate = st["steps"] / max(time.time() - t0, 1e-9)
    held = 0
    while not s.done and held < HOLD_EXTRA:
        s.step(rows[-1])
        held += 1
    st = s.status()
    if not st["success"]:
        print(f"CUTFAIL {family}: LabUtopia's controller does not meet the rule from the frozen instance: {st}", flush=True)
        R.finish(1)
    keep = np.concatenate([rows, np.tile(rows[-1], (held, 1))])[: st["steps"]]
    s.reset()
    s.step(s.command(), n=600)
    idle = s.status()
    if idle["success"]:
        print(f"CUTFAIL {family}: holding the initial targets for 10 s succeeds: {idle}", flush=True)
        R.finish(1)
    np.savez_compressed(out, actions=keep.astype(np.float32))
    print("CUT " + json.dumps({"reference_rows": int(len(keep)), "controller_rows": int(len(rows)), "held_rows": int(max(0, len(keep) - len(rows))),
                               "steps_per_s": int(float(f"{rate:.1g}"))}), flush=True)  # one significant digit: a wall-clock measurement
    R.finish(0)


def verify(family: str, instance: str, oracle: str) -> dict:
    """Two fresh processes replay the reference with the image's own code."""
    with tempfile.TemporaryDirectory() as tmp:
        traj = os.path.join(tmp, "t.npz")
        np.savez(traj, actions=np.load(oracle)["actions"].astype(np.float64), task=family)
        a = tagged(run([TOOL, "replay", "--instance", instance, "--traj", traj]), "RESULT")
        b = tagged(run([TOOL, "replay", "--instance", instance, "--traj", traj]), "RESULT")
    ok = a["success"] and b["success"] and a["state_sha"] == b["state_sha"] and a["instance_ok"] and b["instance_ok"]
    if not ok:
        raise SystemExit(f"{family}: the reference does not replay to one successful state in two fresh processes:\n{a}\n{b}")
    return {"reference_steps": int(a["steps"]), "reference_sha": a["state_sha"]}


MUST_FAIL = ("first_half", "all_but_last_30", "initial_targets_10s")
N_RANDOM = 10


def random_motion(R, s, k: int) -> np.ndarray:
    """A smooth random motion: six random arm configurations within the joints' ranges, each reached in 1.5 s from the
    one before and held 0.5 s, the gripper open or closed at random (12 s in all)."""
    rng = np.random.default_rng(1000 + k)
    q = s.command()[: R.N_DOF].copy()
    rows = []
    for _ in range(6):
        nxt = np.concatenate([rng.uniform(s.q_lo[:7], s.q_hi[:7]), np.full(2, rng.choice([0.0, 0.04]))])
        rows += [q + (nxt - q) * (i + 1) / 90 for i in range(90)] + [nxt] * 30
        q = nxt
    return np.concatenate([np.asarray(rows), np.zeros((len(rows), R.N_DOF))], axis=1)


def controls(family: str) -> None:
    """(subprocess, the image's own LabUtopia) What wrong trajectories do. MUST_FAIL: parts of the reference and idling.
    Reported, not required: the reference reversed, noise, ten smooth random motions and every other family's
    reference, which tell how often the goal is reached by a motion that was not made for it. One process: the
    resets between the cases are approximate, which these controls do not mind."""
    import rcb_labutopia as R

    R.SESSION_LOG = ""
    s = R.Session(instance=str(HERE / "instances" / f"{family}.json"), cameras=False)
    ref = np.load(HERE / "oracles" / f"{family}.npz")["actions"].astype(np.float64)
    rng = np.random.default_rng(0)
    lim = s.action_limits()
    noise = np.concatenate([rng.uniform(lim[:R.N_DOF, 0], lim[:R.N_DOF, 1], size=(240, R.N_DOF)), np.zeros((240, R.N_DOF))], axis=1)
    cases = {
        "reference": ref,
        "first_half": ref[: len(ref) // 2],
        "all_but_last_30": ref[:-30],
        "initial_targets_10s": np.tile(s.command(), (600, 1)),
        "reversed": ref[::-1],
        "noise_4s": noise,
    }
    for k in range(N_RANDOM):
        cases[f"random_{k}"] = random_motion(R, s, k)
    for other in R.FAMILIES:
        o = HERE / "oracles" / f"{other}.npz"
        if other != family and o.exists():
            cases[f"reference_of_{other}"] = np.load(o)["actions"].astype(np.float64)
    out = {}
    for name, rows in cases.items():
        st = s.replay(rows)
        out[name] = {"success": bool(st["success"]), "steps": int(st["steps"])}
    print("CONTROLS " + json.dumps(out), flush=True)
    R.finish(0)


def controls_line(fam: str, out: dict) -> tuple:
    wrong = [k for k in MUST_FAIL if out[k]["success"]] + ([] if out["reference"]["success"] else ["reference"])
    rnd = [k for k in out if k.startswith("random_") and out[k]["success"]]
    cross = [k[len("reference_of_"):] for k in out if k.startswith("reference_of_") and out[k]["success"]]
    n_cross = sum(k.startswith("reference_of_") for k in out)
    return (not wrong, f"{'ok  ' if not wrong else 'FAIL'} {fam}: reference {int(out['reference']['success'])}; "
            + "; ".join(f"{k} {int(out[k]['success'])}" for k in MUST_FAIL)
            + f" | reversed {int(out['reversed']['success'])}; noise_4s {int(out['noise_4s']['success'])}; "
            f"random motions {len(rnd)}/{N_RANDOM}; other families' references {len(cross)}/{n_cross}"
            + (f" ({', '.join(cross)})" if cross else ""))


def build(fam: str, seed: int, upstream: str) -> str:
    inst, orc = HERE / "instances" / f"{fam}.json", HERE / "oracles" / f"{fam}.npz"
    facts = tagged(run([TOOL, "facts", "--family", fam, "--seed", seed]), "FACTS")
    with tempfile.TemporaryDirectory() as tmp:
        raw, tmp_inst = os.path.join(tmp, "raw.npy"), os.path.join(tmp, "instance.json")
        json.dump(facts, open(tmp_inst, "w"))
        rec = tagged(run([__file__, "_record", fam, seed, raw], env={**ENV, "LABUTOPIA_ROOT": upstream}), "RECORD")
        if not rec["controller_success"] or rec["rule_first_success_step"] is None:
            raise SystemExit(f"{fam} seed {seed}: LabUtopia's controller does not succeed ({rec['ended']}; {rec['failure_reason']}) "
                             f"or the rule is not met (step {rec['rule_first_success_step']})")
        if rec["placement_sha"] != facts["placement_sha"] or not rec["float32_exact"] or rec["outside_limits"]:
            raise SystemExit(f"{fam}: the recording does not match the image's instance or the action's range: { {k: v for k, v in rec.items() if k != 'trace'} }")
        (HERE / "oracles").mkdir(exist_ok=True)
        facts.update(tagged(run([__file__, "_cut", fam, tmp_inst, raw, orc]), "CUT"))
        facts.update(verify(fam, tmp_inst, str(orc)))
    facts.pop("build_s", None)  # a wall-clock measurement
    facts["controller_done_step"] = rec["controller_rows"]
    facts["velocity_mode_rows"] = rec["velocity_mode_rows"]
    facts["reference_source"] = (f"LabUtopia's scripted controller ({facts['upstream']['controller_type']}, config "
                                 f"{facts['upstream']['config']} @ {str(facts['upstream']['commit'])[:7]}), seed {seed}")
    (HERE / "instances").mkdir(exist_ok=True)
    inst.write_text(json.dumps(facts, indent=1) + "\n")
    return (f"{fam}: seed {seed} placement {facts['placement_sha']} start {facts['init_sha']}; reference {facts['reference_rows']} rows "
            f"(controller {facts['controller_rows']}, held {facts['held_rows']}), success after {facts['reference_steps']} steps -> "
            f"{facts['reference_sha']}; ~{facts['steps_per_s']} steps/s")


HOST_BITS = ("init_sha", "reference_sha", "reference_steps")  # what PhysX's last bits can change from host to host


def check(fam: str, seed: int) -> tuple:
    """(good, line). FAIL: the instance is not the recorded one (placements, layout, rule) or the reference does not
    replay to success in one state in two fresh processes. `ok` : everything equals the record. `ok*`: the instance and
    the replays are sound but a state hash differs from the record, which was made on another host."""
    inst, orc = HERE / "instances" / f"{fam}.json", HERE / "oracles" / f"{fam}.npz"
    facts = tagged(run([TOOL, "facts", "--family", fam, "--seed", seed]), "FACTS")
    facts.pop("build_s", None)
    have = json.loads(inst.read_text())
    try:
        ref = verify(fam, str(inst), str(orc))
    except SystemExit as exc:
        return False, f"FAIL {fam}: {str(exc)[:600]}"
    diff = [k for k in facts if have.get(k) != facts.get(k)] + [k for k, v in ref.items() if have.get(k) != v]
    hard = [k for k in diff if k not in HOST_BITS]
    mark = "FAIL" if hard else ("ok* " if diff else "ok  ")
    return (not hard, f"{mark} {fam}: placement {facts['placement_sha']} start {facts['init_sha']} reference "
            f"{ref['reference_steps']} steps -> {ref['reference_sha']}"
            + (f"  differs from the record: {diff}" + ("" if hard else " (this host's PhysX differs in the last bits)") if diff else ""))


ASSET_ERRORS = ("comp error", "SdrShaderNode", "Could not open asset", "Failed to open layer")


def rendered(fam: str) -> tuple:
    """A replay that renders (the renderer on, a video written) must end in the reference's recorded state, and the
    renderer must not report a file it could not find: a material that does not compile or a reference that does not
    open (USD's own diagnostics are switched on for this run) means the image's mirror of NVIDIA's asset server
    (images/labutopia/nvidia_assets.sha256) is missing something."""
    inst, orc = HERE / "instances" / f"{fam}.json", HERE / "oracles" / f"{fam}.npz"
    have = json.loads(inst.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        traj = os.path.join(tmp, "t.npz")
        np.savez(traj, actions=np.load(orc)["actions"].astype(np.float64), task=fam)
        out = run([TOOL, "replay", "--instance", inst, "--traj", traj, "--video", os.path.join(tmp, "v.mp4")],
                  env={**ENV, "RCB_KIT_ARGS": "--/persistent/app/usd/muteUsdDiagnostics=false"})
    r = tagged(out, "RESULT")
    missing = sorted({ln.split("] ")[-1].strip()[:200] for ln in out.splitlines() if any(k in ln for k in ASSET_ERRORS)})
    good = bool(r["success"] and r.get("video") and r["state_sha"] == have["reference_sha"] and not missing)
    return good, (f"{'ok  ' if good else 'FAIL'} {fam}: rendered replay -> {r['state_sha']} (reference {have['reference_sha']}), "
                  f"video {bool(r.get('video'))}, first frames after {r.get('first_frame_s')} s"
                  + ("; no missing file reported" if not missing else "; MISSING: " + " | ".join(missing)))


def scan(fam: str, seed: int, upstream: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = run([__file__, "_record", fam, seed, os.path.join(tmp, "raw.npy")], env={**ENV, "LABUTOPIA_ROOT": upstream}, check=False)
    try:
        r = tagged(out, "RECORD")
    except SystemExit:
        return f"{fam:14s} seed {seed}: ERROR {out[-300:]!r}"
    agree = bool(r["controller_success"]) == (r["rule_first_success_step"] is not None)
    return (f"{fam:14s} seed {seed}: controller {'1' if r['controller_success'] else '0'} after {r['controller_rows']:5d} rows ({r['ended']}"
            f"{'; ' + r['failure_reason'] if r['failure_reason'] else ''}); rule {'met at step ' + str(r['rule_first_success_step']) if r['rule_first_success_step'] is not None else 'not met'}"
            f"; {'agree' if agree else 'DISAGREE'}; float32 {r['float32_exact']} outside {r['outside_limits']} {r['beyond_limits'] or ''} |qd|max {r['max_abs_velocity_target']:.2f} velocity-mode rows {r['velocity_mode_rows']}; {json.dumps(r['rule_values'])[:260]}")


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("_controls", "_record", "_cut"):
        {"_controls": controls, "_record": record, "_cut": cut}[sys.argv[1]](*sys.argv[2:])
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", help="a LabUtopia checkout at the image's commit, with its controllers")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--controls", action="store_true", help="what wrong trajectories do: parts of the reference and idling must fail; random motions and other families' references are counted")
    ap.add_argument("--rendered", action="store_true", help="a replay with the renderer on ends in the reference's state")
    ap.add_argument("--scan", nargs="*", type=int, help="seeds: LabUtopia's controller and the rule on each, nothing is written")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=1, help="simulators at a time (each takes about 8 GB of RAM)")
    a = ap.parse_args()
    sys.path.insert(0, str(HERE / "shared"))
    import rcb_labutopia as R

    seed_of = seeds()
    fams = a.only or [f for f in R.FAMILIES if f in seed_of]
    bad = 0
    with concurrent.futures.ThreadPoolExecutor(max(1, a.jobs)) as pool:
        if a.scan is not None:
            if not a.upstream:
                raise SystemExit("--scan needs --upstream")
            for line in pool.map(lambda fs: scan(fs[0], fs[1], a.upstream), [(f, sd) for f in fams for sd in (a.scan or [0])]):
                print(line, flush=True)
        elif a.controls:
            for fam, out in zip(fams, pool.map(lambda f: tagged(run([__file__, "_controls", f]), "CONTROLS"), fams)):
                good, line = controls_line(fam, out)
                bad += not good
                print(line, flush=True)
        elif a.check:
            for good, line in pool.map(lambda f: check(f, seed_of[f]), fams):
                bad += not good
                print(line, flush=True)
        elif a.rendered:
            for good, line in pool.map(rendered, fams):
                bad += not good
                print(line, flush=True)
        else:
            if not a.upstream:
                raise SystemExit("--upstream <LabUtopia checkout> (with controllers), --check, --controls or --scan")
            for line in pool.map(lambda f: build(f, seed_of[f], a.upstream), fams):
                print(line, flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

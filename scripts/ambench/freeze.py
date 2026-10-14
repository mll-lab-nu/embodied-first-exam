#!/usr/bin/env python3
"""Freeze one AM-Bench instance and record its reference rows (docs/benchmarks/ambench.md). Run on a host with docker, an
NVIDIA GPU and the image built (images/ambench/BUILD_ONLY); writes scripts/ambench/frozen/<task>-iNN/ and the task's entry
in scripts/ambench/instances.json.

    python3 scripts/ambench/freeze.py --task press_button --env-id PressButton-Am-FAHexa-Abs-PID-Direct-v0 --seed 0 --id 0 \\
        --expert <an AM-Bench checkout at the image's commit>/source/ambench/ambench/policies

1. record (in the image, --network none): the tooling's Session builds the instance (AM-Bench's seeded reset) and AM-Bench's
   scripted expert for the task, mounted read-only from the checkout OUTSIDE the image (the image has none: PROTOCOL §2.7),
   drives it in closed loop (no injected noise) until the episode ends; its rows are what the tooling executed, followed
   by --pad-s (2 s) of holding its last command. Writes instance.json (environment id, seed, the start's state hash) and
   oracle_actions.npy.
2. verify (in the image, no expert mounted): two replays with the grader's own CLI (`rcb_ambench.py replay`), each in a fresh
   process; both must succeed and end in the same state. `--verify-only` runs this step alone on the frozen rows (after a
   change of the tooling) and updates the hashes in instances.json.
The recording process's own episode need not be bit-identical to the replays (the expert reads the state in between); the
fresh-process replays are what the grader runs, so they decide.
"""
from __future__ import annotations
import argparse, json, os, pathlib, subprocess, sys, time

_ME = pathlib.Path(__file__).resolve()
ROOT = _ME.parents[2] if len(_ME.parents) > 2 else _ME.parent     # (inside the image the script is /freeze/freeze.py)
HERE = ROOT / "scripts/ambench"
EXPERTS = {"PressButton": ("ambench.policies.scripted.press_button", "PressButtonPolicy"),
           "PushSlider": ("ambench.policies.scripted.push_slider", "PushSliderPolicy"),
           "RotateValve": ("ambench.policies.scripted.rotate_valve", "RotateValvePolicy"),
           "TossBall": ("ambench.policies.scripted.toss_ball", "TossBallPolicy")}


def inside_record(env_id: str, seed: int, out: str, npz: str, pad_s: float, tries: int) -> int:
    """In the image: build the instance with the tooling, run the expert mounted at /expert, save its executed rows."""
    sys.path.insert(0, "/opt/tools")
    import importlib
    import numpy as np
    import rcb_ambench as R
    s = R.Session({"env_id": env_id, "seed": seed})
    import torch
    import ambench.policies as P
    P.__path__.append("/expert")                      # the expert, read-only, from outside the image
    mod, cls = EXPERTS[env_id.split("-")[0]]
    t0 = time.time()
    # Some experts sample their waypoints and timings from torch's RNG (TossBall's release); try k > 0 seeds that RNG with k
    # before the expert plans, on the same frozen instance, until one succeeds live (the replays decide afterwards)
    for k in range(tries):
        if k:
            s.reset(); torch.manual_seed(k)
        policy = getattr(importlib.import_module(mod), cls)(env=s.env, inject_noise=False)
        with torch.inference_mode():
            while not s.done:
                s.step(policy.advance(s.obs, 0).detach().cpu().numpy().reshape(-1))
        print("TRY " + json.dumps({"try": k, "success": s.succeeded, "control_steps": s.n_steps}), flush=True)
        if s.succeeded:
            break
    inst = {"env_id": env_id, "seed": seed, "task": env_id.split("-")[0], "action_dim": R.ACTION_DIM,
            "control_hz": R.CONTROL_HZ, "episode_length_s": float(s.env.cfg.episode_length_s), "initial_sha": s.initial_sha}
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "instance.json").write_text(json.dumps(inst, indent=1) + "\n")
    rows = s.actions()
    # the expert's rows end where its live episode succeeded; a replay can be a step or two behind (the live episode's state
    # reads change its numerics), so the reference holds the last command a little longer: rows after the replay's own
    # success never run
    rows = np.vstack([rows, np.repeat(rows[-1:], int(round(pad_s * R.CONTROL_HZ)), axis=0)])
    np.save(o / "oracle_actions.npy", rows)
    np.savez(npz, task=np.array(env_id), actions=rows)             # the same rows as a trajectory file, for the replays
    st = o.stat()                                     # the files belong to the directory's (the host user's) owner
    for f in (o / "instance.json", o / "oracle_actions.npy", pathlib.Path(npz)):
        os.chown(f, st.st_uid, st.st_gid)
    print("RECORD " + json.dumps({**s.status(), "expert_try": k, "clipped": s.n_clipped, "wall_s": round(time.time() - t0, 1)}), flush=True)
    os._exit(0)


def docker(args: list[str], mounts: dict[str, str], log: pathlib.Path, timeout: float = 2400.0, gpu: bool = True) -> str:
    """One container run; a run that hangs (Isaac can hang at exit after an error, e.g. out of GPU memory) is killed."""
    image = f"ghcr.io/mll-lab-nu/eai-ambench:{(ROOT / 'images/ambench/VERSION').read_text().strip()}"
    name = f"ambench-freeze-{log.stem}-{os.getpid()}"
    cmd = ["docker", "run", "--rm", "--name", name] + (["--gpus", "all"] if gpu else []) + ["--network", "none", "--shm-size", "8g",
           "-v", "rcb_ambench_freeze_cache:/cache"]
    for src, dst in mounts.items():
        cmd += ["-v", f"{src}:{dst}"]
    try:
        out = subprocess.run(cmd + [image] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "kill", name], capture_output=True)
        out = (exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")) + "\n[freeze] killed: timeout\n"
    log.write_text(out)
    return out


def last_json(text: str, prefix: str = "") -> dict:
    v = {}
    for line in text.splitlines():
        if line.startswith(prefix + "{"):
            try:
                v = json.loads(line[len(prefix):])
            except ValueError:
                pass
    return v


def record(a, fz: pathlib.Path, logs: pathlib.Path, tools: dict) -> dict:
    """Step 1 in the image, with the expert mounted read-only from outside it."""
    out = docker(["python", "/freeze/freeze.py", "--inside-record", "--task", a.task, "--env-id", a.env_id, "--seed", str(a.seed),
                  "--out", "/w", "--npz", f"/l/{a.task}-oracle.npz", "--pad-s", str(a.pad_s), "--tries", str(a.tries)],
                 {**tools, str(pathlib.Path(a.expert).resolve()): "/expert:ro", str(fz.resolve()): "/w", str(logs.resolve()): "/l"},
                 logs / f"{a.task}-record.log")
    rec = last_json(out, "RECORD ")
    print("record:", json.dumps(rec), flush=True)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True); ap.add_argument("--env-id", required=True)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--id", type=int, default=0)
    ap.add_argument("--expert", help="AM-Bench's policies/ directory (outside the image)")
    ap.add_argument("--logs", default="/tmp/ambench-freeze-logs")
    ap.add_argument("--pad-s", type=float, default=2.0, help="seconds of holding the expert's last command after its rows")
    ap.add_argument("--tries", type=int, default=1, help="expert runs (try k > 0 seeds torch's RNG with k) until one succeeds live")
    ap.add_argument("--verify-only", action="store_true",
                    help="no recording: replay the frozen rows (step 2) and update the task's hashes in instances.json")
    ap.add_argument("--inside-record", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS); ap.add_argument("--npz", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.inside_record:
        try:
            return inside_record(a.env_id, a.seed, a.out, a.npz, a.pad_s, a.tries)
        except BaseException:  # noqa: BLE001 — Isaac Sim can hang at exit after an error
            import traceback
            traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(1)
    fz = HERE / "frozen" / f"{a.task}-i{a.id:02d}"
    logs = pathlib.Path(a.logs); logs.mkdir(parents=True, exist_ok=True); fz.mkdir(parents=True, exist_ok=True)
    tools = {str(HERE / "shared"): "/opt/tools:ro", str(pathlib.Path(__file__).resolve().parent): "/freeze:ro"}
    if a.verify_only:
        rec: dict = {}
        # the frozen rows as a trajectory file (numpy is in the image, not necessarily on the host)
        docker(["python", "-c", "import numpy as np, os, sys; p = '/l/' + sys.argv[1] + '-oracle.npz'; "
                "np.savez(p, task=np.array(sys.argv[2]), actions=np.load('/w/oracle_actions.npy')); st = os.stat('/l'); "
                "os.chown(p, st.st_uid, st.st_gid)", a.task, a.env_id],
               {str(fz.resolve()): "/w:ro", str(logs.resolve()): "/l"}, logs / f"{a.task}-npz.log", gpu=False)
    else:
        if not a.expert:
            ap.error("--expert is required (or --verify-only)")
        rec = record(a, fz, logs, tools)
        if not rec.get("success"):
            print(f"the expert did not succeed (log {logs}/{a.task}-record.log)"); return 1
    reps = []
    for i in (1, 2):
        o = docker(["python", "/opt/tools/rcb_ambench.py", "replay", "--instance", "/w/instance.json", "--traj", f"/l/{a.task}-oracle.npz"],
                   {**tools, str(fz.resolve()): "/w:ro", str(logs.resolve()): "/l:ro"}, logs / f"{a.task}-replay{i}.log")
        r = last_json(o); reps.append(r)
        print(f"replay {i}:", json.dumps(r), flush=True)
    outs = [(r.get("replays") or [{}])[0] for r in reps]
    ok = all(r.get("instance_matches") for r in reps) and all(o.get("success") for o in outs) and len({o.get("state_sha") for o in outs}) == 1
    if not ok:
        print("the fresh-process replays do not both succeed in the same state: not frozen"); return 1
    import fcntl
    reg_p = HERE / "instances.json"
    lock = open(HERE / ".instances.lock", "w"); fcntl.flock(lock, fcntl.LOCK_EX)     # parallel freezes
    reg = json.loads(reg_p.read_text()) if reg_p.exists() else {"modes": ["privileged"], "tasks": {}}
    inst = json.loads((fz / "instance.json").read_text())
    entry = reg["tasks"].get(a.task, {}) if a.verify_only else {
        "provenance": "AM-Bench's scripted expert for the task (policies/scripted, no injected noise), run in closed loop on "
                      "this instance by scripts/ambench/freeze.py"
                      + (f" (expert try {rec['expert_try']}: torch's RNG seeded with {rec['expert_try']} before it planned; the "
                         "earlier tries did not succeed live)" if rec.get("expert_try") else "")
                      + f", followed by {a.pad_s:g} s of holding its last command",
        "recorded": time.strftime("%Y-%m-%d")}
    reg["tasks"][a.task] = {"id": a.id, "env_id": a.env_id, "seed": a.seed, "initial_sha": inst["initial_sha"],
                            "oracle_rows": int(outs[0]["executed_rows"]), "oracle_final_sha": outs[0]["state_sha"],
                            "provenance": entry.get("provenance", ""), "recorded": entry.get("recorded", ""),
                            "verified": time.strftime("%Y-%m-%d") + ": two fresh-process replays with the grader's CLI succeed "
                                        "at control step %d and end in the same state" % int(outs[0]["executed_rows"])}
    reg["tasks"] = dict(sorted(reg["tasks"].items()))
    reg_p.write_text(json.dumps(reg, indent=1) + "\n")
    fcntl.flock(lock, fcntl.LOCK_UN); lock.close(); (HERE / ".instances.lock").unlink(missing_ok=True)
    print(f"frozen {fz.relative_to(ROOT)}: success at row {outs[0]['executed_rows']}, end state {outs[0]['state_sha'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

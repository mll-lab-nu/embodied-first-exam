#!/usr/bin/env python3
"""The reference trajectories of RoboSafeBench's privileged tasks (each task's solution/trajectory.npz).

A privileged task's reference is its standard twin's: RoboSafeBench's native reference of the member, streamed live
through the standard service (the twin's environment/sim/server.py and solution/oracle_replay.py, exactly as a Harbor
oracle trial runs them) and finalized as at the end of a trial. The service's journal (data/trajectory.npz: the rows,
the action types and the notes; data/picture_events.jsonl) is that episode in the privileged trajectory format
(rcb_rsb_privileged.py). The trajectory is then replayed by the privileged verifier's replay in two fresh processes with
the image's package and once with the package as scrub.py leaves it for the agent's container; the reference is kept
only when the live episode passed and all three replays pass with its outcome and the same end state. The last check
shows that the scrub changes nothing the verdict reads.

    # inside the eai-robosafe image (the twin's sim service needs requests, installed when missing):
    python3 scripts/robosafe/privileged_oracles.py one tasks/<base>-standard OUT_DIR
    # on a host with podman and the image, all bases, N at a time, then copy the passing ones into oracles_privileged/:
    python3 scripts/robosafe/privileged_oracles.py all WORK_DIR [--jobs N] [--image IMAGE]
    python3 scripts/robosafe/privileged_oracles.py collect WORK_DIR
`collect` writes scripts/robosafe/oracles_privileged/<base>.npz and <base>.json, which gen_privileged.py render puts
into the tasks; after committing the rendered tasks, delete oracles_privileged/ (the tasks hold the references).
The privileged tooling (rcb_rsb_privileged.py, scrub.py) is the canonical privileged task's (check_release.py LAYERS).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import check_release  # noqa: E402

TOOLS = check_release.shared("privileged", "rcb_rsb_privileged.py").parent   # with scrub.py
OUT = HERE / "oracles_privileged"
IMAGE = "ghcr.io/mll-lab-nu/eai-robosafe:0.5.4"


def run_live(task: pathlib.Path, out: pathlib.Path) -> None:
    """The standard twin's reference through its own service, finalized (SIGUSR1) as Harbor's collect hook does."""
    sim, data = out / "sim", out / "data"
    sim.mkdir(parents=True)
    data.mkdir()
    for f in (task / "environment" / "sim").iterdir():
        shutil.copyfile(f, sim / f.name)
    env = {**os.environ, "RCB_INSTANCE": str(sim / "instance.json"), "RCB_DATA": str(data), "RCB_WALL_CLOCK_S": "3600",
           "RCB_STARTUP_TIMEOUT_S": "300", "RCB_RESET_BUDGET": "0", "PYTHONPATH": str(sim)}
    env.pop("ROBOSAFE_THIRD_PARTY", None)
    with (out / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, str(sim / "server.py")], env=env, stdout=log, stderr=log, cwd="/tmp")
    try:
        try:
            import requests  # noqa: F401,PLC0415
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests", "pillow", "scipy"], check=True)
        sol = pathlib.Path("/solution")
        sol.mkdir(exist_ok=True)
        for f in (task / "solution").iterdir():
            shutil.copyfile(f, sol / f.name)
        app = pathlib.Path("/app/output")
        shutil.rmtree(app, ignore_errors=True)
        app.mkdir(parents=True)
        cenv = {**os.environ, "PYTHONPATH": str(task / "environment")}
        with (out / "oracle.log").open("w") as log:
            subprocess.run([sys.executable, str(sol / "oracle_replay.py")], env=cenv, stdout=log, stderr=log,
                           cwd="/app", timeout=3300, check=False)
        pid = int((data / "server.pid").read_text())
        for _ in range(120):
            os.kill(pid, signal.SIGUSR1)
            time.sleep(5)
            final = data / "final.json"
            if final.exists() and json.loads(final.read_text()).get("finalized"):
                break
        else:
            raise RuntimeError("the service never finalized the episode")
    finally:
        server.terminate()
        server.wait(timeout=60)


def convert(out: pathlib.Path) -> pathlib.Path:
    sys.path[:0] = [str(TOOLS), str(out / "sim")]
    import numpy as np  # noqa: PLC0415
    import rcb_rsb_privileged as P  # noqa: PLC0415
    z = np.load(out / "data" / "trajectory.npz", allow_pickle=False)
    pe = out / "data" / "picture_events.jsonl"
    events = [json.loads(line) for line in pe.read_text().splitlines() if line.strip()] if pe.exists() else []
    inst = json.loads((out / "sim" / "instance.json").read_text())
    path = out / "trajectory.npz"
    P.save({"actions": z["actions"], "types": json.loads(str(z["types"])), "notes": json.loads(str(z["notes"])),
            "picture_events": events, "start_sha": inst["state_sha"]}, str(path))
    return path


def replays(out: pathlib.Path, traj: pathlib.Path) -> list[dict]:
    tool = out / "sim" / "rcb_rsb_privileged.py"
    shutil.copyfile(TOOLS / "rcb_rsb_privileged.py", tool)
    inst = str(out / "sim" / "instance.json")
    cmd = lambda o: [sys.executable, str(tool), "replay", "--instance", inst, "--traj", str(traj), "--out", str(o)]
    procs = [subprocess.Popen(cmd(out / f"replay{i}.json"), stdout=(out / f"replay{i}.log").open("w"),
                              stderr=subprocess.STDOUT, cwd="/tmp") for i in (1, 2)]
    for p in procs:
        p.wait(timeout=3900)
    import robosafebench  # noqa: PLC0415
    scrubbed = out / "scrubbed"
    shutil.copytree(pathlib.Path(robosafebench.__file__).resolve().parent, scrubbed / "robosafebench")
    subprocess.run([sys.executable, str(TOOLS / "scrub.py"), str(scrubbed / "robosafebench")], check=True,
                   stdout=(out / "scrub.log").open("w"), stderr=subprocess.STDOUT)
    env = {**os.environ, "PYTHONPATH": str(scrubbed)}
    subprocess.run(cmd(out / "replay_scrubbed.json"), env=env, stdout=(out / "replay_scrubbed.log").open("w"),
                   stderr=subprocess.STDOUT, cwd="/tmp", timeout=3900, check=False)
    shutil.rmtree(scrubbed)
    return [json.loads((out / f"{n}.json").read_text()) for n in ("replay1", "replay2", "replay_scrubbed")]


def one(task: pathlib.Path, out: pathlib.Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    run_live(task, out)
    traj = convert(out)
    r = replays(out, traj)
    live = json.loads((out / "data" / "final.json").read_text())
    lv = json.loads((out / "data" / "verdict.json").read_text())
    res = {"live_success": bool(live.get("success")), "live_outcome": lv.get("outcome"),
           "replay_success": [x.get("success") for x in r],
           "replay_outcome": [(x.get("verdict") or {}).get("outcome") for x in r],
           "bad": [x.get("bad_trajectory") for x in r], "same_sha": len({x.get("state_sha") for x in r}) == 1,
           "n_actions": r[0].get("n_actions"), "steps": r[0].get("steps")}
    res["ok"] = (res["live_success"] and all(res["replay_success"]) and res["same_sha"]
                 and all(o == res["live_outcome"] for o in res["replay_outcome"]))
    (out / "RESULT.json").write_text(json.dumps(res))
    return res


def bases() -> list[str]:
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("gen_privileged", HERE / "gen_privileged.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g.bases()


def run_all(work: pathlib.Path, jobs: int, image: str) -> int:
    work.mkdir(parents=True, exist_ok=True)

    def go(base: str) -> tuple[str, dict]:
        out = work / base
        if (out / "RESULT.json").exists() and json.loads((out / "RESULT.json").read_text()).get("ok"):
            return base, json.loads((out / "RESULT.json").read_text())
        subprocess.run(["podman", "run", "--rm", "-v", f"{ROOT}:{ROOT}:ro", "-v", f"{work}:{work}", image, "python",
                        str(HERE / "privileged_oracles.py"), "one", str(ROOT / "tasks" / f"{base}-standard"), str(out)],
                       stdout=(work / f"{base}.log").open("w"), stderr=subprocess.STDOUT, check=False)
        r = out / "RESULT.json"
        return base, json.loads(r.read_text()) if r.exists() else {"ok": False}
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
        results = dict(ex.map(go, bases()))
    bad = [b for b, r in results.items() if not r.get("ok")]
    print(f"{len(results) - len(bad)} of {len(results)} references pass; failed: {bad}")
    return 1 if bad else 0


def collect(work: pathlib.Path) -> int:
    OUT.mkdir(exist_ok=True)
    missing = []
    for base in bases():
        r = work / base / "RESULT.json"
        res = json.loads(r.read_text()) if r.exists() else {}
        if not res.get("ok"):
            missing.append(base)
            continue
        shutil.copyfile(work / base / "trajectory.npz", OUT / f"{base}.npz")
        (OUT / f"{base}.json").write_text(json.dumps({"rows": res["n_actions"], "steps": res["steps"],
                                                      "outcome": res["live_outcome"]}, sort_keys=True) + "\n")
    print(f"collected {len(bases()) - len(missing)} references into {OUT.relative_to(ROOT)}; missing: {missing}")
    return 1 if missing else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("task", type=pathlib.Path)
    o.add_argument("out", type=pathlib.Path)
    a = sub.add_parser("all")
    a.add_argument("work", type=pathlib.Path)
    a.add_argument("--jobs", type=int, default=8)
    a.add_argument("--image", default=IMAGE)
    c = sub.add_parser("collect")
    c.add_argument("work", type=pathlib.Path)
    args = p.parse_args(argv)
    if args.cmd == "one":
        res = one(args.task.resolve(), args.out.resolve())
        print(json.dumps(res))
        return 0 if res["ok"] else 1
    if args.cmd == "all":
        return run_all(args.work.resolve(), args.jobs, args.image)
    return collect(args.work.resolve())


if __name__ == "__main__":
    sys.exit(main())

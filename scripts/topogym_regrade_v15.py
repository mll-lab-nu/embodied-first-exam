#!/usr/bin/env python3
"""Offline tooling-v15 re-grade of ONE finished TopoGym trial from what it saved, into a separate output dir.

Tooling v15 (2026-10-03) changes the grading replays of the GPU families (rcb_topogym.py "grading replays": the final
targets held for up to 2 s after the last row, the replay tolerances) and, for every family, the physical-validity policy
(rcb_topogym.py "physical-validity policy": v14's R1 no longer ends an episode, the protective stop does, a breakdown is an
infrastructure error unless forced, a success with a deep task contact is held for review). A v14 trial whose live
episode was not ended by R1 can be graded again from its saved trajectory with the v15 task dir's own graders:
  * privileged: the task's tests/grade.py replays the agent's /app/output/trajectory.npz twice, as its verifier does;
  * standard: the live verdict stays (the trial's final.json: live success, live rows, crash-recovery fields); the task's
    environment/sim/replay.py replays the live rows once (the collect hook's grading replay, with the video), the merge of
    its environment/sim/finalize.sh writes final.json, and its tests/grade.py grades that.
blanket_flatten trials are refused: v15 also changes its live criterion (coverage 0.90 -> 0.95), so they are rerun. So is a
standard trial whose live episode R1 ended (final.json reason task_contact_forced / held_contact_forced: its agent never
got to continue); a v14 final.json has no live review record, so only its replay's counts. The trial dir is only read:
mount it read-only.

Run it in a fresh container of the task's image on one GPU (the trial's frozen instance must be the task's: the
trajectory's instance_sha is checked), e.g. on lab:
  privileged:
    docker run --rm --network none --gpus device=<g> -e NVIDIA_DRIVER_CAPABILITIES=all -e PYTHONDONTWRITEBYTECODE=1 \\
      -v <trial>/verifier:/trial:ro -v <trial>/artifacts/app/output:/app/output:ro -v <v15 task dir>:/task:ro \\
      -v <out>:/out -v scripts/topogym_regrade_v15.py:/regrade.py:ro -e PYTHONPATH=/task/tests:/opt/topogym \\
      ghcr.io/luigivamper/rcb-topogym:0.2.12-cu128 python /regrade.py
  standard (the task's graders read /data and write /logs/verifier):
    docker run ... -v <trial>/verifier:/trial:ro -v <v15 task dir>:/task:ro -v <out>:/out -v <out>/data:/data \\
      -v <out>/verifier:/logs/verifier -v scripts/topogym_regrade_v15.py:/regrade.py:ro \\
      -e PYTHONPATH=/task/environment/sim:/opt/topogym ghcr.io/luigivamper/rcb-topogym:0.2.12-cu128 python /regrade.py
It writes <out>/regrade.json (the trial, its v14 reward, the v15 reward, every grading replay's record) next to the
graders' own output (<out>/verifier: reward.json, verdict.json or final.json, replay.mp4, ...) and prints a summary line.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np

# what the standard service's dump() writes into episode.json (environment/sim/server.py); everything else in a trial's
# final.json was added by its collect hook's replay and merge, which this re-grade redoes
LIVE_KEYS = ("success", "steps", "calls", "control_steps", "physics_steps", "sim_time_s", "elapsed_s", "reason", "task",
             "protocol", "n_actions", "live_rows", "live_sha", "instability", "sim_startups", "resumes",
             "resume_state_mismatch", "resume_max_tcp_dev_m", "resume_max_joint_dev")
INFRA_REASONS = ("error", "simulator_instability")      # server.py: the live ends that are infrastructure failures


def load(path):
    return json.loads(Path(path).read_text()) if Path(path).is_file() else None


def same_instance(traj, instance):
    with np.load(traj, allow_pickle=False) as d:
        got = str(d["instance_sha"]) if "instance_sha" in d else None
    want = json.loads(Path(instance).read_text())["state_sha"]
    if got != want:
        sys.exit(f"the trajectory was recorded on instance {got}, the task's frozen instance is {want}: not re-gradable here")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", default="/task", help="the v15 task dir (-privileged or -standard), read-only")
    ap.add_argument("--trial", default="/trial", help="the trial's verifier/ dir, read-only")
    ap.add_argument("--out", default="/out")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    task, trial, out = Path(a.task), Path(a.trial), Path(a.out)
    toml = tomllib.loads((task / "task.toml").read_text())
    meta, name = toml["metadata"], toml["task"]["name"].split("/")[-1]   # the mount point's name says nothing
    family, standard = meta["family"], (task / "environment/sim").is_dir()
    if meta.get("tooling_version") != "15":
        sys.exit(f"{task}: tooling v{meta.get('tooling_version')}, not v15")
    if family == "blanket_flatten":
        sys.exit("blanket_flatten: v15 changes the live criterion too (coverage 0.95), so its trials are rerun, not re-graded")
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RCB_SESSION_LOG="", PYTHONDONTWRITEBYTECODE="1")
    original = load(trial / "reward.json")
    if not standard:
        traj = Path("/app/output/trajectory.npz")
        if not traj.is_file():
            sys.exit("no /app/output/trajectory.npz: nothing to re-grade (the v14 verdict stands: missing_trajectory)")
        same_instance(traj, task / "tests/instance.json")
        log = out / "verifier"
        log.mkdir(exist_ok=True)
        cmd = [sys.executable, str(task / "tests/grade.py"), "--family", family, "--instance", str(task / "tests/instance.json"),
               "--traj", str(traj), "--repeat", "2"] + (["--no-video"] if a.no_video else [])
        with open(log / "grade.log", "w") as err:
            subprocess.run(cmd, env=dict(env, RCB_VERIFIER_LOG_DIR=str(log)), stdout=subprocess.DEVNULL, stderr=err, check=False)
        reward, verdict = load(log / "reward.json"), load(log / "verdict.json") or {}
        grading = [r.get("grading") for r in (verdict.get("evidence") or {}).get("replays", [])]
    else:
        final = load(trial / "final.json")
        if final is None or not (trial / "trajectory.npz").is_file():
            sys.exit("the trial saved no final.json / trajectory.npz: nothing to re-grade")
        if final.get("gave_up") or final.get("instance_mismatch"):
            sys.exit("the trial's verdict did not come from a replay (gave_up / instance_mismatch): it stands")
        if str(final.get("reason") or "").startswith(("task_contact_forced", "held_contact_forced")):
            sys.exit("v14's R1 ended the live episode (its agent never got to continue): rerun it, it cannot be re-graded")
        data, log = Path("/data"), Path("/logs/verifier")
        (out / "data").mkdir(exist_ok=True)
        if not (data.is_dir() and log.is_dir() and os.path.samefile(data, out / "data")):
            sys.exit("mount <out>/data at /data and <out>/verifier at /logs/verifier (the standard graders' paths)")
        same_instance(trial / "trajectory.npz", task / "environment/sim/instance.json")
        for f in ("trajectory.npz", "episode.jsonl"):
            if (trial / f).is_file():
                shutil.copy(trial / f, data / f)
        live = {k: final[k] for k in LIVE_KEYS if k in final}
        live.update(infra_error=int(final.get("reason") in INFRA_REASONS),
                    simulator_instability=final.get("reason") == "simulator_instability")
        (data / "episode.json").write_text(json.dumps(live))
        sim = task / "environment/sim"
        cmd = [sys.executable, str(sim / "replay.py"), "--data", str(data), "--task", family, "--instance",
               str(sim / "instance.json")] + ([] if a.no_video else ["--video", str(data / "replay.mp4")])
        with open(data / "replay.json", "w") as stdout, open(data / "replay.log", "w") as err:
            subprocess.run(cmd, env=env, stdout=stdout, stderr=err, check=False)
        merge = (sim / "finalize.sh").read_text().split("python - <<'PY'\n")[-1].split("\nPY")[0]
        subprocess.run([sys.executable, "-c", merge], env=dict(env, RCB_DATA=str(data)), stdout=subprocess.DEVNULL, check=True)
        subprocess.run([sys.executable, str(task / "tests/grade.py")], env=env, stdout=subprocess.DEVNULL, check=True)
        reward = load(log / "reward.json")
        grading = [(load(data / "final.json") or {}).get("replay_grading")]
    record = dict(script="scripts/topogym_regrade_v15.py", tooling_version="15", family=family,
                  mode="standard" if standard else "privileged", task=name, trial=str(trial),
                  original_reward=original, reward=reward, grading=grading)
    (out / "regrade.json").write_text(json.dumps(record, indent=1))
    keys = ("success", "success_pending_review", "live_success", "replay_success", "all_success", "replay_hold_steps",
            "replay_tolerance_needed", "grader_error", "infra_error")
    print(json.dumps(dict(task=name, v14={k: (original or {}).get(k) for k in keys if k in (original or {})},
                          v15={k: (reward or {}).get(k) for k in keys if k in (reward or {})})), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

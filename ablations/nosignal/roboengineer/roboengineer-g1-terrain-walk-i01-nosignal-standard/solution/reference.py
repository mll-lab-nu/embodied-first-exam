"""G1 reference (solution/): train the public blind-terrain curriculum from scratch on the agent's GPU, deploy three
times, seal the last completed round. Its tools are the agent's: control_public.g1_training (copied, with the 1024
environment cap lifted to 4096) and the public client; its PPO settings (below) are its own choice. No evaluator
code, no hidden cases, no warm start.

A short probe segment measures the iteration time on this GPU; three training segments follow (50 / 30 / 20 % of
the time left minus G1_REF_RESERVE_S, read from /run/rcb-limits/usage.json, else the task's 14400 s), each resumed
from the previous checkpoint. Each segment's exported actor is deployed (one deployment at a time, in the background)
while the next segment trains; a failed deployment is logged and the run goes on. A segment still training
G1_REF_RESERVE_S / 2 before the cutoff is stopped (a GPU faster than the probe's estimate); if no segment finished,
the probe's actor is deployed.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

OUT = Path(os.environ.get("G1_REF_OUT", "/app/output/reference"))
ENVS = int(os.environ.get("G1_REF_ENVS", "4096"))
PROBE = int(os.environ.get("G1_REF_PROBE_ITERATIONS", "200"))
MIN_SEGMENT = int(os.environ.get("G1_REF_MIN_SEGMENT_ITERATIONS", "50"))
RESERVE = float(os.environ.get("G1_REF_RESERVE_S", "1800"))
SEGMENT_OVERHEAD_S = 120.0   # environment build + Warp kernel load per segment process (measured ~85 s on an L40S)
MAX_ITERATIONS = int(os.environ.get("G1_REF_MAX_ITERATIONS", "20000"))
UPSTREAM = "/opt/control-assets/unitree_rl_mjlab"
# From-scratch PPO settings: rsl-rl's usual learning rate and entropy for a policy trained from scratch (the trainer's
# own defaults, 1e-4 / 1e-3, are for fine-tuning a warm-started actor) with moderate friction / encoder-bias /
# centre-of-mass randomization; the same numbers as the operator's training baseline in the evaluator's contract.py.
SETTINGS = {
    "learning_rate": 0.001,
    "entropy_coef": 0.01,
    "friction_low": 0.3,
    "friction_high": 1.6,
    "encoder_bias": 0.015,
    "com_offset": 0.05,
    "action_rate_weight": -0.05,
}
START = time.time()


def time_left():
    try:
        return float(json.loads(Path("/run/rcb-limits/usage.json").read_text())["time_left_s"])
    except (OSError, ValueError, KeyError, TypeError):
        return 14400.0 - (time.time() - START)


def trainer():
    """The public trainer, with the environment cap raised (4096 environments need ~16.5 GB of GPU memory)."""
    package = OUT / "trainer" / "control_public"
    package.mkdir(parents=True, exist_ok=True)
    for p in Path("/app/control_public").glob("*.py"):
        shutil.copy(p, package / p.name)
    source = (package / "g1_training.py").read_text()
    assert "not 1 <= num_envs <= 1024" in source
    (package / "g1_training.py").write_text(source.replace("not 1 <= num_envs <= 1024", "not 1 <= num_envs <= 4096"))


def train(folder, *, seed, iterations, checkpoint):
    """One training segment in its own process (the trainer sets process-wide torch state once)."""
    args = dict(upstream=UPSTREAM, out=str(folder), seed=seed, gpu=0, iterations=iterations, num_envs=ENVS,
                checkpoint=checkpoint, settings=SETTINGS)
    code = ("import json, sys; from control_public.g1_training import train; "
            "a = json.loads(sys.argv[1]); out = a.pop('upstream'), a.pop('out'); train(*out, **a)")
    with open(OUT / f"{Path(folder).name}.log", "w") as log:
        # cwd: `python -c` puts the working directory first on sys.path (not /app, which holds the capped trainer)
        # one Warp kernel cache for all segments (the trainer's default is per output folder: a recompile each time)
        env = {**os.environ, "PYTHONPATH": f"{OUT / 'trainer'}:/app", "WARP_CACHE_PATH": str(OUT / "warp-cache")}
        subprocess.run([sys.executable, "-c", code, json.dumps(args)], check=True, stdout=log, stderr=subprocess.STDOUT,
                       cwd=OUT / "trainer", env=env, timeout=max(60.0, time_left() - RESERVE / 2))
    return json.loads((Path(folder) / "training.json").read_text())


def latest_checkpoint(folder):
    return max(Path(folder).glob("model_*.pt"), key=lambda p: int(p.stem.split("_")[1]))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trainer()
    sys.path.insert(0, "/app")
    from control_public.client import Client, artifact

    client = Client(out=str(OUT / "trace"))
    client.describe()
    rounds, log, lock = [], [], threading.Lock()
    deployer = ThreadPoolExecutor(1)   # one deployment at a time: the service runs one round at once

    def save(entry=None):
        with lock:   # the deploy thread logs too
            if entry is not None:
                log.append(entry)
            (OUT / "reference.json").write_text(json.dumps(log, indent=2))

    def deploy(policy, note):
        try:
            rounds.append(client.deploy(artifact(policy), note)["round_id"])
        except Exception:
            save({"deploy_failed": str(policy), "error": traceback.format_exc(limit=3)})

    def segment(name, iterations, checkpoint, seed):
        folder = OUT / name
        began = time.time()
        record = train(folder, seed=seed, iterations=iterations, checkpoint=checkpoint)
        save({"segment": name, "iterations": iterations, "elapsed_s": round(time.time() - began, 1),
              "steps": record["steps"], "time_left_s": time_left()})
        return folder, max(0.05, time.time() - began - SEGMENT_OVERHEAD_S) / iterations

    folder, per_iteration = segment("probe", PROBE, None, 0)
    probe, checkpoint, trained, submitted = folder, str(latest_checkpoint(folder)), PROBE, 0
    budget = max(0.0, time_left() - RESERVE - 3 * SEGMENT_OVERHEAD_S)
    plan = [int(budget * share / max(per_iteration, 0.05)) for share in (0.5, 0.3, 0.2)]
    for i, iterations in enumerate(plan):
        if i:   # re-plan from what is left (the GPU's speed can change while other work shares it)
            left = max(0.0, time_left() - RESERVE - (3 - i) * SEGMENT_OVERHEAD_S)
            iterations = min(iterations, int(left / max(per_iteration, 0.05)))
        iterations = min(MAX_ITERATIONS, iterations)
        if iterations < MIN_SEGMENT:
            save({"segment": f"segment-{i}", "skipped": f"{iterations} iterations left", "time_left_s": time_left()})
            break
        try:
            folder, per_iteration = segment(f"segment-{i}", iterations, checkpoint, i + 1)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            save({"segment": f"segment-{i}", "failed": type(error).__name__, "time_left_s": time_left()})
            break
        checkpoint, trained = str(latest_checkpoint(folder)), trained + iterations
        note = (f"Reference segment {i}: {trained} PPO iterations x {ENVS} environments from scratch; the feedback is "
                "not used, the next segment continues training.")
        deployer.submit(deploy, folder / "policy.npz", note)
        submitted += 1
    if not submitted:
        deployer.submit(deploy, probe / "policy.npz", f"Reference probe: {PROBE} PPO iterations x {ENVS} environments.")
    deployer.shutdown(wait=True)
    if not rounds:
        save({"rounds": [], "time_left_s": time_left()})
        raise SystemExit("no completed deployment")
    last = max(rounds)
    client.seal(last, "Reference: the most trained actor that completed a deployment.")
    save({"rounds": sorted(rounds), "sealed": last, "time_left_s": time_left()})


if __name__ == "__main__":
    main()

"""Import and verify the frozen instances and reference trajectories (trusted authoring step; run it through
import_references.sh, inside the benchmark image).

The instances and references were authored in PR #4 (scripts/coverage/author_demo.py there): each scene is the initial
state of an official demonstration episode, frozen with the full MuJoCo state, the model arrays the kitchen's reset
rewrites, the env's Python task state and every RNG; the reference is that demonstration's native controller actions,
executed from the frozen scene by the robot's own controller. This step copies the instance byte for byte and the
reference's actions, and re-verifies both with this benchmark's tooling (shared/casa_tool.py) and grading:
1. not solved at the start; reset() is bit-exact;
2. the reference's final state is a success (graded on the final state; if only an earlier state succeeded, the
   reference is cut at its first success and checked again);
3. two replays in fresh processes end in the live run's state hash, with success;
4. informational: whether the success survives 10 more "hold still" steps (the README says so when it does not).

Writes frozen/<slug>/instance.npz, frozen/<slug>/oracle.npz (key `actions`, (T, dim) float64) and frozen/report.json.

    bash scripts/<benchmark>/import_references.sh <PR #4 checkout> [env ...]
"""

import concurrent.futures
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import casa_tool  # noqa: E402
from envs import SOURCES, slug  # noqa: E402

OUT = HERE / "frozen"
SRC = Path("/src")  # the PR #4 checkout, mounted read-only
BENCH = HERE.name
HOLD_STEPS = 10


def replay_child(instance: str, oracle: str) -> None:
    """Child process: one fresh replay; prints its result as JSON."""
    r = casa_tool.Session(instance).replay(np.load(oracle)["actions"])
    print(json.dumps(r))


def provenance(task_dir: Path) -> dict:
    toml = (task_dir / "task.toml").read_text()
    orig = toml.split('derived_from = "robot-coding-bench/', 1)[1].split('"', 1)[0]
    recipe = SRC / "archive/task_versions/pre-unified-20260929/tasks" / orig / "recipe.json"
    if not recipe.exists():
        recipe = SRC / "staging/coverage" / BENCH / orig / "recipe.json"
    if not recipe.exists():
        return {"source_task": orig}
    r = json.loads(recipe.read_text())
    demo = r.get("demonstration") or {}
    return {
        "source_task": orig,
        "upstream_commit": r.get("upstream_commit"),
        "environment_source": (r.get("source") or {}).get("url"),
        "demonstration": {k: demo.get(k) for k in ("episode", "demo", "n_actions")},
        "demonstration_source": (demo.get("source") or {}).get("url"),
        "demonstration_path": (demo.get("source") or {}).get("human_path") or (demo.get("source") or {}).get("path"),
        "reference_method": r.get("reference_method"),
        "controller_mode": r.get("controller_mode"),
    }


def run_live(instance: Path, actions: np.ndarray) -> tuple[dict, casa_tool.Session]:
    s = casa_tool.Session(instance)
    first = None
    for i, a in enumerate(actions):
        if s.step(a)["success"] and first is None:
            first = i
    return {"first_success": first, "success": s.success, "state_sha": s.state_sha()}, s


def verify(env: str) -> dict:
    task_dir = SRC / "unlimited_tasks" / BENCH / SOURCES[env]
    d = OUT / slug(env)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(task_dir / "environment/instance.npz", d / "instance.npz")
    actions = np.asarray(np.load(task_dir / "solution/oracle.npz")["actions"], np.float64)
    rec = {"env": env, "slug": slug(env), **provenance(task_dir)}
    s = casa_tool.Session(d / "instance.npz")
    sha0 = s.state_sha()
    rec.update(
        instance_sha=s.instance_sha,
        instruction=s.inst["text"],
        action_dim=s.action_dim,
        arm_kind=s.action_spec["channels"][0]["kind"],
        initial_success=s.initial_success,
        cameras=list(s.camera_views),
    )
    s.step(s.hold_targets())
    s.reset()
    rec["reset_exact"] = s.state_sha() == sha0
    s.close()
    live, s = run_live(d / "instance.npz", actions)
    rec.update(reference_actions=len(actions), first_success=live["first_success"], truncated=False)
    if not live["success"] and live["first_success"] is not None:
        s.close()
        actions = actions[: live["first_success"] + 1]
        live, s = run_live(d / "instance.npz", actions)
        rec["truncated"] = True
    rec.update(oracle_success=live["success"], n_actions=len(actions), live_state_sha=live["state_sha"])
    for _ in range(HOLD_STEPS):
        s.step(s.hold_targets())
    rec["success_after_hold"] = s.success
    s.close()
    if not live["success"]:
        return rec
    np.savez(d / "oracle.npz", actions=actions)
    replays = []
    for _ in range(2):
        p = subprocess.run(
            [sys.executable, __file__, "--replay", str(d / "instance.npz"), str(d / "oracle.npz")],
            check=True,
            capture_output=True,
            text=True,
        )
        replays.append(json.loads(p.stdout.strip().splitlines()[-1]))
    rec["replay_state_sha"] = [r["state_sha"] for r in replays]
    rec["deterministic"] = all(r["state_sha"] == rec["live_state_sha"] for r in replays)
    rec["replay_success"] = all(r["success"] for r in replays)
    return rec


def ok(rec: dict) -> bool:
    keys = ("reset_exact", "oracle_success", "deterministic", "replay_success")
    return all(rec.get(k) for k in keys) and not rec.get("initial_success")


def main(names: list[str], workers: int) -> None:
    report_path = OUT / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    with concurrent.futures.ProcessPoolExecutor(workers) as ex:
        for env, rec in zip(names, ex.map(verify, names), strict=True):
            report[slug(env)] = rec
            print(
                f"{env:28s} n={rec.get('n_actions')} truncated={rec.get('truncated')} ok={ok(rec)} "
                f"hold={rec.get('success_after_hold')}",
                flush=True,
            )
    report_path.write_text(json.dumps(dict(sorted(report.items())), indent=1) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--replay":
        replay_child(sys.argv[2], sys.argv[3])
    else:
        args = sys.argv[1:]
        workers = 6
        if args[:1] == ["--workers"]:
            workers, args = int(args[1]), args[2:]
        main(args or sorted(SOURCES), workers)

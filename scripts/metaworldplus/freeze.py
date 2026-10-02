"""Freeze the MetaWorld+ instances and record the oracles (trusted authoring step; run it through freeze.sh).

Per environment (envs.py):
1. freeze the instance: Meta-World's reset randomization drawn from the instance seed, with the full MuJoCo state, the
   model arrays reset rewrites, the env's caches and the RNG states (shared/mw_tool.py create_instance);
2. check it: not solved at the start, and reset() is bit-exact;
3. record the oracle: Meta-World's scripted policy for the environment, run until its first success (<= 500 actions);
4. verify it: two replays in fresh processes end in the live episode's final state, and that state is a success;
   also note whether the success survives 10 more "hold" steps (informational: the README says so when it does not).

Writes frozen/<env>/instance.npz, frozen/<env>/oracle.npz and frozen/report.json (read by generate.py).

    bash scripts/metaworldplus/freeze.sh [env ...]
"""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import mw_tool  # noqa: E402
from envs import GOALS, SEEDS  # noqa: E402

OUT = HERE / "frozen"
HOLD_STEPS = 10


def policy_for(env: str):
    stem = "peg_insertion_side" if env == "peg-insert-side" else env.replace("-", "_")
    mod = importlib.import_module(f"metaworld.policies.sawyer_{stem}_v3_policy")
    return getattr(mod, "Sawyer" + "".join(p.capitalize() for p in stem.split("_")) + "V3Policy")()


def replay_child(instance: str, oracle: str) -> None:
    """Child process: one fresh replay; prints its result as JSON."""
    r = mw_tool.Session(instance).replay(np.load(oracle)["actions"])
    print(json.dumps(r))


def freeze(env: str) -> dict:
    d = OUT / env
    d.mkdir(parents=True, exist_ok=True)
    seed = SEEDS.get(env, 0)
    np.savez_compressed(d / "instance.npz", **mw_tool.create_instance(f"{env}-v3", seed, GOALS[env]))
    s = mw_tool.Session(d / "instance.npz")
    rec = {"env": env, "seed": seed, "instance_sha": s.instance_sha, "initial_success": s.check()["success"]}
    sha0 = s.state_sha()
    s.step(np.zeros(4))
    s.reset()
    rec["reset_exact"] = s.state_sha() == sha0
    rec["mocap_low"] = np.round(s.env.mocap_low, 4).tolist()
    rec["mocap_high"] = np.round(s.env.mocap_high, 4).tolist()
    policy = policy_for(env)
    for _ in range(mw_tool.MAX_STEPS):
        s.step(np.clip(policy.get_action(s.obs), -1.0, 1.0))
        if s.check()["success"]:
            break
    actions = np.asarray(s.actions, dtype=np.float64)
    live = s.check()
    rec.update(oracle_success=live["success"], n_actions=len(actions), live_state_sha=s.state_sha())
    for _ in range(HOLD_STEPS):
        s.step(s.hold_targets())
    rec["success_after_hold"] = s.check()["success"]
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


def main(envs: list[str]) -> None:
    report_path = OUT / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    for env in envs:
        rec = freeze(env)
        report[env] = rec
        ok = rec["oracle_success"] and rec.get("deterministic") and rec.get("replay_success")
        print(f"{env:28s} seed={rec['seed']} n={rec['n_actions']:3d} ok={bool(ok)} hold={rec['success_after_hold']}")
    OUT.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(dict(sorted(report.items())), indent=1) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--replay":
        replay_child(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1:] or sorted(GOALS))

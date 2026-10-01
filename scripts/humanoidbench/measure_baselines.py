#!/usr/bin/env python3
"""Two trivial-policy floors for every HumanoidBench family -- the evidence behind which families
subset.toml keeps.

This deliberately covers all 32 upstream families, not just the ones in subset.toml: the whole point is
to decide which families deserve a slot, so it has to see the ones currently outside it. gen_tasks.py
measure is the per-task counterpart that records the same numbers against a FROZEN instance.

    nop   all-zero action. HumanoidBench is position-controlled and unnormalize_action() maps the action
          linearly onto each actuator's ctrlrange, so zero is NOT "hold still" -- it commands every joint
          to the MIDPOINT of its range, which folds H1 into a crouch.
    hold  the action whose ctrl equals the scene's own starting joint angles, i.e. "stand to attention
          and write no controller at all".

`hold` is the number that decides whether a task is too easy: it is what any competent agent collects
for free before writing a line of code. The two disagree a lot and in both directions -- sit_simple
scores 637 on nop and 468 on hold, spoon scores 7 on nop and 375 on hold -- so a family is judged on
max(nop, hold), and "how many steps it survived" is read alongside (`stand` holds only 8.4% of its bar
AND falls at step 96, which is a very different task from one that coasts to 1000).

The image has no reward function (images/humanoidbench/scrub_oracles.py), so this restores it from
rewards.json first -- the same table and the same code path the verifier uses, so the floors reported here
are the floors the verifier would produce.

    docker run --rm -v "$PWD:/out" -w /out ghcr.io/embodied-agent-interface-v2-internal/eai-humanoidbench:$(cat ../../images/humanoidbench/VERSION) \
        python /out/measure_baselines.py --out /out/baselines.json
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import numpy as np

# Every upstream family, in the paper's own order (loco then manip).
FAMILIES = [
    "stand", "walk", "run", "crawl", "sit_simple", "sit_hard", "hurdle", "stair", "slide", "pole",
    "maze", "balance_simple", "balance_hard", "reach", "door", "spoon", "window", "push", "room",
    "powerlift", "highbar_simple", "highbar_hard", "basketball", "package", "bookshelf_simple",
    "bookshelf_hard", "cabinet", "truck", "kitchen", "cube", "insert_small", "insert_normal",
]
# Cheapest robot first: 19 actuators if the family has an h1 scene, else the 61-actuator hands.
# h1strong exists for exactly one family (highbar_hard).
ROBOTS = ["h1", "h1hand", "h1strong"]


def _rollout(env, action, max_steps: int) -> tuple[float, int]:
    ret, n = 0.0, 0
    for _ in range(max_steps):
        _, r, term, trunc, _ = env.step(action)
        ret += float(r)
        n += 1
        if term or trunc:
            break
    return ret, n


def hold_action(u) -> np.ndarray:
    """The action that commands every actuator to the position it already has.

    actuator_trnid[:, 0] is what each actuator drives: a joint (read its qpos slot) or, for the Shadow hand's
    coupled finger actuators, a tendon (read its length, the summed angle of the two joints it moves).
    The inverse of unnormalize_action() is 2*(q - low)/(high - low) - 1.
    """
    import mujoco
    m, d = u.model, u.data
    lo = np.asarray(u.action_low, dtype=np.float64)
    hi = np.asarray(u.action_high, dtype=np.float64)
    q0 = np.array([d.ten_length[i] if t == mujoco.mjtTrn.mjTRN_TENDON else d.qpos[m.jnt_qposadr[i]]
                   for t, i in zip(m.actuator_trntype, m.actuator_trnid[:, 0])])
    return np.clip(2.0 * (q0 - lo) / np.maximum(hi - lo, 1e-9) - 1.0, -1.0, 1.0)


def measure(fam: str, seed: int = 0) -> dict:
    import gymnasium as gym
    import humanoid_bench  # noqa: F401  (registers every robot x task env id)

    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here / "shared"))
    from rcb_rewards import restore
    restore(json.loads((here / "rewards.json").read_text())[fam])

    for robot in ROBOTS:
        eid = f"{robot}-{fam}-v0"
        try:
            np.random.seed(seed)          # task-level randomisation still rides the legacy global
            env = gym.make(eid, render_mode=None)
        except Exception:
            continue                      # no scene XML for this robot; try the next one
        try:
            u = env.unwrapped
            np.random.seed(seed)
            env.reset(seed=seed)
            hold = hold_action(u)
            steps, bar = int(env.spec.max_episode_steps), float(u.task.success_bar)

            np.random.seed(seed); env.reset(seed=seed)
            nop_r, nop_n = _rollout(env, np.zeros(u.model.nu), steps)
            np.random.seed(seed); env.reset(seed=seed)
            hold_r, hold_n = _rollout(env, hold, steps)

            return {"env_id": eid, "robot": robot, "nu": int(u.model.nu), "bar": bar,
                    "max_steps": steps,
                    "nop": round(nop_r, 2), "nop_steps": nop_n, "nop_pct": round(100 * nop_r / bar, 1),
                    "hold": round(hold_r, 2), "hold_steps": hold_n, "hold_pct": round(100 * hold_r / bar, 1)}
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return {"env_id": eid, "error": f"{type(e).__name__}: {e}"}
        finally:
            env.close()
    return {"error": f"no scene XML for {fam} on any of {ROBOTS}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="baselines.json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("families", nargs="*", default=None, help="default: all 32")
    a = ap.parse_args()

    out = {}
    for fam in (a.families or FAMILIES):
        out[fam] = measure(fam, a.seed)
        print(json.dumps({fam: out[fam]}), flush=True)

    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)

    rows = sorted(((k, v) for k, v in out.items() if "hold_pct" in v), key=lambda kv: -kv[1]["hold_pct"])
    print(f"\n{'task':18}{'robot':10}{'nu':>3}{'bar':>7}{'nop':>10}{'nop%':>7}{'hold':>10}{'hold%':>7}{'alive':>7}")
    for k, v in rows:
        print(f"{k:18}{v['robot']:10}{v['nu']:3}{v['bar']:7.0f}{v['nop']:10.2f}{v['nop_pct']:7.1f}"
              f"{v['hold']:10.2f}{v['hold_pct']:7.1f}{v['hold_steps']:7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

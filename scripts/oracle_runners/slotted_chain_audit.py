#!/usr/bin/env python3
"""Independent audit of a rigid-chain Slotted oracle run (run_slotted_chain_oracle.py): its trajectory.npz in a
fresh Session.

replay: Session.replay(actions, physics_steps, grading=True), the verifier's own replay; prints its status.
scan:   the same rows stepped one by one, checking every control step with code written apart from the oracle's:
        - the bead1 rule: the lifted ring may not pass the post with bead1 in its hole (post axis crossing the ring's
          plane inside the hole below the post top while bead1's centre is inside the hole near that plane);
        - no part and no chain point more than 0.1 m below the table top;
        - the arm joint targets change at most 0.04 rad per control step (the standard service's limit);
        and the end status (success, state hash) against the run's own report.json.
--perturb SEED (scan only): a run recorded from a perturbed reset, which its actions do not hold: after the reset the
puzzle's degrees of freedom get np.random.default_rng(SEED).normal(0, V) velocities (--perturb-v V, default 0.1) and
the targets are held PERTURB_SETTLE_STEPS before the rows are stepped.

    python scripts/oracle_runners/slotted_chain_audit.py replay runs/slotted_chain/hard --out runs/slotted_chain/hard
    python scripts/oracle_runners/slotted_chain_audit.py scan runs/slotted_chain/hard --out runs/slotted_chain/hard
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
JOINT_STEP_LIMIT_RAD = .04
FALL_M = .1
LIFTED_M = .005
PERTURB_SETTLE_STEPS = 80


def bead1_passes_with_post(scene, lay):
    c, rot = scene.poses["ring"]
    n = rot.apply([0., 0., 1.])
    if abs(n[2]) < .2 or c[2] < lay.base_height_m+lay.ring_tube_radius_m+LIFTED_M:
        return False
    z = c[2]-(n[0]*(0.-c[0])+n[1]*(0.-c[1]))/n[2]          # the post axis (x = y = 0) meets the ring's plane
    post_in = lay.base_height_m < z < lay.base_height_m+lay.post_height_m and \
        np.linalg.norm(np.r_[0., 0., z]-c) < lay.ring_inner_radius
    d = scene.pos("bead_left")-c
    h = float(d @ n)
    bead_in = abs(h) < lay.bead_radius_m+lay.ring_tube_radius_m and np.linalg.norm(d-h*n) < lay.ring_inner_radius
    return bool(post_in and bead_in)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=("replay", "scan"))
    p.add_argument("run", type=Path, help="the E run's directory (trajectory.npz, report.json)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--perturb", type=int, metavar="SEED", help="scan only: the run's perturbed start (see above)")
    p.add_argument("--perturb-v", type=float, default=.1, metavar="V")
    a = p.parse_args()
    from topogym.planning.slotted_post_ring.chain.session import build_session, scene
    if a.perturb is not None and a.mode == "replay":
        p.error("--perturb: the verifier's replay starts from the reset; use scan")
    t = np.load(a.run/"trajectory.npz", allow_pickle=True)
    actions, ticks = t["actions"], t["physics_steps_per_action"] if "physics_steps_per_action" in t.files else None
    layout = list(t["action_layout"])
    joints = [i for i, name in enumerate(layout) if "gripper" not in name]
    steps = np.abs(np.diff(actions[:, joints], axis=0))
    out = dict(run=str(a.run), rows=int(len(actions)), action_layout=layout,
               max_joint_step_rad=round(float(steps.max()), 4), rows_over_limit=int((steps > JOINT_STEP_LIMIT_RAD+1e-6).any(1).sum()))
    original = json.loads((a.run/"report.json").read_text()).get("status", {})
    variation = str(t["variation_id"]) if "variation_id" in t.files else "slotted_post_ring_hard_chain"
    session = build_session(variation)
    if a.mode == "replay":
        st = session.replay(actions, physics_steps=ticks, grading=True)
    else:
        session.reset()
        lay = session.env._task.layout
        if a.perturb is not None:
            from topogym.planning.slotted_post_ring.chain.motion import Hands
            entity = session.env._world.entities["slotted_chain"]
            v = entity.get_dofs_velocity()
            shape = np.asarray(v.cpu() if hasattr(v, "cpu") else v, float).shape
            entity.set_dofs_velocity(np.random.default_rng(a.perturb).normal(0., a.perturb_v, shape))
            Hands(session, []).hold(PERTURB_SETTLE_STEPS)
            out.update(perturb_seed=a.perturb, perturb_v=a.perturb_v)
        violations, lowest = [], (np.inf, -1, "")
        for i, row in enumerate(np.asarray(actions, np.float32)):
            ended = session.step(row, _physics_steps=None if ticks is None else int(ticks[i]))
            s = scene(session)
            if bead1_passes_with_post(s, lay):
                violations.append(i)
            z = min([(float(s.points[:, 2].min()), "chain")]+[(float(s.pos(k)[2]), k) for k in s.poses])
            if z[0] < lowest[0]:
                lowest = (z[0], i, z[1])
            if ended:
                break
        st = session.status()
        out.update(bead1_rule_violations=len(violations), bead1_rule_first=violations[:10],
                   lowest_z_m=round(lowest[0], 4), lowest_step=lowest[1], lowest_part=lowest[2],
                   fell=bool(lowest[0] < -FALL_M))
    out.update(variation_id=variation, ring_major_radius_m=float(session.env._task.layout.ring_major_radius_m),
               success=bool(st.get("success")), episode_end=st.get("episode_end"), state_sha=st.get("state_sha"),
               original_success=original.get("success"), original_state_sha=original.get("state_sha"),
               same_end=st.get("state_sha") == original.get("state_sha"), grading=st.get("grading"))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/f"audit_{a.mode}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "action_layout"}, default=str))


if __name__ == "__main__":
    main()

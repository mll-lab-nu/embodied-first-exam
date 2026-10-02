#!/usr/bin/env python3
"""Check GenesisWorld.read_state's batched rigid readback (_RigidReadout) against the per-entity / per-link getters it
replaced, on the GPU, at every physics tick of a few control steps with motion.

    python scripts/check_read_state_batch.py <family> <instance.json> [--steps 6] [--out report.json]

Run inside the TopoGym image with the task tooling importable (rcb_topogym.Session) and this repository's topogym on
PYTHONPATH. Pass: bodies and articulations bit-identical at every tick (same keys in the same order, same dtypes, shapes
and bytes). Also reports the time of both readbacks and of one control step. Exit 1 on any difference."""
import argparse
import json
import sys
import time

import numpy as np

from rcb_topogym import Session
from topogym.utils.arrays import to_numpy


def legacy(world):
    """The rigid part of GenesisWorld.read_state before the batched readout (dev/jianwen c4d952c86), with the IPC
    coupler's velocity override."""
    bodies, articulations = {}, {}
    for name, entity in world.entities.items():
        if hasattr(entity, "material_coordinates") or hasattr(entity, "get_particles_pos") or not hasattr(entity, "get_pos"):
            continue
        bodies[name] = dict(position_m=to_numpy(entity.get_pos()).reshape(-1, 3)[0],
                            quaternion_wxyz=to_numpy(entity.get_quat()).reshape(-1, 4)[0],
                            linear_velocity_m_s=to_numpy(entity.get_vel()).reshape(-1, 3)[0],
                            angular_velocity_rad_s=to_numpy(entity.get_ang()).reshape(-1, 3)[0],
                            link_indices=tuple(link.idx for link in entity.links))
        qpos = to_numpy(entity.get_qpos()).reshape(-1)
        velocity = to_numpy(entity.get_dofs_velocity()).reshape(-1)
        articulations[name] = dict(
            joints={joint.name: dict(position=qpos[list(joint.qs_idx_local)].copy(),
                    velocity=velocity[list(joint.dofs_idx_local)].copy()) for joint in entity.joints},
            links={link.name: dict(position_m=to_numpy(link.get_pos()).reshape(-1, 3)[0],
                    quaternion_wxyz=to_numpy(link.get_quat()).reshape(-1, 4)[0],
                    linear_velocity_m_s=to_numpy(link.get_vel()).reshape(-1, 3)[0],
                    angular_velocity_rad_s=to_numpy(link.get_ang()).reshape(-1, 3)[0]) for link in entity.links})
    coupler = world.scene.sim.coupler
    if hasattr(coupler, "rigid_velocities"):
        for name, (linear, angular) in coupler.rigid_velocities().items():
            bodies[name]["linear_velocity_m_s"] = linear
            bodies[name]["angular_velocity_rad_s"] = angular
            link = articulations[name]["links"][world.entities[name].base_link.name]
            link["linear_velocity_m_s"], link["angular_velocity_rad_s"] = linear.copy(), angular.copy()
    return bodies, articulations


def differences(a, b, path=""):
    if type(a) is not type(b):
        return [f"{path}: {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        if list(a) != list(b):
            return [f"{path}: keys {list(a)} != {list(b)}"]
        return [d for k in a for d in differences(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, np.ndarray):
        if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
            return [f"{path}: {a.dtype}{a.shape} {a.ravel()[:4]} != {b.dtype}{b.shape} {b.ravel()[:4]}"]
        return []
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("family"); ap.add_argument("instance")
    ap.add_argument("--steps", type=int, default=6); ap.add_argument("--out")
    a = ap.parse_args()
    s = Session(a.family, instance=a.instance, strict=False)   # the readback, not the instance identity, is under test
    world = s.env._world
    batched = world.read_state
    log = dict(ticks=0, rigid_entities=0, links=0, diffs=[], batched_s=[], legacy_s=[])

    def compared():
        t = time.perf_counter(); state = batched(); t1 = time.perf_counter()
        bodies, articulations = legacy(world); t2 = time.perf_counter()
        log["batched_s"].append(t1 - t); log["legacy_s"].append(t2 - t1); log["ticks"] += 1
        log["rigid_entities"] = len(bodies); log["links"] = sum(len(v["links"]) for v in articulations.values())
        found = differences(state["bodies"], bodies, "bodies") + differences(state["articulations"], articulations, "articulations")
        log["diffs"] += [f"tick {log['ticks']}: {d}" for d in found[:5]]
        return state

    world.read_state = compared
    hold = s.hold_action()
    step_s = []
    for k in range(a.steps):   # small joint-target motion, clipped to the limits by Session.step
        t = time.perf_counter(); s.step(hold + np.float32(0.02 * np.sin(1 + k))); step_s.append(time.perf_counter() - t)
    world.read_state = batched
    med = lambda v: round(float(np.median(v)), 4) if v else None
    report = dict(family=a.family, ticks=log["ticks"], rigid_entities=log["rigid_entities"], links=log["links"],
                  identical=not log["diffs"], diffs=log["diffs"][:20], batched_read_s=med(log["batched_s"]),
                  legacy_read_s=med(log["legacy_s"]), step_s_with_both=med(step_s), episode_end=s.status()["episode_end"])
    print(json.dumps(report), flush=True)
    if a.out:
        open(a.out, "w").write(json.dumps(report, indent=1) + "\n")
    s.close()
    return 0 if report["identical"] and report["ticks"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""Virtual-hand witness: the frozen cloth follows a two-patch route without a robot.

Only the declared patches are pinned (Genesis fix_particles) and moved each
physics tick with the route, like native link attachment moves a held patch.
Everything else is the unmodified PBD scene: gravity, material, table friction.
Between stages both patches are released and the cloth rests for the robot's
regrasp time; each new patch must pass the assist's exposure test on the live
cloth. The robot stays at its home targets. This shows that a route of two
gripper-sized patches flattens the actual initial state; it is not a robot
proof and never sets the Task result.
"""
import hashlib
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from topogym.utils.grasp import material_patch, exposed_patch
from topogym.utils.io import to_jsonable, write_json_atomic
from .routes import PATCH, ROUTES

CONTACT_DISTANCE = .006  # SoftGraspTarget.contact_distance_m default, the assist's exposure clearance


def guard_edges(uv):
    """Material edges exactly as SoftGraspBackend.initialize_material builds them."""
    tree = cKDTree(uv)
    distance, _ = tree.query(uv, k=min(5, len(uv)))
    edges = np.asarray(sorted(tree.query_pairs(1.6*np.median(distance[:, 1]))), dtype=int).reshape(-1, 2)
    rest = np.linalg.norm(uv[edges[:, 1]]-uv[edges[:, 0]], axis=1)
    return edges[rest > 1e-10], rest[rest > 1e-10]


def segment_goal(segment, side, origin, current, table):
    """Patch-centre goal: absolute `to` (x, y, height), grasp-relative `by` (dx, dy, height), or hold."""
    if "to" in segment:
        x, y, h = segment["to"][side]
    elif "by" in segment:
        dx, dy, h = segment["by"][side]
        x, y = origin[0]+dx, origin[1]+dy
    else:
        return current
    return np.array([x, y, table+h])


def smoothstep(s):
    return s*s*(3.-2.*s)


def run_witness(output, *, variation="easy", seed=0, settle_s=4., pause_s=4., work_dir=None):
    from topogym.simulator import Env, SimulatorConfig
    output = Path(output)
    route = ROUTES[variation]
    guard_limit = route["max_strain_ratio"]
    # The frozen scene identity includes the camera rig, so RGB stays enabled;
    # this witness never samples observations.
    config = SimulatorConfig(task_id="blanket_flatten", variation_id=variation, compute_backend="cuda",
                             enable_rgb=True, enable_privileged=True,
                             work_dir=Path(work_dir or output/"episodes"))
    started = time.monotonic()
    with Env(config) as env:
        env.reset(seed=seed)
        world, task = env._world, env._task
        cloth = world.entities["blanket"]
        uv, table, dt = task.material_uv, task.table_height_m, env.config.physics_dt_s
        edges, rest = guard_edges(uv)

        def positions():
            return np.asarray(world.read_state()["particles"]["blanket"]["position_m"])

        timeline, frames, frame_times = [], [], []
        peak = dict(task_edge_ratio=0., guard_edge_ratio=0.)
        held_now = [False]

        def sample(phase):
            state = world.read_state()
            ok, reason, metrics = task.evaluate_state(state)
            p = np.asarray(state["particles"]["blanket"]["position_m"])
            guard = float((np.linalg.norm(p[edges[:, 1]]-p[edges[:, 0]], axis=1)/rest).max())
            if held_now[0]:
                peak["task_edge_ratio"] = max(peak["task_edge_ratio"], metrics.get("maximum_stretch_ratio", np.inf))
                peak["guard_edge_ratio"] = max(peak["guard_edge_ratio"], guard)
            row = dict(sim_time_s=world.sim_time_s, physics_step=world.physics_step, phase=phase, held=held_now[0],
                       predicate=bool(ok), reason=reason, guard_edge_ratio=guard, **metrics)
            timeline.append(row)
            if world.physics_step % 40 == 0:
                frames.append(p.astype(np.float32))
                frame_times.append(world.sim_time_s)
            return row

        def advance(ticks, phase):
            for _ in range(ticks):
                world.advance()
                if world.physics_step % 10 == 0:
                    sample(phase)

        sample("start")
        grasps = []
        for index, stage in enumerate(route["stages"]):
            if index:
                advance(int(round(pause_s/dt)), "regrasp_pause")
            x = positions()
            hands = {}
            for side, target in stage["grasp_uv"].items():
                center = int(np.argmin(np.sum((uv-np.asarray(target))**2, axis=1)))
                patch = material_patch(x, uv, center, **PATCH)
                hands[side] = dict(center=center, indices=patch, offsets=x[patch]-x[center], target=x[center].copy(),
                                   origin=x[center].copy())
            if np.intersect1d(hands["left"]["indices"], hands["right"]["indices"]).size:
                raise ValueError("Route patches overlap")
            exposed = {side: bool(exposed_patch(x, uv, h["indices"], radius=PATCH["spatial_radius_m"],
                                                clearance=CONTACT_DISTANCE)) for side, h in hands.items()}
            grasps.append(dict(stage=index, physics_step=world.physics_step, exposed=exposed,
                               **{side: dict(center_index=h["center"], patch_particles=len(h["indices"]),
                                             position_m=x[h["center"]].tolist()) for side, h in hands.items()}))
            for hand in hands.values():
                cloth.fix_particles(particles_idx_local=hand["indices"])
            held_now[0] = True
            for segment in stage["segments"]:
                start = {side: hand["target"].copy() for side, hand in hands.items()}
                goal = {side: segment_goal(segment, side, hands[side]["origin"], start[side], table) for side in hands}
                ticks = int(round(segment["duration_s"]/dt))
                for i in range(ticks):
                    u = smoothstep((i+1)/ticks)
                    for side, hand in hands.items():
                        hand["target"] = start[side]+u*(goal[side]-start[side])
                        cloth.set_particles_pos(hand["target"]+hand["offsets"], particles_idx_local=hand["indices"])
                    world.advance()
                    if world.physics_step % 10 == 0:
                        sample(f"{index}:{segment['name']}")
            for hand in hands.values():
                cloth.release_particle(particles_idx_local=hand["indices"])
            held_now[0] = False
        release_step = world.physics_step
        advance(int(round(settle_s/dt)), "settle")
    # Contiguous predicate time at the 25 ms control sampling, after release.
    hold = best = 0.
    first = None
    for row in timeline:
        if row["physics_step"] <= release_step:
            continue
        hold = hold+10*dt if row["predicate"] else 0.
        best = max(best, hold)
        if row["predicate"] and first is None:
            first = row["sim_time_s"]
    final = timeline[-1]
    verified = (best >= task.config["stable_duration_s"] and final["predicate"]
                and peak["guard_edge_ratio"] <= guard_limit and all(all(g["exposed"].values()) for g in grasps))
    np.savez_compressed(output/"witness_frames.npz", positions=np.stack(frames), sim_time_s=np.asarray(frame_times),
                        material_uv=uv, table_height_m=table)
    source = {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(Path(__file__).parent.glob("*.py"))}
    witness = dict(
        status="object_witness_verified" if verified else "object_witness_rejected",
        scope="virtual two-patch route on the frozen initial state; robot stationary; not a robot proof",
        variation_id=variation, seed=seed, route=route, patch=PATCH,
        grasps=grasps, pause_between_stages_s=pause_s,
        initial_state=to_jsonable(env._initial_state_report) if hasattr(env, "_initial_state_report") else None,
        release_physics_step=release_step, first_predicate_time_s=first,
        longest_predicate_hold_s=best, required_hold_s=task.config["stable_duration_s"],
        peak_while_held=peak, guard_strain_limit=guard_limit, final=final,
        timeline=timeline[::4], source_sha256=source, wall_time_s=time.monotonic()-started)
    write_json_atomic(output/"object_witness.json", to_jsonable(witness))
    return witness

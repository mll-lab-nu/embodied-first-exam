"""Manager oracle: pregrasp birth, assisted acquisition, planned joint route, separated hold.

Only the observation policy issues native JOINT_ABS targets. Object poses and
passive joints are never set. The plan comes from a separately verified
held_plan.json; this routine re-derives nothing about its geometry.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.arrays import to_numpy
from topogym.planning.rigid_reference.feedback import body_pose
from topogym.utils.io import write_json_atomic, to_jsonable
from .guards import ClawsGuardedSequence
from .held_oracle import plan_held_route


def export_robot_geometry(env, output):
    arrays, links = {}, []
    for link in env._robot.entity.links:
        p = to_numpy(link.get_pos()).reshape(3)
        r = Rotation.from_quat(to_numpy(link.get_quat()).reshape(4)[[1, 2, 3, 0]])
        keys = []
        for geom in link.geoms:
            key = f"geom_{len(arrays)//2}"
            arrays[key+"_vertices"] = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
            arrays[key+"_faces"] = np.asarray(geom.init_faces)
            keys.append(key)
        links.append(dict(name=link.name, index=int(link.idx), local_index=int(link.idx_local), geoms=keys))
    np.savez_compressed(output/"robot_geometry.npz", **arrays)
    write_json_atomic(output/"robot_geometry.json", dict(links=links,
        sha256=hashlib.sha256((output/"robot_geometry.npz").read_bytes()).hexdigest(),
        frame="Genesis relative=True authored link frames", source="imported robot collision surfaces"))


def run_claws_oracle(env, runner, output, witness, *, joint_speed_rad_s=.2, acquisition_s=1., piece_force_n=5., integral_gain=.3, wrist_feedforward=False, relative_servo=False):
    output = Path(output)
    task = env._task
    if task.task_id != "interlocked_claws" or env._world.physics_step != 0:
        raise ValueError("The oracle must begin at the Claws pregrasp birth state")
    if witness["status"] != "object_witness_verified" or witness["instance_id"] != task.instance_id:
        raise ValueError("A verified object witness for this exact instance is required")
    control_dt = env.config.physics_dt_s*env.config.control_decimation
    if env.config.grasp_assist.model != "contact_weld_v1":
        raise ValueError("This oracle declares contact-triggered assistance on both hands")
    target, = task.placement_targets
    other, = task.placement_remainder
    from .held_oracle import ownership_for
    ownership = ownership_for(task)
    hands = {side: (f"{side}/gripper_link", name) for name, side in ownership.items()}
    q_indices = {side: list(env._robot._q_indices[side][:6]) for side in env._robot.groups}
    report = dict(status="running", start="pregrasp_birth", assistance=env.config.grasp_assist.model,
                  config=to_jsonable(env.config), instance_id=task.instance_id, asset_sha256=env._asset_build.sha256,
                  witness_sha256=hashlib.sha256(json.dumps(witness, sort_keys=True).encode()).hexdigest(),
                  phases=[], task_success=False, accepted_proof=False, maximum_joint_speed_rad_s=joint_speed_rad_s, piece_force_limit_n=piece_force_n, integral_gain=integral_gain, wrist_feedforward=wrist_feedforward, relative_servo=relative_servo,
                  contact_coverage="tick-end samples; no all-substep claim")
    source = Path(__file__).read_bytes()+Path(__file__).with_name("guards.py").read_bytes()
    export_robot_geometry(env, output)

    def hold(seconds):
        return [{}]*int(np.ceil(seconds/control_dt))

    def joint_actions(rows, start, start_relative=None):
        """Joint targets per control step; also the planned relative pose (other piece in the target piece's
        frame) per step so the executor can servo it. Rows without piece poses yield None targets."""
        from topogym.planning.rigid_reference.feedback import relative_pose
        from topogym.planning.rigid_reference.geometry import interpolate
        previous = np.asarray(start, float)
        previous_relative = start_relative
        actions, relatives = [], []
        for row in rows:
            q = np.asarray(row["qpos"], float)
            relative = relative_pose(body_pose(row["pieces"][target]), body_pose(row["pieces"][other])) if "pieces" in row else None
            arms = np.concatenate([q_indices["left"], q_indices["right"]])
            count = max(1, int(np.ceil(np.max(np.abs(q[arms]-previous[arms]))/(joint_speed_rad_s*control_dt))))
            for u in np.linspace(0., 1., count+1)[1:]:
                step = previous+u*(q-previous)
                actions.append({side: {"joint_position_rad": step[q_indices[side]].tolist()} for side in ("left", "right")})
                relatives.append(interpolate(previous_relative, relative, u) if (relative is not None and previous_relative is not None) else relative)
            previous, previous_relative = q, relative
        return actions, relatives

    def run(name, actions, *, guard=True, relatives=None, servo=False, initial_offset=None):
        print(f"{name}: {len(actions)} control steps", flush=True)
        write_json_atomic(output/f"{name}_actions.json", actions)
        from topogym.planning.base import ActionSequencePolicy
        policy = (ClawsGuardedSequence(actions, pieces=(target, other), hands=hands, piece_force_n=piece_force_n, integral_gain=integral_gain,
                                       relative_targets=relatives if servo else None, kin=executor_kin if servo else None,
                                       servo_side=ownership[other] if servo else None, wrist_load=wrist_load if wrist_feedforward else None,
                                       initial_offset=initial_offset) if guard else ActionSequencePolicy(actions))
        result = runner.run_policy(request_id=name, policy=policy,
            submission_hash=hashlib.sha256(source+json.dumps(actions, sort_keys=True).encode()).hexdigest(),
            mode="unlimited", state_fields=("world",))
        state = dict(world=env._world.read_state(), robot=env._robot.observe(), segment=result)
        write_json_atomic(output/f"{name}_state.json", state)
        phase = dict(name=name, result=result)
        if guard:
            phase["guard_maxima"] = policy.maximum
            phase["relative_servo"] = policy.servo
            phase["wrist_feedforward"] = policy.wrist_ff
        report["phases"].append(phase)
        write_json_atomic(output/"oracle_report.json", report)
        if result["reason"] != "policy_done" and not task.result.task_success:
            raise RuntimeError(f"{name}: {result['reason']}")
        return state

    write_json_atomic(output/"oracle_report.json", report)
    try:
        birth = env._world.read_state()
        for name in (target, other):
            authored = np.asarray(witness["initial_poses"][name]["position_m"])
            if np.linalg.norm(authored-np.asarray(birth["bodies"][name]["position_m"])) > 1e-6:
                raise RuntimeError("Witness and live birth poses differ")
        state = run("acquire", hold(acquisition_s), guard=False)
        world = state["world"]
        bindings = {side: world["grasp"]["hands"][side]["binding"] for side in hands}
        if not world["assist_active"] or any(b is None for b in bindings.values()):
            raise RuntimeError("Both hands must acquire their piece through contact before moving")
        if {tuple(b["target"])[0] for b in bindings.values()} != {target, other}:
            raise RuntimeError("Assisted bindings do not hold one piece per hand")
        report["bindings"] = to_jsonable(bindings)
        # Plan from the measured post-acquisition state: sag before binding is real and stays in the grasp.
        plan = plan_held_route(env, witness, output/"measured_plan", measured=True,
                               progress=lambda e: print(e, flush=True))
        report["measured_plan_status"] = plan["status"]
        if plan["status"] != "held_ik_route_found":
            raise RuntimeError("Measured-state route planning failed: "+plan["status"])
        q0 = to_numpy(env._robot.entity.get_qpos()).reshape(-1)
        from .object_oracle import frozen_problem
        from .kinematics import ClawsIK
        _, executor_meshes, _, _, _ = frozen_problem(output/"executor_geometry", variation=task.variation_id.removeprefix("interlocked_claws_"), seed=task.seed)
        executor_kin = ClawsIK(env, executor_meshes, ownership)
        wrist_load = {}
        for name, side in ownership.items():
            mesh = executor_meshes[name].copy(); mesh.density = 600.
            try:
                mass, com = float(mesh.mass), np.asarray(mesh.center_mass, float)
            except Exception:
                mass, com = 600.*float(abs(mesh.volume)), np.asarray(mesh.centroid, float)
            dp, dr = executor_kin.offsets[side]      # T_piece_tcp
            wrist_load[side] = dict(mass_kg=mass, com_in_tcp_m=dr.inv().apply(com-dp).tolist())
        report["wrist_load_model"] = wrist_load
        # Relative-pose servo on the separation stage is opt-in (gentle, rate-limited outer loop).
        stages = [("separate", plan["separation_rows"], relative_servo)]
        current = q0
        live = env._world.read_state()
        from topogym.planning.rigid_reference.feedback import relative_pose as _rel
        current_relative = _rel(body_pose(live["bodies"][target]), body_pose(live["bodies"][other]))
        for name, rows, servo in stages:
            if not rows:
                continue
            actions, relatives = joint_actions(rows, current, current_relative)
            # Start the integral correction at the measured droop under the held load, so the first command
            # keeps the acquisition hold target (continuous) instead of stepping onto the sagged posture.
            observed = env._robot.observe()
            droop = {side: np.asarray(observed[side]["joint_position_target_rad"], float)
                     - np.asarray(observed[side]["joint_position_rad"], float) for side in hands}
            run(name, actions+hold(.5), relatives=relatives+[None]*len(hold(.5)), servo=servo, initial_offset=droop)
            current = np.asarray(rows[-1]["qpos"], float)
            current_relative = relatives[-1]
            if task.result.task_success:
                break
        if not task.result.task_success:
            run("stable_goal", hold(3.))
        reached, failure, metrics = task.evaluate_goal_region(env._world.read_state(), task.goal_region)
        report.update(status="native_success_pending_audit" if task.result.task_success else "candidate_completed",
                      task_success=bool(task.result.task_success), candidate_reached=reached, candidate_failure=failure,
                      candidate_metrics=metrics, task_result=to_jsonable(task.result),
                      physics_steps=env._world.physics_step, simulation_time_s=env._world.sim_time_s)
        return report
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}",
                      task_result=to_jsonable(task.result), physics_steps=env._world.physics_step,
                      simulation_time_s=env._world.sim_time_s)
        raise
    finally:
        write_json_atomic(output/"oracle_report.json", report)

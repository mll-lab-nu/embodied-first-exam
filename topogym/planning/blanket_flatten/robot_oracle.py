"""ALOHA execution of a virtual-hand Blanket route with pbd_local_patch_v1.

Every phase is planned from the measured state at its start and executed as
native JOINT_ABS actions through SegmentRunner. The policy never writes cloth
or robot state: it sends joint and gripper targets only. The assist attaches a
patch when both real finger surfaces are within its admission distance, and
releases it on an opening command. IK is Genesis' native solver with checked
residuals, seeded along the path.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.robot.grasp_geometry import read_grasp_geometry
from topogym.solvers.genesis_kinematics import GenesisIKSolver
from topogym.utils.arrays import to_numpy
from topogym.utils.grasp import material_patch
from topogym.utils.io import to_jsonable, write_json_atomic
from .object_oracle import segment_goal
from .routes import PATCH, ROUTES

SIDES = ("left", "right")
# Local +x (approach) points down; local y (closing) along world -y. Half-turn
# variants about world z are searched per arm for joint-limit margin.
DOWN = Rotation.from_quat([.7071067811865476, 0., -.7071067811865476, 0.])
PRESHAPE_M, PINCH_M, OPEN_M = .015, .006, .037   # native finger rail coordinates
FINGERTIP_GAP_M = .0015                          # fingertip clearance above the patch top at the start of contact


class Sequence:
    """Precomputed actions; optionally stop early when the observation says so."""
    def __init__(self, actions, stop=None):
        self.actions, self.stop, self.index = list(actions), stop, 0

    def act(self, obs):
        if self.index == len(self.actions) or (self.stop is not None and self.stop(obs)):
            return None
        self.index += 1
        return self.actions[self.index-1]


def held(obs):
    hands = obs["privileged"]["world"].get("grasp", {}).get("hands", {})
    return {side: bool(hands.get(side, {}).get("binding")) for side in SIDES}


class Arms:
    def __init__(self, env):
        self.env, self.robot = env, env._robot
        self.ik = GenesisIKSolver(self.robot.entity)
        self.q_index = {s: list(self.robot._q_indices[s][:6]) for s in SIDES}
        self.dof_index = {s: list(self.robot._indices[s][:6]) for s in SIDES}
        self.limits = {s: np.asarray(env.action_spec["groups"][s]["joint_limits_rad"]) for s in SIDES}
        self.rotation = {}

    def qpos(self):
        return to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()

    def tcp(self):
        measured = self.robot.observe()
        return {s: np.asarray(measured[s]["tcp_position_world_m"]) for s in SIDES}

    def solve(self, side, position, seed, rotation=None):
        group = self.robot.groups[side]
        rotation = self.rotation[side] if rotation is None else rotation
        hand = rotation*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        return self.ik.solve_checked(link_name=group.hand_link,
            position_world_m=np.asarray(position)-hand.apply(group.tcp_position_in_hand_m),
            orientation_wxyz=hand.as_quat()[[3, 0, 1, 2]], initial_qpos=seed,
            joint_dof_indices=self.dof_index[side], max_solver_iterations=300)

    def margin(self, side, q):
        value, limit = q[self.q_index[side]], self.limits[side]
        return float(np.min(np.minimum(value-limit[:, 0], limit[:, 1]-value)))

    def action(self, q, grip):
        return {s: {"joint_position_rad": q[self.q_index[s]].tolist(), "gripper_position_m": float(grip[s])}
                for s in SIDES}

    def fingertip_extension(self, side):
        """Actual finger collision surfaces beyond the TCP along the approach axis."""
        measured = self.robot.observe()[side]
        tcp = np.asarray(measured["tcp_position_world_m"])
        axis = Rotation.from_quat(np.roll(measured["tcp_orientation_wxyz"], -1)).apply([1., 0., -.023])
        axis /= np.linalg.norm(axis)
        return float(max(((v-tcp) @ axis).max() for v, _ in read_grasp_geometry(self.robot, side)["surfaces"]))


def smoothstep(s):
    return s*s*(3.-2.*s)


def export_robot_geometry(env, output):
    """Imported collision surfaces in authored link frames, for the offline audit."""
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


class Contact:
    """Lower each unheld hand 1 mm per step until the assist admits it.

    Every step re-reads the live cloth: the fingertips are commanded to the
    pinched material point's current XY and to `depth` below the hover height
    over its patch, so a patch that sags or slides is followed rather than
    approached at a stale pose. Admitted hands keep their command.
    """
    def __init__(self, arms, commands, q, grip, *, hover, centers, uv, patch, step_m=.001, max_steps=25, dwell=10):
        self.arms, self.commands, self.q, self.grip = arms, commands, q, grip
        self.hover, self.centers, self.uv, self.patch = hover, centers, uv, patch
        self.step_m, self.max_steps, self.dwell = step_m, max_steps, dwell
        self.depth = dict.fromkeys(SIDES, 0.)
        self.steps, self.tick, self.log = 0, 0, []

    def act(self, obs):
        state = held(obs)
        if all(state.values()):
            return None
        if self.tick % self.dwell == 0:
            if self.steps == self.max_steps:
                return None
            self.steps += 1
            world = obs["privileged"]["world"]
            x = np.asarray(world["particles"]["blanket"]["position_m"])
            self.log.append(dict(step=self.steps, held=state, admission=world.get("grasp", {}).get("admission", {}),
                                 commands={s: c.tolist() for s, c in self.commands.items()}))
            for side in SIDES:
                if not state[side]:
                    self.depth[side] += self.step_m
                    center = self.centers[side]
                    top = float(x[material_patch(x, self.uv, center, **self.patch), 2].max())
                    self.commands[side] = np.array([*x[center][:2], top+self.hover[side]-self.depth[side]])
                self.q = self.arms.solve(side, self.commands[side], self.q)
        self.tick += 1
        return self.arms.action(self.q, self.grip)


def cartesian(arms, q, starts, goals, duration_s, dt, grip):
    """Smoothstep TCP interpolation, checked IK per control tick, seeded along the path."""
    actions, worst = [], np.inf
    count = max(1, int(round(duration_s/dt)))
    for i in range(count):
        u = smoothstep((i+1)/count)
        for side in SIDES:
            q = arms.solve(side, starts[side]+u*(goals[side]-starts[side]), q)
            worst = min(worst, arms.margin(side, q))
        actions.append(arms.action(q, grip))
    return actions, q, worst


def run_route_oracle(env, runner, output, *, variation="easy"):
    output = Path(output)
    if env._world.physics_step != 0:
        raise ValueError("The complete oracle must begin at the episode's default home state")
    if env.config.grasp_assist.model != "pbd_local_patch_v1" or env.config.control_mode != "JOINT_ABS":
        raise ValueError("The Blanket oracle uses pbd_local_patch_v1 and JOINT_ABS")
    route = ROUTES[variation]
    task, world = env._task, env._world
    table, uv = task.table_height_m, task.material_uv
    dt = env.config.physics_dt_s*env.config.control_decimation
    arms = Arms(env)
    source = b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
    if env.config.grasp_assist.targets[0].max_strain_ratio != route["max_strain_ratio"]:
        raise ValueError("Assist strain guard must match the route's declared value")
    report = dict(status="running", start="default_home", variation_id=variation, route=route, patch=PATCH,
                  assistance="pbd_local_patch_v1", control_mode="JOINT_ABS", config=to_jsonable(env.config),
                  instance_id=task.instance_id, phases=[], task_success=False, accepted_proof=False,
                  grasp_semantics="bilateral finger-surface proximity admission; native kinematic patch attachment; "
                                  "no measured clamping force")
    export_robot_geometry(env, output)
    # Inputs of the independent audit: rest material map, gates and frozen start identity.
    np.savez_compressed(output/"material_map.npz", uv=uv)
    declaration = task.frozen_initial_state()
    report.update(task_config={k: task.config[k] for k in ("minimum_coverage_ratio", "maximum_height_m",
                               "maximum_stretch_ratio", "maximum_speed_m_s", "stable_duration_s")},
                  layout=dict(length_m=task.layout.length_m, width_m=task.layout.width_m,
                              particle_size_m=task.layout.particle_size_m),
                  table_height_m=table, initial_state_manifest=str(declaration.manifest_path),
                  initial_state_sha256=declaration.sha256,
                  joint_limits_rad={s: arms.limits[s].tolist() for s in SIDES},
                  material_map_sha256=hashlib.sha256((output/"material_map.npz").read_bytes()).hexdigest())

    def cloth():
        return np.asarray(world.read_state()["particles"]["blanket"]["position_m"])

    def run(name, policy, actions=None):
        if task.result.terminated:
            return dict(name=name, skipped="episode already terminated", held=dict.fromkeys(SIDES, False))
        print(f"{name}: {'feedback' if actions is None else len(actions)} control steps", flush=True)
        if actions is not None:
            write_json_atomic(output/f"{name}_actions.json", actions)
        digest = hashlib.sha256(source+name.encode()+json.dumps(actions, sort_keys=True).encode()).hexdigest()
        # Only feedback policies read world/grasp state; open-loop phases take none, keeping the per-tick
        # step records small. No camera is selected, so the runner records no frames or video.
        reads_world = actions is None or getattr(policy, "stop", None) is not None
        result = runner.run_policy(request_id=name, policy=policy, submission_hash=digest, mode="unlimited",
                                   observation_profile={"rgb_camera_ids": []},
                                   state_fields=("world",) if reads_world else ())
        grasp = world.read_state().get("grasp", {})
        phase = dict(name=name, result=result, held={s: bool(grasp.get("hands", {}).get(s, {}).get("binding"))
                                                      for s in SIDES}, health=grasp.get("health"))
        report["phases"].append(phase)
        write_json_atomic(output/"oracle_report.json", to_jsonable(report))
        return phase

    def hold(seconds, q, grip):
        return [arms.action(q, grip)]*int(np.ceil(seconds/dt))

    write_json_atomic(output/"oracle_report.json", to_jsonable(report))
    try:
        extension = {s: arms.fingertip_extension(s) for s in SIDES}
        report.update(fingertip_extension_m=extension, stages=[])
        q = arms.qpos()
        for index, stage in enumerate(route["stages"]):
            # Stage 0 keeps the single-stage phase names; later stages are suffixed.
            name = (lambda base: base) if index == 0 else (lambda base, i=index: f"{base}_{i+1}")
            log = dict(stage=index)
            report["stages"].append(log)
            # Grasp sites: material points named by the route, located on the live cloth.
            x = cloth()
            centers = {s: int(np.argmin(np.sum((uv-np.asarray(stage["grasp_uv"][s]))**2, axis=1))) for s in SIDES}
            # Top-down orientation per arm: the half-turn with the larger joint margin along the stage.
            choice = {}
            for side in SIDES:
                best = None
                for yaw in (0., 180.):
                    rotation = Rotation.from_euler("z", yaw, degrees=True)*DOWN
                    try:
                        probe, worst = q.copy(), np.inf
                        points = [x[centers[side]]+[0., 0., .10]]+[
                            segment_goal(seg, side, x[centers[side]], None, table)+[0., 0., .02]
                            for seg in stage["segments"] if "to" in seg or "by" in seg]
                        for point in points:
                            probe = arms.solve(side, point, probe, rotation)
                            worst = min(worst, arms.margin(side, probe))
                    except ValueError:
                        continue
                    if best is None or worst > best[1]:
                        best = (yaw, worst)
                if best is None:
                    raise RuntimeError(f"No top-down IK along stage {index} for {side}")
                choice[side] = best
                arms.rotation[side] = Rotation.from_euler("z", best[0], degrees=True)*DOWN
            log.update(yaw_deg={s: c[0] for s, c in choice.items()},
                       planned_route_joint_margin_rad={s: c[1] for s, c in choice.items()})
            grip = {s: PRESHAPE_M for s in SIDES}

            # 1. Current pose (home, or 8 cm above the last release) -> 10 cm above the sites,
            #    joint-space, jaws pre-shaped narrow.
            goal = q.copy()
            for side in SIDES:
                goal = arms.solve(side, x[centers[side]]+[0., 0., .10], goal)
            count = int(round(3./dt))
            actions = [arms.action(q+smoothstep((i+1)/count)*(goal-q), grip) for i in range(count)]
            actions += hold(.3, goal, grip)
            run(name("approach"), Sequence(actions), actions)
            # 2. Descend so fingertips stop 1.5 mm above the live patch top.
            x, q = cloth(), arms.qpos()
            commands = {}
            for side in SIDES:
                patch = material_patch(x, uv, centers[side], **PATCH)
                top = float(x[patch, 2].max())+task.layout.particle_size_m/2
                commands[side] = np.array([*x[centers[side]][:2], top+FINGERTIP_GAP_M+extension[side]])
            log["pinch_commands_m"] = {s: c.tolist() for s, c in commands.items()}
            actions, q, _ = cartesian(arms, q, arms.tcp(), commands, 1.5, dt, grip)
            actions += hold(.3, q, grip)
            run(name("descend"), Sequence(actions), actions)
            # 3. Close the jaws in the air, then lower until both assists admit.
            grip = {s: PINCH_M for s in SIDES}
            actions = hold(.6, q, grip)
            run(name("close"), Sequence(actions, stop=lambda obs: all(held(obs).values())), actions)
            hover = {s: task.layout.particle_size_m/2+FINGERTIP_GAP_M+extension[s] for s in SIDES}
            contact = Contact(arms, commands, q, grip, hover=hover, centers=centers, uv=uv, patch=PATCH)
            phase = run(name("contact"), contact)
            log["contact_log"] = contact.log
            if not all(phase["held"].values()):
                raise RuntimeError(f"Assist did not admit both hands: {phase['held']}")
            # 4. Route segments: the held patches follow the witness route. Commands continue from the
            #    admitted contact command, keeping the arm's steady tracking offset out of the route.
            x, q = cloth(), contact.q
            origin = {s: x[centers[s]].copy() for s in SIDES}
            offset = {s: contact.commands[s]-origin[s] for s in SIDES}
            log["command_minus_patch_center_m"] = {s: o.tolist() for s, o in offset.items()}
            starts = dict(contact.commands)
            for segment in stage["segments"]:
                goals = {s: (segment_goal(segment, s, origin[s], None, table)+offset[s]
                             if "to" in segment or "by" in segment else starts[s]) for s in SIDES}
                actions, q, worst = cartesian(arms, q, starts, goals, segment["duration_s"], dt, grip)
                log.setdefault("route_joint_margin_rad", {})[segment["name"]] = worst
                phase = run(name(segment["name"]), Sequence(actions, stop=lambda obs: not all(held(obs).values())),
                            actions)
                if not all(phase["held"].values()) and not task.result.task_success:
                    raise RuntimeError(f"{segment['name']}: assisted grasp lost {phase['held']} {phase['health']}")
                starts = goals
            # 5. Open and lift the hands 8 cm.
            grip = {s: OPEN_M for s in SIDES}
            actions = hold(.5, q, grip)
            run(name("release"), Sequence(actions), actions)
            up = {s: starts[s]+[0., 0., .08] for s in SIDES}
            actions, q, _ = cartesian(arms, q, starts, up, 1.5, dt, grip)
            run(name("retreat"), Sequence(actions), actions)
        # 6. Wait for the Task's own settled predicate.
        if not task.result.task_success:
            actions = hold(route.get("settle_s", 10.), q, grip)
            run("settle", Sequence(actions), actions)
        report.update(status="complete", task_success=bool(task.result.task_success),
                      task_result=to_jsonable(task.result), sim_time_s=world.sim_time_s,
                      physics_steps=world.physics_step)
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}",
                      task_result=to_jsonable(task.result))
        raise
    finally:
        write_json_atomic(output/"oracle_report.json", to_jsonable(report))
    return report

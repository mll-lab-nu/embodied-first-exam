"""Joint-controlled horseshoe manipulation with free, gravity-driven rings.

Pose assignments are confined to reset. Checkpoint resets are exploration only;
a complete task qualification must start from the original assembly.
"""
from pathlib import Path
import hashlib
import json
import shutil

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from .gravity_demo import ROOT, array, sha
from .robot_motion import Kinematics, PAD_CENTER

PHYSICAL_SEED = ROOT / "assets/tasks/horseshoe_ring/tutorial_solvable_v3/physical_seed.json"


class PhysicalMotion:
    def __init__(self, output, *, dt=.002, checkpoint=None, initial_grasps=None, instance=None):
        import genesis as gs
        from topogym.robot.aloha import AlohaDualArmController
        from .scene import build_scene
        if not np.isfinite(dt) or dt <= 0 or not np.isclose(.05/dt, round(.05/dt)):
            raise ValueError("dt must divide the 20 Hz recording interval")
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        from topogym.world.aloha_cameras import configure_aloha_rig
        self.instance = instance
        if instance is None:
            with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
                self.cfg = cfg = compose(config_name="horseshoe_ring_aloha")
        else:
            from .variant_generator import validate_instance
            validate_instance(instance)
            self.cfg = cfg = OmegaConf.create(instance["resolved_config"])
            (self.output/"instance.json").write_text(json.dumps(instance, ensure_ascii=False, indent=2))
            from ompl.util import RNG
            RNG.setSeed(instance["episode_spec"]["execution_profile"]["parameters"]["planning_seed"])
        cfg.run.output = str(self.output)
        cfg.env.genesis.backend = "cpu"
        cfg.env.renderer.type = "rasterizer"
        cfg.env.sim.dt = dt
        cfg.env.sim.substeps = 4
        cfg.env.sim.gravity = [0., 0., -9.81]
        cfg.robot_control.controller.kp = [10000, 18000, 14000, 6000, 4000, 2500, 2000]
        cfg.robot_control.controller.kv = [200, 300, 250, 100, 80, 40, 124]
        configure_aloha_rig(cfg, keep=(), resolution=(960, 540), low_pitch_offset_deg=20)
        OmegaConf.set_struct(cfg.env.cameras, False)
        cfg.env.cameras.detail = dict(res=[960, 720], pos=[.12, -.53, 1.43],
            lookat=[-.1356786, .05, 1.10], up=[0, 0, 1], fov=43, near=.005, far=12)
        (self.output / "recording_cameras.json").write_text(json.dumps(
            OmegaConf.to_container(cfg.env.cameras, resolve=True), indent=2))
        cfg.env.cameras = {}
        template = Path(cfg.task.template_path)
        shutil.copy2(template if template.is_absolute() else ROOT/template, self.output / "input_template.json")
        cfg.task.template_path = str(self.output / "input_template.json")
        OmegaConf.save(cfg, self.output / "config.yaml", resolve=True)
        if instance is None:
            shutil.copy2(PHYSICAL_SEED, self.output / "source_motion.json")
        else:
            from .variant_generator import retarget_seed
            seed = retarget_seed(instance, cfg)
            (self.output/"source_motion.json").write_text(json.dumps(seed))
        shutil.copy2(__file__, self.output / "execution_source.py")
        for filename in ("physical_demo.py", "physical_plan.py", "physical_extraction.py", "physical_place.py", "scene.py", "robot_motion.py", "robot_clearance.py"):
            shutil.copy2(Path(__file__).with_name(filename), self.output / filename)
        if instance is not None:
            for filename in ("variant_generator.py", "family_routes.py"):
                shutil.copy2(Path(__file__).with_name(filename), self.output/filename)
        gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
        self.task = task = build_scene(cfg, self.output / "assets")
        self.scene, self.robot = task.scene, task.manifest.get("robot")
        self.ctrl = AlohaDualArmController(self.scene, self.robot, cfg.robot_control)
        self.ctrl.configure()
        self.solver = self.scene.sim.rigid_solver
        self.kin = Kinematics(cfg.robot_control)
        self.mount = np.asarray(cfg.env.robot_mount.pos)
        self.old_motion = json.loads((self.output/"source_motion.json").read_text())
        digest = hashlib.sha256(json.dumps(task.assembly.template, sort_keys=True).encode()).hexdigest()
        if (digest != self.old_motion["report"]["source_template_sha256"]
                or float(cfg.task.scale) != self.old_motion["report"]["scene_scale"]):
            raise ValueError("Physical seed is only qualified for its exact baseline geometry and scale")
        initial = self.old_motion["frames"][0]
        self.checkpoint_start = checkpoint is not None
        self.q = np.asarray((checkpoint or initial)["qpos"])
        self.robot.set_qpos(self.q, zero_velocity=True)
        for name, body in task.bodies.items():
            if checkpoint:
                pose = checkpoint["bodies"][name]
                body.set_pos(np.asarray(pose["pos"]))
                body.set_quat(np.asarray(pose["quat_wxyz"]))
            else:
                pose = initial["bodies"][name]
                body.set_pos(self.mount + pose["pos"])
                body.set_quat(np.asarray(pose["quat"])[[3, 0, 1, 2]])
            body.zero_all_dofs_velocity()
        self.kin.q = self.q.copy()
        self.registrations, self.events = [], []
        self.bodylinks = {b.base_link_idx for b in task.bodies.values()}
        self.names = {b.base_link_idx: n for n, b in task.bodies.items()}
        self.names.update({l.idx: "robot/" + l.name for l in self.robot.links})
        self.names[task.manifest.get("table").base_link_idx] = "table"
        self.dt, self.step_count, self.frame_count = dt, 0, 0
        self.phase = "pregrasp"
        self.max_pen = self.max_nonfinger_pen = 0.
        self.max_robot_pen = 0.
        self.max_robot_table_pen = 0.
        self.max_tracking_error = 0.
        self.tracking_stall_steps = 0
        self.failed = None
        self.fingers = {s: {self.robot.get_link(f"{s}/{f}_finger_link").idx for f in ("left", "right")} for s in ("left", "right")}
        self.trace = (self.output / "physical_states.jsonl").open("w")
        if initial_grasps is None:
            initial_grasps = [("left", "horseshoe_left"), ("right", "horseshoe_right")]
        self.initial_grasps = list(initial_grasps)
        if not checkpoint and initial_grasps != [("left", "horseshoe_left"), ("right", "horseshoe_right")]:
            raise ValueError("Full runs must start from the declared two-shoe pregrasp")
        self.replace_grasps(initial_grasps, reason="checkpoint grasp reset" if checkpoint else "declared initial pregrasp")
        self.initial_ring_z = self.body_pose("target_ring")[0][2]
        self.capture()
        (self.output / "result.json").write_text(json.dumps(dict(complete=False, task_success=False, status="running")))

    def body_pose(self, name):
        b = self.task.bodies[name]
        return array(b.get_pos()), Rotation.from_quat(array(b.get_quat())[[1, 2, 3, 0]])

    def hand_pose(self, side):
        link = self.robot.get_link(side + "/gripper_link")
        r = Rotation.from_quat(array(link.get_quat())[[1, 2, 3, 0]])
        return array(link.get_pos()) + r.apply(PAD_CENTER), r

    def contacts(self):
        ct = self.solver.collider.get_contacts(as_tensor=True, to_torch=True)
        return {k: array(ct[k]) for k in ("link_a", "link_b", "penetration", "force")}

    def grasp_connected(self, side, bodies):
        """Require a loaded contact path across both pads and every grasped body."""
        nodes = self.fingers[side] | {self.task.bodies[n].base_link_idx for n in bodies}
        graph = {v: set() for v in nodes}
        ct = self.contacts()
        for a, b, f in zip(ct["link_a"], ct["link_b"], ct["force"]):
            if a in nodes and b in nodes and np.linalg.norm(f) > .01:
                graph[a].add(b)
                graph[b].add(a)
        # A dangling body touching an already clamped body is not itself
        # clamped. Every body must lie on a simple loaded path between pads.
        first, last = sorted(self.fingers[side])
        supported = set()

        def visit(node, path):
            if node == last:
                supported.update(path)
                return
            for peer in graph[node]-set(path):
                visit(peer, path+[peer])

        visit(first, [first])
        return supported == nodes

    def replace_grasps(self, pairs, *, reason):
        from topogym.tasks.cast_coil.robot_grasp import release_grasps, active_grasps
        added = [(s, n) for s, n in pairs if
                 (self.robot.get_link(s + "/gripper_link").idx, self.task.bodies[n].base_link_idx) not in self.registrations]
        evidence = {}
        if self.step_count:
            for side in {s for s, _ in added}:
                bodies = [n for s, n in pairs if s == side]
                if not self.grasp_connected(side, bodies):
                    raise RuntimeError(f"Cannot attach {side}: no loaded two-pad contact path through {bodies}")
                nodes = self.fingers[side] | {self.task.bodies[n].base_link_idx for n in bodies}
                ct = self.contacts()
                evidence[side] = dict(bodies=bodies, edges=[
                    dict(a=self.names[int(a)], b=self.names[int(b)], force_N=float(np.linalg.norm(f)))
                    for a, b, f in zip(ct["link_a"], ct["link_b"], ct["force"])
                    if a in nodes and b in nodes and np.linalg.norm(f) > .01])
        if self.registrations:
            release_grasps(self.solver, self.registrations)
        self.registrations = [(self.robot.get_link(s + "/gripper_link").idx, self.task.bodies[n].base_link_idx) for s, n in pairs]
        for a, b in self.registrations:
            self.solver.add_weld_constraint(a, b)
        self.events.append(dict(time_s=self.step_count*self.dt, reason=reason, pairs=pairs,
                                contact_evidence=evidence,
                                actual_constraints=active_grasps(self.solver, self.bodylinks)))

    def capture(self):
        from .demo import current_loops
        from topogym.tasks.cast_coil.robot_grasp import active_grasps
        loops = current_loops(self.task)
        links = [int(loops[a].linking(loops[b])) for a, b in self.task.assembly.edges]
        if any(abs(v) != 1 for v in links):
            raise RuntimeError("Physical chain/eye connection lost")
        ct = self.contacts()
        ring_id = self.task.bodies["target_ring"].base_link_idx
        pairs = [[self.names.get(int(a), str(a)), self.names.get(int(b), str(b)), float(np.linalg.norm(f))]
                 for a, b, f in zip(ct["link_a"], ct["link_b"], ct["force"]) if np.linalg.norm(f) > .001]
        peers = {self.names.get(int(v), str(v)) for a, b, f in zip(ct["link_a"], ct["link_b"], ct["force"])
                 if ring_id in (a, b) and np.linalg.norm(f) > .001 for v in (a, b) if v != ring_id}
        row = dict(frame=self.frame_count, step=self.step_count, time_s=self.step_count*self.dt, stage=self.phase,
            qpos=array(self.robot.get_qpos()).tolist(), target_qpos=self.q.tolist(),
            bodies={n: dict(pos=array(b.get_pos()).tolist(), quat_wxyz=array(b.get_quat()).tolist(),
                            velocity=array(b.get_vel()).tolist(), angular_velocity=array(b.get_ang()).tolist()) for n, b in self.task.bodies.items()},
            active_welds=active_grasps(self.solver, self.bodylinks), chain_link_numbers=links,
            contacts=pairs, ring_contact_bodies=sorted(peers), maximum_penetration_m=self.max_pen)
        self.trace.write(json.dumps(row)+"\n")
        self.trace.flush()
        self.frame_count += 1

    def step(self):
        for arm in self.ctrl.arms.values():
            arm.set_arm_qpos(self.q[arm.qs_idx[:6]])
            arm.set_gripper(self.q[arm.qs_idx[6]])
        self.scene.step()
        self.step_count += 1
        indices = np.r_[0:6, 8:14]
        error = float(np.max(np.abs(array(self.robot.get_qpos())[indices]-self.q[indices])))
        self.max_tracking_error = max(self.max_tracking_error, error)
        self.tracking_stall_steps = self.tracking_stall_steps+1 if error > .2 else 0
        if self.tracking_stall_steps*self.dt > .2:
            raise RuntimeError("Arm tracking error exceeds 0.2 rad for more than 0.2 seconds")
        ct = self.contacts()
        a, b = ct["link_a"], ct["link_b"]
        mask = np.isin(a, list(self.bodylinks)) | np.isin(b, list(self.bodylinks))
        pen = float(ct["penetration"][mask].max(initial=0))
        self.max_pen = max(self.max_pen, pen)
        fingers = set.union(*self.fingers.values())
        nonfinger = mask & ~(np.isin(a, list(fingers)) | np.isin(b, list(fingers)))
        self.max_nonfinger_pen = max(self.max_nonfinger_pen, float(ct["penetration"][nonfinger].max(initial=0)))
        robot_links = [link.idx for link in self.robot.links if "base_link" not in link.name]
        robot_contact = np.isin(a, robot_links) & np.isin(b, robot_links)
        self.max_robot_pen = max(self.max_robot_pen, float(ct["penetration"][robot_contact].max(initial=0)))
        table = self.task.manifest.get("table").base_link_idx
        robot_table = ((a == table) & np.isin(b, robot_links)) | ((b == table) & np.isin(a, robot_links))
        self.max_robot_table_pen = max(self.max_robot_table_pen, float(ct["penetration"][robot_table].max(initial=0)))
        if self.max_robot_table_pen > .001:
            raise RuntimeError(f"Robot/table penetration {self.max_robot_table_pen*1000:.3f} mm exceeds 1 mm")
        if self.max_robot_pen > .001:
            raise RuntimeError(f"Robot self penetration {self.max_robot_pen*1000:.3f} mm exceeds 1 mm")
        if pen > .001:
            raise RuntimeError(f"Puzzle penetration {pen*1000:.3f} mm exceeds 1 mm")
        if self.step_count % round(.05/self.dt) == 0:
            self.capture()

    def joint_segment(self, target, seconds, *, phase=None):
        if phase:
            self.phase = phase
            print(f"{self.step_count*self.dt:.2f}s {phase}", flush=True)
        start = self.q.copy()
        n = round(seconds/self.dt)
        for i in range(1, n+1):
            u = i/n
            self.q = (1-u)*start + u*np.asarray(target)
            self.step()

    def hold(self, seconds, *, phase="settle"):
        self.joint_segment(self.q.copy(), seconds, phase=phase)

    def cartesian(self, goals, seconds, *, phase):
        """Simultaneous pad-center targets in world coordinates, using fresh IK."""
        self.phase = phase
        print(f"{self.step_count*self.dt:.2f}s {phase}", flush=True)
        starts = {s: self.hand_pose(s) for s in goals}
        self.kin.q = self.q.copy()
        count = max(1, round(seconds/.05))
        for k in range(1, count+1):
            u = k/count
            u = u*u*(3-2*u)
            for side, (p, r) in goals.items():
                p0, r0 = starts[side]
                rot = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), r.as_quat()]))([u])[0]
                error = self.kin.solve(side, (1-u)*p0+u*p-self.mount, rot)
                if error[0] > .0005 or error[1] > .005:
                    raise RuntimeError(f"Unreachable {side} IK in {phase}: {error}")
            self.joint_segment(self.kin.q.copy(), seconds/count)

    def follow_old_fold(self):
        stop = next(p["frame"] for p in self.old_motion["phases"] if p["name"] == "双臂交接支撑")
        fps = self.old_motion["fps"]
        # Reparameterize each 12 Hz frame to an integral number of physics steps.
        for i, f in enumerate(self.old_motion["frames"][1:stop], 1):
            self.phase = f["stage"]
            duration = (round(i/fps/self.dt)-round((i-1)/fps/self.dt))*self.dt
            self.joint_segment(np.asarray(f["qpos"]), duration)
        self.hold(1., phase="settle_fold")

    def transform_pair(self, rotation, offset, seconds, *, center=None, phase="rotate_pair"):
        self.phase = phase
        print(f"{self.step_count*self.dt:.2f}s {phase}", flush=True)
        start = {s: self.hand_pose(s) for s in ("left", "right")}
        center = self.mount + [0., .05, .2] if center is None else np.asarray(center)
        self.kin.q = self.q.copy()
        count = max(1, round(seconds/.05))
        for k in range(1, count+1):
            u = k/count
            u = u*u*(3-2*u)
            rot = Rotation.from_rotvec(u*rotation.as_rotvec())
            for side, (p, r) in start.items():
                error = self.kin.solve(side, center+rot.apply(p-center)+u*np.asarray(offset)-self.mount, rot*r)
                if error[0] > .0005 or error[1] > .005:
                    raise RuntimeError(f"Unreachable {side} in {phase}: {error}")
            self.joint_segment(self.kin.q.copy(), seconds/count)

    def goal_state(self):
        from .independent_motion import IndependentWitness
        from .physical_plan import body_frame
        from topogym.tasks.cast_coil.robot_grasp import active_grasps
        ring = self.task.bodies["target_ring"]
        goal = IndependentWitness(self.task.assembly.template, float(self.cfg.task.scale)).goal(body_frame(self))
        constraints = active_grasps(self.solver, self.bodylinks)
        goal["ring_released"] = not any(ring.base_link_idx in pair for pair in constraints)
        ct = self.contacts()
        table = self.task.manifest.get("table").base_link_idx
        a, b = ct["link_a"], ct["link_b"]
        mask = ((a == table) & (b == ring.base_link_idx)) | ((b == table) & (a == ring.base_link_idx))
        goal["ring_table_contact_force_N"] = float(np.linalg.norm(ct["force"][mask], axis=-1).sum())
        goal["ring_speed_m_s"] = float(np.linalg.norm(array(ring.get_vel())))
        goal["ring_angular_speed_rad_s"] = float(np.linalg.norm(array(ring.get_ang())))
        goal["passed"] = bool(goal["separation_m"] > .02 and goal["ring_released"]
            and goal["ring_table_contact_force_N"] > .01 and goal["ring_speed_m_s"] < .01
            and goal["ring_angular_speed_rad_s"] < .2)
        return goal

    def finish(self, *, success=False, failure=None):
        self.trace.close()
        goal = self.goal_state()
        qualified = bool(success and goal["passed"] and failure is None and not self.checkpoint_start)
        result = dict(complete=failure is None, task_success=qualified, goal=goal, failure=failure,
            checkpoint_start=self.checkpoint_start, counts_as_complete_robotics_demo=False,
            classification="physical_manipulation_with_pregrasp_assistance", physics_steps=self.step_count,
            simulated_seconds=self.step_count*self.dt, dt=self.dt, substeps=int(self.cfg.env.sim.substeps),
            physical_frame_count=self.frame_count, physical_frame_fps=20, physical_states_sha256=sha(self.output/"physical_states.jsonl"),
            source_motion_sha256=sha(self.output/"source_motion.json"), template_sha256=sha(self.output/"input_template.json"),
            gravity_m_s2=[0, 0, -9.81], pose_writes_after_reset=False, chain_assistance=False,
            puzzle_body_dofs={n: b.n_dofs for n, b in self.task.bodies.items()},
            ring_initial_assistance=any(n == "target_ring" for _, n in self.initial_grasps),
            initial_grasps=self.initial_grasps, ring_initial_height_m=self.initial_ring_z,
            ring_downward_displacement_m=self.initial_ring_z-self.body_pose("target_ring")[0][2],
            maximum_puzzle_penetration_m=self.max_pen, maximum_nonfinger_penetration_m=self.max_nonfinger_pen,
            maximum_robot_self_penetration_m=self.max_robot_pen,
            maximum_robot_table_penetration_m=self.max_robot_table_pen,
            maximum_arm_tracking_error_rad=self.max_tracking_error,
            events=self.events, body_link_indices={n:b.base_link_idx for n,b in self.task.bodies.items()})
        if self.instance is not None:
            result["instance_id"] = self.instance["instance_id"]
            result["instance_sha256"] = sha(self.output/"instance.json")
        (self.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        return result

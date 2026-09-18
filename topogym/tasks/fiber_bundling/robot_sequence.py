"""Experimental Panda execution on the fixed-terminal cable; all strands stay passive.

Only robot motor targets are commanded after reset. Optional grasp assistance
is a native weld enabled after simultaneous contact of both fingers with the
same working-trunk link; it never writes a cable pose or moves the terminal.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import shape_in_root_frame
from .scene import FiberSceneBuilder, as_numpy
from .sequential import local_metrics
from .validation import pair_clearances
from .anchored_geometry import AnchoredLayout
from .anchored_verifier import CONTRACT_REVISION


def smooth(t):
    return 10*t**3-15*t**4+6*t**5


def bundle_fit(paths, layout, margin=.0003, ring_center=None):
    """Current finite-radius projection; earlier shapes are never a constraint.

    Preparation uses the cable's local frame. Before feeding, use the actual
    fixed ring axis, so cable tilt and centering errors cannot hide in that frame.
    Forward tangents are diagnostics, not an extra task acceptance condition.
    """
    local, radii, forward = local_metrics(paths, layout)
    if ring_center is not None:
        radii = np.linalg.norm(np.asarray(paths)[:, :, 1:]-np.asarray(ring_center)[1:], axis=-1).max(axis=1)+layout.fiber_radius_m
    ready = np.isfinite(radii) & (radii < layout.minimum_aperture_radius-margin)
    return dict(all_fit=bool(ready.all()), ready=ready.tolist(), envelope_radii_m=radii.tolist(),
                forward=forward.tolist(), aperture_radius_m=layout.minimum_aperture_radius,
                planning_margin_m=margin, frame="fixed_ring" if ring_center is not None else "cable_root")


def grasp_health(finger_ids, touching_ids, half_gap, previous_loss_time, dt,
                 max_half_gap, max_loss_time):
    """Require current bilateral contact; a weld is never evidence of a grasp."""
    loss_time = 0. if set(finger_ids).issubset(touching_ids) else previous_loss_time+dt
    if not np.isfinite(half_gap).all() or float(np.max(half_gap)) > max_half_gap:
        return loss_time, "Grasp lost: gripper opened while holding; refusing support by weld alone"
    if loss_time > max_loss_time+1e-12:
        return loss_time, "Grasp lost: bilateral finger contact absent for more than 100 ms"
    return loss_time, None


def touching_grasp_fingers(link_a, link_b, allowed_jacket_links, finger_ids):
    """Current native pairs only; never accumulate opposite contacts over time."""
    a, b = np.asarray(link_a), np.asarray(link_b)
    touched = set(b[np.isin(a, list(allowed_jacket_links))].tolist())
    touched.update(a[np.isin(b, list(allowed_jacket_links))].tolist())
    return touched.intersection(finger_ids)


class RobotSequence:
    def __init__(self, args):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.utils.franka import initialize_franka_controller

        self.args, self.output = args, args.output
        self.output.mkdir(parents=True, exist_ok=True)
        gate = json.loads(args.stability.read_text())
        if not gate["stability_passed"]:
            raise RuntimeError("Anchored stability gate has not passed")
        if gate.get("variant") != "anchored_terminal_v2":
            raise RuntimeError("A free-cable stability gate cannot qualify the anchored task")
        from .run_config import load_run_config
        cfg = load_run_config(getattr(args, "config", None))
        if args.order is None:
            args.order = list(range(int(cfg.task.geometry.fiber_count)))
        if any(i < 0 or i >= int(cfg.task.geometry.fiber_count) for i in args.order):
            raise ValueError("Selected strand index is outside the configured cable")
        from .ring_mount import require_fixture_evidence
        require_fixture_evidence(cfg.task, gate)
        anchor = asdict(AnchoredLayout.from_task_config(cfg.task))
        if gate.get("anchor") != json.loads(json.dumps(anchor)):
            raise RuntimeError("Stability evidence must explicitly match the current cradle/ring layout")
        contact_model = str(cfg.task.get("contact_model", "genesis_default"))
        precision = str(cfg.env.genesis.get("precision", "32"))
        if gate.get("precision", "32") != precision:
            raise RuntimeError("Stability evidence must match the numerical precision")
        from .numerics import require_solver_evidence
        constraint_solver=require_solver_evidence(cfg.task,gate)
        if gate.get("contact_model", "genesis_default") != contact_model:
            raise RuntimeError("Stability evidence must match the capsule contact implementation")
        cfg.env.cameras = {}
        cfg.env.renderer.type = "rasterizer"
        cfg.env.genesis.backend = args.backend
        cfg.env.sim.dt = args.dt
        OmegaConf.save(cfg, self.output/"config.yaml", resolve=True)
        self.spec = dict(variant=str(cfg.task.variant), success_contract_revision=CONTRACT_REVISION,
            backend=args.backend, dt=args.dt, substeps=int(cfg.env.sim.substeps),
            precision=precision, constraint_solver=constraint_solver,
            genesis_performance_mode=args.performance_mode, contact_model=contact_model,
            strategy="real_robot_bilateral_grasp_outer_rim_prepare_each_wire_then_axial_feed",
            grasp_link=getattr(args, "grasp_link", "trunk_05"), grasp_point_local_m=[args.grip_x, 0., 0.],
            grasp_y_angle_deg=args.grasp_angle, grasp_assist="native weld after simultaneous bilateral contact" if args.assist else "none",
            regrasp_back=args.regrasp_back, motion_time_scale=args.motion_scale, selection=args.selection,
            neighbor_shape_policy="diagnostic_only_final_current_bundle_fit",
            preparation_passes=args.preparation_passes, anchor=anchor,
            ring_fixture=gate.get("ring_fixture"),
            fiber_count=int(cfg.task.geometry.fiber_count),
            rear_grasp_link=args.rear_link, rear_grasp_point_local_m=[args.rear_x, 0., 0.],
            park_clearance_m=args.park_clearance, final_jacket_depth_m=args.feed_depth,
            tip_feedback_gain_s_inv=4.,
            max_grasp_half_gap_m=float(cfg.task.geometry.trunk_radius_m)+.003,
            max_bilateral_contact_loss_s=.10,
            grasp_health_scope="current bilateral contact on selected or immediately adjacent working-jacket segments",
            preparation_margin_m=.0003,
            fine_contact_penetration_limit_m=.0003, robot_fixture_penetration_limit_m=.0003,
            coarse_contact_penetration_limit_m=.0007, root_error_limit_m=1e-5,
            per_step_point_displacement_limit_m=.0012, order=args.order,
            press_radius_m=args.press_radius, stability_gate=str(args.stability),
            stability_gate_sha256=hashlib.sha256(args.stability.read_bytes()).hexdigest(),
            cable_pose_writes=0, fine_force_commands=0, terminal_pose_writes=0, ring_pose_writes=0,
            robot_pose_writes_after_home_reset=0)
        (self.output/"plan.json").write_text(json.dumps(self.spec, indent=2)+"\n")
        source = self.output/"source"
        source.mkdir(exist_ok=True)
        for name in ("robot_sequence.py", "scene.py", "ring_mount.py", "run_config.py", "geometry.py",
                     "anchored_geometry.py", "sequential.py", "validation.py", "anchored_verifier.py",
                     "contact_guard.py", "contact_precision.py", "numerics.py"):
            (source/name).write_bytes(Path(__file__).with_name(name).read_bytes())
        gs.init(backend=gs.cuda if args.backend == "cuda" else gs.cpu, logging_level="warning",
                seed=int(cfg.task.geometry.seed), performance_mode=args.performance_mode, precision=precision)
        self.task = FiberSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=self.output/"assets")
        if hashlib.sha256((self.output/"assets/bundle.xml").read_bytes()).hexdigest() != gate["asset_sha256"]:
            raise RuntimeError("Current cable differs from the anchored stability test asset")
        self.c = initialize_franka_controller(scene=self.task.scene, manifest=self.task.manifest,
                                             robot_cfg=cfg.robot_control, settle_steps=0)
        self.robot, self.cable = self.c.robot, self.task.bundle
        self.solver = self.task.scene.sim.rigid_solver
        self.grasp_link = self.cable.get_link(self.spec["grasp_link"])
        self.robot_ids = [link.idx for link in self.robot.links]
        self.fine_ids = list(self.task.contact_guard.fine_links)
        self.cable_ids = [link.idx for link in self.cable.links if link.name != "fixed_terminal"]
        self.fingers = {self.robot.get_link(n).idx for n in ("left_finger", "right_finger")}
        working = self.task.asset_report["graspable_links"]
        self.grasp_neighborhood = {name: {self.cable.get_link(other).idx for other in working
            if abs(int(other.split("_")[1])-int(name.split("_")[1])) <= 1} for name in working}
        self.frames, self.events, self.phase_metrics = [], [], []
        self.commands = []
        self.step_count, self.phase, self.target = 0, "initial", -1
        self.active_grasp = False
        self.holding = False
        self.grasp_loss_time = 0.
        self.contact_counts = {}
        self.grasp_evidence = None
        self.grasp_events = []
        self.shape_references, self.shape_changes = {}, {}
        self.final_fit_checks = []
        self.maxima = dict(fine_penetration_m=0., coarse_penetration_m=0., robot_fixture_penetration_m=0.,
                          fine_pair_penetration_m=0., root_error_m=0., fine_length_error_m=0.,
                          point_displacement_per_step_m=0., hand_tracking_error_m=0., anchor_error_m=0.)
        self.before = self.task.state()
        self.previous = self.before["fibers_m"].copy()
        self.last_status = self.before
        self.last_print = time.monotonic()
        self.record()

    def record(self):
        s = self.last_status
        self.frames.append(dict(time_s=self.step_count*self.args.dt, phase=self.phase, target=self.target,
            fibers=s["fibers_m"].copy(), coarse=s["coarse_m"].copy(),
            cable_qpos=as_numpy(self.cable.get_qpos()).copy(), robot_qpos=as_numpy(self.robot.get_qpos()).copy(),
            cable_qvel=as_numpy(self.cable.get_dofs_velocity()).copy(),
            robot_qvel=as_numpy(self.robot.get_dofs_velocity()).copy(),
            grasp_active=self.active_grasp, failed=s["failed"], success=s["success"],
            gripper_half_gap_m=self.c.gripper_qpos().copy(),
            prepared_shape_change_m=max(self.shape_changes.values(), default=0.)))

    def save(self):
        np.savez_compressed(self.output/"trajectory.npz", **{
            key: np.asarray([frame[key] for frame in self.frames]) for key in self.frames[0]})
        (self.output/"preparation_events.json").write_text(json.dumps(self.events, indent=2)+"\n")
        (self.output/"phase_metrics.json").write_text(json.dumps(self.phase_metrics, indent=2)+"\n")
        (self.output/"robot_commands.json").write_text(json.dumps(self.commands, indent=2)+"\n")

    def step(self):
        self.task.scene.step(update_visualizer=False)
        self.step_count += 1
        s = self.task.last_step_state
        self.last_status = s
        contacts = self.solver.collider.get_contacts()
        a, b, pen = [as_numpy(contacts[key]) for key in ("link_a", "link_b", "penetration")]
        fine = np.isin(a, self.fine_ids) | np.isin(b, self.fine_ids)
        cable = np.isin(a, self.cable_ids) | np.isin(b, self.cable_ids)
        robot_a, robot_b = np.isin(a, self.robot_ids), np.isin(b, self.robot_ids)
        ring = (a == self.task.ring.base_link_idx) | (b == self.task.ring.base_link_idx)
        fine_names = self.task.contact_guard.fine_links
        contacted = set(int(fine_names[int(link)].split("_")[1])
                        for link in np.r_[a[ring & fine], b[ring & fine]] if int(link) in fine_names)
        counts = self.contact_counts.setdefault(self.phase, {})
        for i in contacted:
            counts[i] = counts.get(i, 0)+1
        # The robot mount on the table is an intentional fixed contact.
        fixture = ((robot_a & ~robot_b) | (robot_b & ~robot_a)) & ~cable
        fixture &= (a != self.robot.base_link_idx) & (b != self.robot.base_link_idx)
        values = dict(fine_penetration_m=float(pen[fine].max(initial=0.)),
            coarse_penetration_m=float(pen[cable & ~fine].max(initial=0.)),
            robot_fixture_penetration_m=float(pen[fixture].max(initial=0.)),
            fine_pair_penetration_m=max(0., -float(pair_clearances(s["fibers_m"], self.task.layout.fiber_radius_m).min())),
            root_error_m=s["max_root_error_m"], anchor_error_m=s["threading"]["max_attachment_error_m"],
            fine_length_error_m=float(np.abs(np.linalg.norm(np.diff(s["fibers_m"], axis=1), axis=-1)-
                                           self.task.layout.fiber_length_m/self.task.layout.fiber_segments).max()),
            point_displacement_per_step_m=float(np.linalg.norm(s["fibers_m"]-self.previous, axis=-1).max()))
        self.previous = s["fibers_m"].copy()
        for key, value in values.items():
            self.maxima[key] = max(self.maxima[key], value)
        local = shape_in_root_frame(s["fibers_m"])
        for i, ref in self.shape_references.items():
            self.shape_changes[i] = max(self.shape_changes[i], float(np.linalg.norm(local[i]-ref, axis=-1).max()))
        if self.step_count % max(1, round(.04/self.args.dt)) == 0:
            self.record()
        problem = None
        grasp_problem = None
        if self.holding:
            touched = touching_grasp_fingers(a, b, self.grasp_neighborhood[self.grasp_link.name], self.fingers)
            self.grasp_loss_time, grasp_problem = grasp_health(
                self.fingers, touched, self.c.gripper_qpos(), self.grasp_loss_time, self.args.dt,
                self.spec["max_grasp_half_gap_m"], self.spec["max_bilateral_contact_loss_s"])
        if s["failed"]:
            problem = f"Task rejected: {s['invalid_reasons']}"
        elif grasp_problem:
            problem = grasp_problem
        elif not np.isfinite(np.r_[s["fibers_m"].ravel(), s["coarse_m"].ravel()]).all():
            problem = "Non-finite cable state"
        elif max(values["fine_penetration_m"], values["fine_pair_penetration_m"]) > self.spec["fine_contact_penetration_limit_m"]:
            problem = f"Fine contact penetration exceeded: {values}"
        elif values["coarse_penetration_m"] > self.spec["coarse_contact_penetration_limit_m"]:
            problem = f"Coarse contact penetration exceeded: {values}"
        elif values["robot_fixture_penetration_m"] > self.spec["robot_fixture_penetration_limit_m"]:
            problem = f"Robot/fixture penetration exceeded: {values}"
        elif max(values["root_error_m"], values["fine_length_error_m"]) > self.spec["root_error_limit_m"]:
            problem = f"Geometric constraint error: {values}"
        elif values["point_displacement_per_step_m"] > self.spec["per_step_point_displacement_limit_m"]:
            problem = f"Motion per step exceeded: {values}"
        if time.monotonic()-self.last_print > 25:
            print(json.dumps(dict(phase=self.phase, time_s=self.step_count*self.args.dt, maxima=self.maxima)), flush=True)
            self.last_print = time.monotonic()
        if problem:
            names = {link.idx: link.name for link in self.solver.links}
            self.failure_contact_pairs = [dict(a=names.get(int(aa), str(int(aa))),
                b=names.get(int(bb), str(int(bb))), penetration_m=float(pp))
                for aa, bb, pp in zip(a, b, pen) if int(aa) in self.robot_ids or int(bb) in self.robot_ids or pp > .0001]
            if grasp_problem and self.active_grasp:
                self.solver.delete_weld_constraint(self.c.ee_link.idx, self.grasp_link.idx)
                self.active_grasp = False
                self.holding = False
            self.record()
            raise RuntimeError(problem)

    def finish_phase(self):
        local, radii, forward = local_metrics(self.last_status["fibers_m"], self.task.layout)
        row = dict(phase=self.phase, time_s=self.step_count*self.args.dt,
                   envelope_radii_m=radii.tolist(), forward=forward.tolist(),
                   hand_pos=self.c.hand_pos().tolist(), grasp_center=self.c.grasp_center_pos().tolist(),
                   gripper_half_gap_m=self.c.gripper_qpos().tolist(), maxima=dict(self.maxima))
        self.phase_metrics.append(row)
        self.record()
        self.save()
        print(json.dumps(row), flush=True)

    def hold(self, name, seconds):
        self.phase = name
        for _ in range(round(seconds/self.args.dt)):
            self.step()
        self.finish_phase()

    def command_hand(self, pos, rot):
        q, error = self.robot.inverse_kinematics(link=self.c.ee_link, pos=pos,
            quat=rot.as_quat()[[3, 0, 1, 2]], init_qpos=self.robot.get_qpos(),
            dofs_idx_local=self.c.arm_dofs, max_samples=1, max_solver_iters=150,
            pos_tol=1e-5, rot_tol=1e-4, return_error=True)
        e = as_numpy(error)
        if np.linalg.norm(e[:3]) > .001 or np.linalg.norm(e[3:]) > .01:
            raise RuntimeError(f"Unreachable hand target in {self.phase}: {e.tolist()}, pos={pos.tolist()}")
        if np.max(np.abs(as_numpy(q)[:7]-self.c.arm_qpos())) > .25:
            raise RuntimeError("IK branch discontinuity")
        self.robot.control_dofs_position(q[:7], self.c.arm_dofs)
        self.commands.append(dict(time_s=self.step_count*self.args.dt, phase=self.phase,
            arm_joint_target=as_numpy(q)[:7].tolist(), hand_target_m=np.asarray(pos).tolist(),
            hand_target_quat_wxyz=rot.as_quat()[[3, 0, 1, 2]].tolist(),
            gripper_half_gap_target_m=self.c.current_gripper_qpos))

    def move_hand(self, name, pos, rot, seconds):
        self.phase = name
        p0 = self.c.hand_pos()
        r0 = Rotation.from_quat(self.c.hand_quat()[[1, 2, 3, 0]])
        delta = (rot*r0.inv()).as_rotvec()
        count = max(1, round(seconds/.01))
        for k in range(count):
            t = smooth((k+1)/count)
            goal = p0+(pos-p0)*t
            self.command_hand(goal, Rotation.from_rotvec(t*delta)*r0)
            for _ in range(round(.01/self.args.dt)):
                self.step()
            self.maxima["hand_tracking_error_m"] = max(self.maxima["hand_tracking_error_m"],
                                                       float(np.linalg.norm(self.c.hand_pos()-goal)))
        self.finish_phase()

    def close_and_attach(self, name):
        self.phase = name
        self.c.set_gripper(.009, steps=0)
        evidence = None
        for _ in range(round(3.0/self.args.dt)):
            self.step()
            ct = self.cable.get_contacts(with_entity=self.robot)
            a, b = as_numpy(ct["link_a"]), as_numpy(ct["link_b"])
            touched = set(b[a == self.grasp_link.idx].tolist()) | set(a[b == self.grasp_link.idx].tolist())
            if self.fingers.issubset(touched):
                evidence = dict(time_s=self.step_count*self.args.dt,
                    target=self.grasp_link.name, touching_finger_ids=sorted(self.fingers),
                    gripper_half_gap_m=self.c.gripper_qpos().tolist(),
                    measured_grasp_center_m=self.c.grasp_center_pos().tolist(),
                    native_contact_pairs=np.column_stack([a, b]).tolist())
                break
        if evidence is None:
            raise RuntimeError(f"Simultaneous bilateral contact on {self.grasp_link.name} was not established")
        self.grasp_evidence = evidence
        self.grasp_events.append(evidence)
        self.holding = True
        self.grasp_loss_time = 0.
        if self.args.assist:
            self.solver.add_weld_constraint(self.c.ee_link.idx, self.grasp_link.idx)
            self.active_grasp = True
        self.finish_phase()
        self.hold("grasp_hold", .4)

    def calibrate_grasp(self, offset):
        actual_p = as_numpy(self.grasp_link.get_pos())
        actual_r = Rotation.from_quat(as_numpy(self.grasp_link.get_quat())[[1, 2, 3, 0]])
        self.relative_hand_p = actual_r.inv().apply(self.c.hand_pos()-actual_p)
        self.relative_hand_r = actual_r.inv()*Rotation.from_quat(self.c.hand_quat()[[1, 2, 3, 0]])
        self.reference_r = actual_r
        self.reference_p = actual_p.copy()-offset
        self.reference_root = self.last_status["roots_m"].mean(axis=0)-offset
        self.offset, self.roll = np.asarray(offset).copy(), 0.

    def grasp(self):
        self.hold("initial_hold", .4)
        r = Rotation.from_euler("y", self.args.grasp_angle, degrees=True)
        link_r = Rotation.from_quat(as_numpy(self.grasp_link.get_quat())[[1, 2, 3, 0]])
        center = as_numpy(self.grasp_link.get_pos())+link_r.apply(self.spec["grasp_point_local_m"])
        current_r = Rotation.from_quat(self.c.hand_quat()[[1, 2, 3, 0]])
        open_offset = current_r.inv().apply(self.c.grasp_center_pos()-self.c.hand_pos())
        hand = center-r.apply(open_offset)
        self.move_hand("approach_above_cable", hand-r.apply([0, 0, .10]), r, 2.0)
        self.move_hand("lower_open_gripper", hand, r, 2.0)
        self.close_and_attach("close_on_working_jacket")
        self.calibrate_grasp(np.zeros(3))
        if self.args.regrasp_back:
            self.move_cable("lift_for_regrasp", [0., 0., .065], seconds=2.)
            self.hold("settle_before_regrasp", 1.)
            if self.active_grasp:
                self.solver.delete_weld_constraint(self.c.ee_link.idx, self.grasp_link.idx)
                self.active_grasp = False
            self.holding = False
            self.c.set_gripper(.023, steps=0)
            self.hold("open_for_regrasp", 1.5)
            self.grasp_link = self.cable.get_link(self.args.rear_link)
            actual_r = Rotation.from_quat(as_numpy(self.grasp_link.get_quat())[[1, 2, 3, 0]])
            center = as_numpy(self.grasp_link.get_pos())+actual_r.apply([self.args.rear_x, 0, 0])
            hand_r = Rotation.from_quat(self.c.hand_quat()[[1, 2, 3, 0]])
            open_offset = hand_r.inv().apply(self.c.grasp_center_pos()-self.c.hand_pos())
            self.move_hand("shift_grasp_to_rear_jacket", center-hand_r.apply(open_offset), hand_r, 2.5)
            self.close_and_attach("close_on_rear_jacket")
            self.calibrate_grasp(np.array([0., 0., .065]))

    def move_cable(self, name, offset=None, roll=None, seconds=1., track_tip=False, tangent=None,
                   radial_direction=None, radial_target=None):
        self.phase = name
        start, end = self.offset.copy(), np.asarray(self.offset if offset is None else offset)
        a0, a1 = self.roll, self.roll if roll is None else roll
        radial_start = None if radial_direction is None else float(
            (self.task.ring_center[1:]-self.last_status["roots_m"].mean(axis=0)[1:])@radial_direction)
        count = max(1, round(seconds*self.args.motion_scale/.01))
        for k in range(count):
            blend = smooth((k+1)/count)
            old = self.offset.copy()
            self.offset = start+(end-start)*blend
            if track_tip:
                tip = self.last_status["fibers_m"][self.target, -1]
                gain = self.spec["tip_feedback_gain_s_inv"]*.01
                self.offset[0] = old[0]+np.clip(gain*(self.task.ring_center[0]-tip[0]), -.025*.01, .025*.01)
                if tangent is None:
                    self.offset[2] = old[2]+np.clip(gain*(self.task.ring_center[2]-tip[2]), -.025*.01, .025*.01)
                else:
                    correction = np.clip(gain*((self.task.ring_center[1:]-tip[1:])@tangent), -.025*.01, .025*.01)
                    self.offset[1:] += tangent*((old[1:]-self.offset[1:])@tangent+correction)
                if radial_direction is not None:
                    actual = float((self.task.ring_center[1:]-self.last_status["roots_m"].mean(axis=0)[1:])@radial_direction)
                    desired = radial_start+(radial_target-radial_start)*blend
                    correction = np.clip(gain*(actual-desired), -.015*.01, .015*.01)
                    self.offset[1:] += radial_direction*((old[1:]-self.offset[1:])@radial_direction+correction)
            self.roll = a0+(a1-a0)*blend
            rot = Rotation.from_euler("x", self.roll)*self.reference_r
            pos = self.reference_p+self.offset
            self.command_hand(pos+rot.apply(self.relative_hand_p), rot*self.relative_hand_r)
            for _ in range(round(.01/self.args.dt)):
                self.step()
        self.finish_phase()

    def prepare(self, index):
        self.target = index
        before = shape_in_root_frame(self.last_status["fibers_m"])
        if self.args.selection == "orbit":
            self.prepare_orbit(index, before)
            return
        # Rearward motion while still in the cradle brings the gripper linkage
        # into the support. Lift first, then retreat and move sideways.
        self.move_cable(f"wire_{index}_lift", [*self.offset[:2], .08], seconds=2.)
        self.hold(f"wire_{index}_lift_hold", .6)
        self.move_cable(f"wire_{index}_park", [-.030, *self.offset[1:]], seconds=1.5)
        direction = before[index, -1]-before[index, 0]
        roll = -np.arctan2(direction[2], direction[1])
        roll += 2*np.pi*round((self.roll-roll)/(2*np.pi))
        self.move_cable(f"wire_{index}_select", [-.030, -.060, .08], roll=roll, seconds=max(2., abs(roll-self.roll)/.4))
        tip = self.last_status["fibers_m"][index, -1]
        x = self.offset[0]+self.task.ring_center[0]-tip[0]
        z = self.offset[2]+self.task.ring_center[2]-tip[2]
        self.move_cable(f"wire_{index}_approach", [x, -.060, z], seconds=2.5)
        self.move_cable(f"wire_{index}_press", [x, -self.args.press_radius, z], seconds=2., track_tip=True)
        self.hold(f"wire_{index}_settle", .6)
        self.move_cable(f"wire_{index}_release", [self.offset[0], -.060, self.offset[2]], seconds=1.)
        self.hold(f"wire_{index}_inspect", .6)
        self.record_preparation(index, before)

    def prepare_orbit(self, index, before):
        # Select each wire by translating around the fixed rim. Keeping the
        # jacket orientation constant avoids repeatedly rolling prepared wires.
        park = self.task.ring_center[0]-self.args.park_clearance-self.reference_root[0]
        self.move_cable(f"wire_{index}_park", [park, *self.offset[1:]], seconds=1.)
        self.hold(f"wire_{index}_park_hold", .6)
        roots = self.last_status["roots_m"].mean(axis=0)
        direction = self.last_status["fibers_m"][index, -1, 1:]-roots[1:]
        direction /= np.linalg.norm(direction)
        tangent = np.array([-direction[1], direction[0]])
        lateral = self.task.ring_center[1:]-self.reference_root[1:]-.060*direction
        if not self.events:
            self.move_cable(f"wire_{index}_clear_cradle", [park, lateral[0], self.offset[2]], seconds=1.5)
        self.move_cable(f"wire_{index}_select", [park, *lateral], seconds=2.)
        self.hold(f"wire_{index}_select_hold", .6)
        tip = self.last_status["fibers_m"][index, -1]
        x = self.offset[0]+self.task.ring_center[0]-tip[0]
        lateral += tangent*((self.task.ring_center[1:]-tip[1:])@tangent)
        self.move_cable(f"wire_{index}_approach", [x, *lateral], seconds=1.5)
        press = lateral+(.060-self.args.press_radius)*direction
        self.move_cable(f"wire_{index}_press", [x, *press], seconds=2., track_tip=True, tangent=tangent,
                        radial_direction=direction, radial_target=self.args.press_radius)
        self.move_cable(f"wire_{index}_settle", seconds=1., track_tip=True, tangent=tangent,
                        radial_direction=direction, radial_target=self.args.press_radius)
        release = self.offset[1:]-(.060-self.args.press_radius)*direction
        self.move_cable(f"wire_{index}_release", [self.offset[0], *release], seconds=1.5)
        self.hold(f"wire_{index}_inspect", 1.)
        self.record_preparation(index, before)

    def record_preparation(self, index, before):
        local = shape_in_root_frame(self.last_status["fibers_m"])
        fit = bundle_fit(self.last_status["fibers_m"], self.task.layout, self.spec["preparation_margin_m"])
        ready = fit["ready"][index]
        changes = np.linalg.norm(local-before, axis=-1).max(axis=1)
        self.events.append(dict(target=index, prepared=ready, simulation_time=self.step_count*self.args.dt,
            envelope_radius_m=fit["envelope_radii_m"][index], other_shape_changes_m=changes.tolist(),
            current_bundle_fit=fit, shape_changes_diagnostic_only=True))
        # Keep the first successful shape as a diagnostic reference only. A
        # wire may change, become unready, and be prepared again later.
        if ready and index not in self.shape_references:
            self.shape_references[index], self.shape_changes[index] = local[index].copy(), 0.
        self.save()

    def align_and_check_bundle(self):
        self.target = -1
        park = self.task.ring_center[0]-self.args.park_clearance-self.reference_root[0]
        self.move_cable("bundle_retreat", [park, *self.offset[1:]], seconds=1.)
        self.move_cable("bundle_unroll", roll=0., seconds=max(1., abs(self.roll)/.6))
        roots = self.last_status["roots_m"].mean(axis=0)
        lateral = self.offset[1:]+self.task.ring_center[1:]-roots[1:]
        self.move_cable("bundle_align", [park, *lateral], seconds=1.5)
        self.hold("before_final_feed", .6)
        fit = bundle_fit(self.last_status["fibers_m"], self.task.layout,
                         self.spec["preparation_margin_m"], self.task.ring_center)
        self.final_fit_checks.append(dict(time_s=self.step_count*self.args.dt, **fit))
        return fit

    def run(self):
        failure = None
        try:
            self.grasp()
            if self.args.stage == "one":
                self.prepare(self.args.order[0])
            if self.args.stage == "full":
                pending = list(self.args.order)
                for _ in range(self.args.preparation_passes):
                    for i in pending:
                        self.prepare(i)
                    fit = self.align_and_check_bundle()
                    if fit["all_fit"]:
                        break
                    pending = [i for i in self.args.order if not fit["ready"][i]]
                if not fit["all_fit"]:
                    raise RuntimeError(f"Preparation budget exhausted; current bundle does not fit ring: {fit}")
                root_x = self.last_status["roots_m"].mean(axis=0)[0]
                feed = self.offset[0]+self.task.ring_center[0]+self.task.layout.ring_tube_radius_m+self.args.feed_depth-root_x
                self.move_cable("final_axial_feed", [feed, *self.offset[1:]], seconds=5.)
                self.hold("final_hold", 2.)
        except RuntimeError as error:
            failure = str(error)
            print("ATTEMPT STOPPED: "+failure, flush=True)
        self.record()
        self.save()
        return self.finish_report(failure)

    def finish_report(self, failure):
        report = dict(scope="anchored_real_robot_sequence", variant="anchored_terminal_v2", stage=self.args.stage,
            passed=failure is None and (self.last_status["success"] if self.args.stage == "full" else
                self.events[-1]["prepared"] if self.args.stage == "one" and self.events else self.args.stage == "grasp"),
            full_threading_verified=failure is None and self.args.stage == "full" and self.last_status["success"],
            robot_grasp_executed=self.grasp_evidence is not None, grasp_evidence=self.grasp_evidence,
            grasp_events=self.grasp_events,
            ring_contact_steps_by_strand=self.contact_counts, final_grasp_link=self.grasp_link.name,
            simulated_seconds=self.step_count*self.args.dt, failure=failure, stopped_phase=self.phase,
            contact_rule=self.last_status["contact_rule"], threading=self.last_status["threading"],
            maxima=self.maxima, preparation_events=self.events, prepared_shape_changes_m=self.shape_changes,
            final_fit_checks=self.final_fit_checks,
            failure_contact_pairs=getattr(self, "failure_contact_pairs", []),
            plan=self.spec, final_grasp_constraint_active=self.active_grasp,
            assets_sha256=hashlib.sha256((self.output/"assets/bundle.xml").read_bytes()).hexdigest())
        (self.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, indent=2), flush=True)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Exact generated variant config; defaults to the historical scene")
    parser.add_argument("--stability", type=Path, default=Path("runs/environment-solvability/fiber_bundling/ik_stability/result.json"))
    parser.add_argument("--stage", choices=("grasp", "one", "full"), default="full")
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--performance-mode", action="store_true", help="Use Genesis static fields; recorded in plan")
    parser.add_argument("--grasp-angle", type=float, default=135.)
    parser.add_argument("--grasp-link", choices=tuple(f"trunk_{i:02d}" for i in range(6)), default="trunk_05")
    parser.add_argument("--grip-x", type=float, default=.015)
    parser.add_argument("--press-radius", type=float, default=.0353)
    parser.add_argument("--order", type=int, nargs="+", default=None)
    parser.add_argument("--assist", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--regrasp-back", action="store_true")
    parser.add_argument("--selection", choices=("roll", "orbit"), default="roll")
    parser.add_argument("--motion-scale", type=float, default=1.)
    parser.add_argument("--preparation-passes", type=int, default=2,
                        help="Revisit currently oversized wires after checking the whole bundle")
    parser.add_argument("--rear-link", choices=("trunk_03", "trunk_04"), default="trunk_04")
    parser.add_argument("--rear-x", type=float, default=.005)
    parser.add_argument("--park-clearance", type=float, default=.088)
    parser.add_argument("--feed-depth", type=float, default=.034)
    args = parser.parse_args()
    from .run_config import load_run_config
    count = int(load_run_config(args.config).task.geometry.fiber_count)
    if args.order is None:
        args.order = list(range(count))
    if sorted(args.order) != list(range(count)) or args.dt not in (.002, .001):
        parser.error("Require each wire exactly once and a tested dt of 2 ms or 1 ms")
    if args.motion_scale <= 0 or not np.isfinite(args.motion_scale):
        parser.error("Motion scale must be finite and positive")
    if args.preparation_passes < 1:
        parser.error("At least one preparation pass is required")
    if not 0 <= args.grip_x <= .04 or not 0 <= args.rear_x <= .04:
        parser.error("Grasp points must lie on the selected 40 mm coarse segment")
    if not 0 < args.press_radius < .060:
        parser.error("Press radius must lie between zero and the 60 mm approach radius")
    if not .03 < args.feed_depth < .08 or not .04 < args.park_clearance < .15:
        parser.error("Require feed depth > 30 mm and a 40–150 mm ring approach clearance")
    if (args.output/"trajectory.npz").exists() or (args.output/"report.json").exists():
        parser.error("Use a new output directory to preserve previous evidence")
    if not RobotSequence(args).run()["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

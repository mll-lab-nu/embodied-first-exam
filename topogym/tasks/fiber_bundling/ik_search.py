"""Whole-bundle IK exploration with live contacts and the anchored task verifier.

Every trial starts from the actual reset and executes a real bilateral grasp.
Only arm/finger motors are commanded; fine strands have no actuators. No
per-strand schedule or pre-insertion all-straight requirement is imposed.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .robot_sequence import RobotSequence, bundle_fit, smooth
from .scene import as_numpy


class BundleIKTrial(RobotSequence):
    def __init__(self, args):
        super().__init__(args)
        self.spec.update(strategy=f"whole_bundle_{args.mode}_IK", wire_order_required=False,
                         pre_insertion_all_fit_required=False,
                         ik_seed="preceding joint target; measured pose for first command",
                         maximum_joint_command_step_rad=.15,
                         policy_parameters=dict(mode=args.mode, cycles=args.cycles,
                             orbit_radius_m=args.orbit_radius, tilt_deg=args.tilt,
                             entry_start_m=args.entry_start, entry_end_m=args.entry_end,
                             roll_span_deg=args.roll_span, feed_speed_m_s=args.feed_speed,
                             max_presses=args.max_presses, entry_envelope_m=args.entry_envelope))
        (self.output/"plan.json").write_text(json.dumps(self.spec, indent=2)+"\n")
        (self.output/"source/ik_search.py").write_bytes(Path(__file__).read_bytes())
        self.bundle_metrics = []
        self.last_ik_target = None
        self.turn_ik_audits = []

    def probe_root_move(self, goal, rotation, seconds):
        """Check an entire candidate IK turn without commanding any actuator.

        Keep the current integral correction fixed during this kinematic
        forecast. Execution still reruns IK and all physical contact guards.
        """
        actual = as_numpy(self.robot.get_qpos()).copy()
        seed = actual.copy()
        previous = self.c.arm_qpos() if self.last_ik_target is None else self.last_ik_target.copy()
        start, r0 = self.root_goal.copy(), self.root_rotation
        delta = (rotation*r0.inv()).as_rotvec()
        count = max(1, round(seconds/.01))
        maximum = 0.
        result = dict(passed=True, commands_checked=0, maximum_command_step_rad=0.)
        for k in range(count):
            t = smooth((k+1)/count)
            rot = Rotation.from_rotvec(t*delta)*r0
            link_goal = start+(np.asarray(goal)-start)*t+self.root_correction-rot.apply(self.head_from_grasp)
            seed[:7] = previous
            hand_r = rot*self.relative_hand_r
            q, error = self.robot.inverse_kinematics(link=self.c.ee_link,
                pos=link_goal+rot.apply(self.relative_hand_p),
                quat=hand_r.as_quat()[[3,0,1,2]], init_qpos=seed,
                dofs_idx_local=self.c.arm_dofs, max_samples=1, max_solver_iters=150,
                pos_tol=1e-5, rot_tol=1e-4, return_error=True)
            arm, error = as_numpy(q)[:7].copy(), as_numpy(error)
            jump = float(np.max(np.abs(arm-previous)))
            maximum = max(maximum, jump)
            result.update(commands_checked=k+1, maximum_command_step_rad=maximum)
            if (not np.isfinite(np.r_[arm,error]).all() or np.linalg.norm(error[:3]) > .001
                    or np.linalg.norm(error[3:]) > .01 or jump > self.spec["maximum_joint_command_step_rad"]):
                result.update(passed=False, rejected_fraction=(k+1)/count,
                              ik_error=error.tolist(), rejected_joint_target=arm.tolist())
                break
            previous = arm
        if not np.allclose(as_numpy(self.robot.get_qpos()), actual, atol=1e-7, rtol=0):
            raise RuntimeError("Kinematic preview unexpectedly changed the actual robot state")
        return result

    def command_hand(self, pos, rot):
        # Test continuity between successive IK solutions. Motor tracking lag
        # is not an IK branch jump; physical grasp/contact checks still apply.
        seed = as_numpy(self.robot.get_qpos()).copy()
        previous = self.c.arm_qpos() if self.last_ik_target is None else self.last_ik_target
        if self.last_ik_target is not None:
            seed[:7] = self.last_ik_target
        q, error = self.robot.inverse_kinematics(link=self.c.ee_link, pos=pos,
            quat=rot.as_quat()[[3, 0, 1, 2]], init_qpos=seed,
            dofs_idx_local=self.c.arm_dofs, max_samples=1, max_solver_iters=150,
            pos_tol=1e-5, rot_tol=1e-4, return_error=True)
        error, arm = as_numpy(error), as_numpy(q)[:7].copy()
        jump = float(np.max(np.abs(arm-previous)))
        if np.linalg.norm(error[:3]) > .001 or np.linalg.norm(error[3:]) > .01:
            raise RuntimeError(f"Unreachable IK pose in {self.phase}: {error.tolist()}")
        if jump > self.spec["maximum_joint_command_step_rad"]:
            raise RuntimeError(f"IK solution discontinuity in {self.phase}: {jump:.4f} rad between commands")
        self.robot.control_dofs_position(arm, self.c.arm_dofs)
        self.last_ik_target = arm
        self.commands.append(dict(time_s=self.step_count*self.args.dt, phase=self.phase,
            arm_joint_target=arm.tolist(), hand_target_m=np.asarray(pos).tolist(),
            hand_target_quat_wxyz=rot.as_quat()[[3, 0, 1, 2]].tolist(),
            gripper_half_gap_target_m=self.c.current_gripper_qpos,
            ik_joint_command_step_rad=jump, ik_error=error.tolist()))

    def finish_phase(self):
        super().finish_phase()
        if not hasattr(self, "bundle_metrics"):
            return
        s, center = self.last_status, self.task.ring_center
        fibers = s["fibers_m"]
        radial = np.linalg.norm(fibers[:, -1, 1:]-center[1:], axis=-1)+self.task.layout.fiber_radius_m
        row = dict(phase=self.phase, time_s=self.step_count*self.args.dt,
            root_center_m=s["roots_m"].mean(axis=0).tolist(),
            tip_x_relative_to_ring_m=(fibers[:, -1, 0]-center[0]).tolist(),
            tips_beyond_ring=int(np.sum(fibers[:, -1, 0]-self.task.layout.fiber_radius_m > center[0])),
            tip_aperture_radii_m=radial.tolist(),
            tips_inside_projection=int(np.sum(radial < self.task.layout.minimum_aperture_radius)),
            local_fit=bundle_fit(fibers, self.task.layout),
            actual_ring_fit=bundle_fit(fibers, self.task.layout, ring_center=center))
        self.bundle_metrics.append(row)
        (self.output/"bundle_metrics.json").write_text(json.dumps(self.bundle_metrics, indent=2)+"\n")
        print("BUNDLE "+json.dumps(row), flush=True)

    def initialize_root_control(self):
        self.root_goal = self.last_status["roots_m"].mean(axis=0).copy()
        self.root_rotation = Rotation.from_quat(as_numpy(self.grasp_link.get_quat())[[1, 2, 3, 0]])
        self.head_from_grasp = self.root_rotation.inv().apply(
            self.root_goal-as_numpy(self.grasp_link.get_pos()))
        self.root_correction = np.zeros(3)

    def move_root(self, name, goal, *, rotation=None, seconds=2.):
        """Continuous IK at 100 Hz, motor-driven physics at 500 Hz.

        A small integral position correction follows the measured cable end;
        it changes only the hand target, never the passive cable state.
        """
        self.phase = name
        start, end = self.root_goal.copy(), np.asarray(goal, dtype=float)
        r0, r1 = self.root_rotation, self.root_rotation if rotation is None else rotation
        delta = (r1*r0.inv()).as_rotvec()
        count = max(1, round(seconds/.01))
        for k in range(count):
            t = smooth((k+1)/count)
            desired = start+(end-start)*t
            rot = Rotation.from_rotvec(t*delta)*r0
            root = self.last_status["roots_m"].mean(axis=0)
            # Evaluate tracking against the preceding target, not the next
            # interpolated sample, to avoid feed-forward drift.
            error = self.root_goal-root
            self.root_correction += np.clip(.02*error, -.00005, .00005)
            self.root_correction = np.clip(self.root_correction, -.012, .012)
            link_goal = desired+self.root_correction-rot.apply(self.head_from_grasp)
            self.command_hand(link_goal+rot.apply(self.relative_hand_p), rot*self.relative_hand_r)
            self.root_goal, self.root_rotation = desired, rot
            for _ in range(round(.01/self.args.dt)):
                self.step()
        self.finish_phase()

    def park(self):
        root = self.root_goal.copy()
        root[2] += .065
        self.move_root("bundle_lift", root, seconds=2.)
        root[0] = self.task.ring_center[0]-.110
        self.move_root("bundle_clear_ring", root, seconds=1.5)
        self.move_root("bundle_center_at_entry", self.task.ring_center+[-.110, 0., 0.], seconds=2.)
        self.hold("entry_hold", .5)

    def feed(self):
        # The final task verifier, rather than a chosen per-wire shape or
        # order, decides whether this contact-based entry was successful.
        goal = self.task.ring_center+[self.task.layout.ring_tube_radius_m+self.args.feed_depth, 0., 0.]
        duration = max(2., np.linalg.norm(goal-self.root_goal)/self.args.feed_speed)
        self.move_root("bundle_axial_feed", goal, rotation=self.reference_r, seconds=duration)
        self.hold("final_hold", 1.)

    def axial(self):
        self.feed()

    def spiral(self):
        center = self.task.ring_center
        radius, tilt = self.args.orbit_radius, np.radians(self.args.tilt)
        start = center+[-self.args.entry_start, radius, 0.]
        # Tilting toward the aperture makes different portions of the bundle
        # lead without selecting a wire ID. Closed orbit shrinks while feeding.
        self.move_root("spiral_approach", start, seconds=3.)
        n = 24*self.args.cycles
        for i in range(n+1):
            fraction = i/n
            angle = 2*np.pi*self.args.cycles*fraction
            yz = radius*(1.-fraction)*np.array([np.cos(angle), np.sin(angle)])
            x = -self.args.entry_start+(self.args.entry_start-self.args.entry_end)*fraction
            direction = np.r_[1., -np.tan(tilt)*(1.-fraction)*np.array([np.cos(angle), np.sin(angle)])]
            direction /= np.linalg.norm(direction)
            axis = np.cross([1., 0., 0.], direction)
            rot = Rotation.from_rotvec(axis/(np.linalg.norm(axis)+1e-15)*np.arccos(direction[0]))*self.reference_r
            self.move_root(f"spiral_capture_{i:03d}", center+np.r_[x, yz], rotation=rot, seconds=.4)
        self.feed()

    def side_sweep(self):
        center = self.task.ring_center
        original = self.reference_r
        # Two lateral sides cover both halves without moving below the stand.
        # Roll is limited to +/- span, avoiding an inverted below-cable tool.
        for side in (-1., 1.):
            self.move_root("sweep_retreat", center+[-.110, *self.root_goal[1:]-center[1:]], seconds=2.)
            self.move_root("sweep_select_side", center+[-.110, side*.060, 0.], rotation=original, seconds=2.)
            self.move_root("sweep_approach", center+[-self.args.entry_start, side*.060, 0.], seconds=2.)
            self.move_root("sweep_press", center+[-self.args.entry_start, side*self.args.press_radius, 0.], seconds=3.)
            for cycle in range(self.args.cycles):
                for roll in (-self.args.roll_span, self.args.roll_span, 0.):
                    rot = Rotation.from_euler("x", roll, degrees=True)*original
                    self.move_root(f"side_{int(side)}_roll_{cycle}_{roll:g}",
                                   self.root_goal.copy(), rotation=rot, seconds=max(2., abs(roll)/30.))
            self.move_root("sweep_release", center+[-self.args.entry_start, side*.060, 0.], seconds=2.)
        self.move_root("sweep_retreat", center+[-.110, *self.root_goal[1:]-center[1:]], seconds=2.)
        self.move_root("sweep_center", center+[-.110, 0., 0.], rotation=original, seconds=2.)
        self.feed()

    def adaptive_sweep(self):
        center, original = self.task.ring_center, self.reference_r
        for cycle in range(self.args.cycles):
            for side in (-1., 1.):
                self.move_root("adaptive_retreat", [center[0]-.110, *self.root_goal[1:]], seconds=2.)
                self.move_root("adaptive_select_side", center+[-.110, side*.060, 0.], rotation=original, seconds=3.)
                self.move_root("adaptive_approach", center+[-.073, side*.060, 0.], seconds=2.)
                self.contact_sweep(side, 0., 4.)
                for roll in (-self.args.roll_span, self.args.roll_span, 0.):
                    # Limit angular speed so the passive branches can follow.
                    duration = max(3., 1.875*(Rotation.from_euler("x", roll, degrees=True)*original*self.root_rotation.inv()).magnitude()/.5)
                    self.contact_sweep(side, roll, duration)
                self.move_root("adaptive_release", [self.root_goal[0], center[1]+side*.060, self.root_goal[2]], seconds=2.)
            self.move_root("adaptive_retreat", [center[0]-.110, *self.root_goal[1:]], seconds=2.)
            self.move_root("adaptive_center", center+[-.110, 0., 0.], rotation=original, seconds=3.)
            self.hold("adaptive_inspect", .6)
        self.feed()

    def contact_sweep(self, side, roll, seconds):
        self.phase = f"adaptive_contact_side_{int(side)}_roll_{roll:g}"
        r0, r1 = self.root_rotation, Rotation.from_euler("x", roll, degrees=True)*self.reference_r
        delta = (r1*r0.inv()).as_rotvec()
        start_y = self.root_goal[1]
        count = max(1, round(seconds/.01))
        for k in range(count):
            fibers = self.last_status["fibers_m"]
            root = fibers[:, 0].mean(axis=0)
            relative = fibers[:, -1]-root
            # Geometric active set, recomputed every command. This can change
            # identity, affect several wires, or revisit a deformed wire.
            facing = -side*relative[:, 1]
            active = int(np.argmax(facing-.35*np.abs(relative[:, 2])))
            tip = fibers[active, -1]
            goal = self.root_goal.copy()
            goal[0] += np.clip(.04*(self.task.ring_center[0]-tip[0]), -.00015, .00015)
            goal[2] += np.clip(.04*(self.task.ring_center[2]-tip[2]), -.00015, .00015)
            blend = smooth((k+1)/count)
            goal[1] = start_y+(self.task.ring_center[1]+side*self.args.press_radius-start_y)*blend
            rot = Rotation.from_rotvec(blend*delta)*r0
            # One 10 ms IK command with the same integral root tracker as the
            # free-space primitive, but no per-command phase/output overhead.
            error = self.root_goal-root
            self.root_correction = np.clip(self.root_correction+np.clip(.02*error,-.00005,.00005),-.012,.012)
            link_goal = goal+self.root_correction-rot.apply(self.head_from_grasp)
            self.command_hand(link_goal+rot.apply(self.relative_hand_p),rot*self.relative_hand_r)
            self.root_goal,self.root_rotation = goal,rot
            for _ in range(round(.01/self.args.dt)):
                self.step()
        self.finish_phase()

    def tug(self):
        root = self.root_goal.copy()+[0., -.08, .08]
        self.move_root("tug_clear_fixtures", root, seconds=2.)
        self.move_root("axial_tug", root+[-.12, 0., 0.], seconds=1.)
        self.hold("tug_inspect", .6)
        self.move_root("tug_return", self.task.ring_center+[-.110, 0., .08], seconds=4.)
        self.move_root("tug_align", self.task.ring_center+[-.110, 0., 0.], seconds=2.)
        self.feed()

    def greedy_rim(self, iterations=None, insert=True):
        """Choose the largest current protrusion; rotate only clear of the ring.

        A press may shape multiple wires. The stopping objective is the whole
        bundle entering the inward-guiding half of the torus, not an ordered
        list of individually straight wires. Final acceptance is still physical.
        """
        center = self.task.ring_center
        for iteration in range(self.args.max_presses if iterations is None else iterations):
            fit = bundle_fit(self.last_status["fibers_m"], self.task.layout)
            if max(fit["envelope_radii_m"]) < self.args.entry_envelope:
                break
            index = int(np.argmax(fit["envelope_radii_m"]))
            self.target = index
            relative = self.last_status["fibers_m"][index,-1]-self.last_status["roots_m"].mean(axis=0)
            phi = np.arctan2(relative[2],relative[1])
            old_roll = (self.root_rotation*self.reference_r.inv()).as_rotvec()[0]
            wrap = lambda x: (x+np.pi)%(2*np.pi)-np.pi
            choices=[]
            for side,target_phi in [(-1.,0.),(1.,np.pi)]:
                roll = np.clip(old_roll+wrap(target_phi-phi),-np.radians(self.args.roll_span),np.radians(self.args.roll_span))
                residual = abs(wrap(phi+roll-old_roll-target_phi))
                choices.append((residual+.04*abs(roll-old_roll),side,roll))
            # At the ring, release laterally before lifting/retreating. Beyond
            # the ring's axial reach, rotations cannot wrap prepared wires.
            lift=self.root_goal.copy();lift[2]=center[2]+.065
            self.move_root("greedy_lift_clear",lift,seconds=1.5)
            self.move_root("greedy_retreat",[center[0]-.110,*self.root_goal[1:]],seconds=1.)
            candidates=[]
            selected=None
            for score,side,roll in sorted(choices):
                rot=Rotation.from_euler("x",roll)*self.reference_r
                duration=max(1.5,1.875*(rot*self.root_rotation.inv()).magnitude()/.65)
                goal=center+[-.110,side*.060,.065]
                audit=self.probe_root_move(goal,rot,duration)
                candidates.append(dict(side=side,roll_deg=float(np.degrees(roll)),score=score,**audit))
                if audit["passed"]:
                    selected=(side,roll,rot,duration,goal)
                    break
            self.turn_ik_audits.append(dict(time_s=self.step_count*self.args.dt,
                geometric_target=index,candidates=candidates))
            (self.output/"turn_ik_audits.json").write_text(json.dumps(self.turn_ik_audits,indent=2)+"\n")
            if selected is None:
                raise RuntimeError("Neither lateral forming turn has a continuous IK path from the current arm posture")
            side,roll,rot,duration,goal=selected
            self.move_root("greedy_orient_clear",goal,rotation=rot,seconds=duration)
            self.hold("greedy_orientation_hold",.35)
            fibers=self.last_status["fibers_m"]
            root=self.last_status["roots_m"].mean(axis=0)
            relative=fibers[index,-1]-root
            # A fixed 60 mm approach offset is unsafe after other motions
            # broaden the fan: a 42 mm inward protrusion already puts its
            # tip inside the torus. Start with the ENTIRE measured envelope
            # outside the outer rim, including 10 mm approach clearance.
            outer=self.task.layout.ring.radius_m+self.task.layout.ring_tube_radius_m+self.task.layout.fiber_radius_m
            facing=float(np.max(-side*(fibers[:,:,1]-root[1])))
            clearance=max(.060,outer+facing+.010)
            self.move_root("greedy_lower",center+[-.110,side*clearance,-relative[2]],seconds=2.)
            self.hold("greedy_lower_hold",.5)
            tip=self.last_status["fibers_m"][index,-1]
            approach=self.root_goal.copy()+[center[0]-tip[0],0.,center[2]-tip[2]]
            self.move_root("greedy_contact_approach",approach,seconds=3.)
            self.press_protrusion(index,side,3.)
            # 60 mm already clears the 22.7 mm outer ring surface. A 100 mm
            # lateral excursion with a rolled wrist approached an IK branch
            # boundary in the first measured trial.
            self.move_root("greedy_release",[self.root_goal[0],center[1]+side*.060,self.root_goal[2]],seconds=2.)
            self.move_root("greedy_retreat",[center[0]-.110,*self.root_goal[1:]],seconds=1.)
            self.hold("greedy_inspect",.5)
            after=bundle_fit(self.last_status["fibers_m"],self.task.layout)
            self.events.append(dict(iteration=iteration,geometric_target=index,side=side,roll_deg=float(np.degrees(roll)),
                before=fit,after=after,prepared=False,scope="whole-envelope planning event; not a per-wire acceptance"))
            self.save()
        self.target=-1
        lift=self.root_goal.copy();lift[2]=center[2]+.065
        self.move_root("greedy_final_lift",lift,seconds=1.5)
        self.move_root("greedy_final_orient",center+[-.110,0.,.065],rotation=self.reference_r,seconds=3.)
        self.move_root("greedy_final_align",center+[-.110,0.,0.],seconds=1.5)
        self.hold("greedy_before_feed",.6)
        if insert:
            self.feed()

    def greedy_orbit(self):
        """Translate around the rim without rolling the held jacket.

        Reuse the measured contact primitive, but select each action from the
        current whole-bundle envelope rather than a prescribed wire order.
        """
        self.calibrate_grasp(np.zeros(3))
        for _ in range(self.args.max_presses):
            fit = bundle_fit(self.last_status["fibers_m"], self.task.layout)
            if max(fit["envelope_radii_m"]) < self.args.entry_envelope:
                break
            self.prepare(int(np.argmax(fit["envelope_radii_m"])))
        self.target = -1
        self.initialize_root_control()
        self.park()
        self.feed()

    def prepare_orbit(self, index, before):
        """Keep the measured fan outside the rim before a radial press.

        The original 60 mm offset is adequate for the reset fan. After a
        rolled forming action, a 40–50 mm protrusion can put its tip inside
        the torus during the axial approach, reversing the intended contact.
        """
        fibers = self.last_status["fibers_m"]
        root = self.last_status["roots_m"].mean(axis=0)
        direction = fibers[index,-1,1:]-root[1:]
        direction /= np.linalg.norm(direction)
        facing = float(np.max((fibers[:,:,1:]-root[1:])@direction))
        if facing <= .034:
            return super().prepare_orbit(index, before)
        park = self.task.ring_center[0]-self.args.park_clearance-self.reference_root[0]
        self.move_cable(f"wire_{index}_park", [park,*self.offset[1:]], seconds=1.)
        self.hold(f"wire_{index}_park_hold", .6)
        fibers = self.last_status["fibers_m"]
        root = self.last_status["roots_m"].mean(axis=0)
        direction = fibers[index,-1,1:]-root[1:]
        direction /= np.linalg.norm(direction)
        tangent = np.array([-direction[1],direction[0]])
        outer = self.task.layout.ring.radius_m+self.task.layout.ring_tube_radius_m+self.task.layout.fiber_radius_m
        radius = max(.060, outer+float(np.max((fibers[:,:,1:]-root[1:])@direction))+.010)
        lateral = self.task.ring_center[1:]-self.reference_root[1:]-radius*direction
        self.move_cable(f"wire_{index}_select", [park,*lateral], seconds=3.)
        self.hold(f"wire_{index}_select_hold", .6)
        # Recheck after the free-space move because passive wires can bend
        # during acceleration. Only hand commands create this clearance.
        fibers = self.last_status["fibers_m"]
        root = self.last_status["roots_m"].mean(axis=0)
        desired = outer+float(np.max((fibers[:,:,1:]-root[1:])@direction))+.010
        actual = float((self.task.ring_center[1:]-root[1:])@direction)
        if desired > actual+.001:
            radius += desired-actual
            lateral -= (desired-actual)*direction
            self.move_cable(f"wire_{index}_clearance", [park,*lateral], seconds=1.5)
            self.hold(f"wire_{index}_select_hold", .6)
        tip = self.last_status["fibers_m"][index,-1]
        x = self.offset[0]+self.task.ring_center[0]-tip[0]
        lateral += tangent*((self.task.ring_center[1:]-tip[1:])@tangent)
        self.move_cable(f"wire_{index}_approach", [x,*lateral], seconds=3.)
        press = lateral+(radius-self.args.press_radius)*direction
        duration = max(2.,2.*(radius-self.args.press_radius)/(.060-self.args.press_radius))
        self.move_cable(f"wire_{index}_press", [x,*press], seconds=duration,track_tip=True,tangent=tangent,
                        radial_direction=direction,radial_target=self.args.press_radius)
        self.move_cable(f"wire_{index}_settle", seconds=1.,track_tip=True,tangent=tangent,
                        radial_direction=direction,radial_target=self.args.press_radius)
        release = self.offset[1:]-(radius-self.args.press_radius)*direction
        self.move_cable(f"wire_{index}_release", [self.offset[0],*release], seconds=2.)
        self.hold(f"wire_{index}_inspect", 1.)
        self.record_preparation(index,before)

    def greedy_hybrid(self):
        """Use translations except where the bottom support blocks the rim.

        Upward protrusions require a below-ring approach if the jacket is not
        rolled. The physical stand occupies that region, so shape those from
        a lateral side and return to the common orientation before replanning.
        """
        self.calibrate_grasp(np.zeros(3))
        for _ in range(self.args.max_presses):
            fit = bundle_fit(self.last_status["fibers_m"], self.task.layout)
            if max(fit["envelope_radii_m"]) < self.args.entry_envelope:
                break
            index = int(np.argmax(fit["envelope_radii_m"]))
            radial = self.last_status["fibers_m"][index,-1,1:]-self.last_status["roots_m"].mean(axis=0)[1:]
            radial /= np.linalg.norm(radial)
            if radial[1] > .6 and abs(radial[0]) < .55:
                self.initialize_root_control()
                self.greedy_rim(iterations=1, insert=False)
                self.calibrate_grasp(np.zeros(3))
            else:
                self.prepare(index)
        self.target = -1
        self.initialize_root_control()
        self.park()
        self.feed()

    def press_protrusion(self,index,side,seconds):
        self.phase="greedy_envelope_press"
        y0=self.root_goal[1]
        count=round(seconds/.01)
        for k in range(count):
            root=self.last_status["roots_m"].mean(axis=0)
            tip=self.last_status["fibers_m"][index,-1]
            # Contact the outer surface while targeting an envelope on the
            # INNER half of the torus for the subsequent guided insertion.
            z=tip[2]-root[2]
            desired_center_radius=self.args.entry_envelope-self.task.layout.fiber_radius_m-.0005
            offset=np.sqrt(max(.006**2,desired_center_radius**2-z*z))
            press=self.task.layout.ring.radius_m+self.task.layout.ring_tube_radius_m+self.task.layout.fiber_radius_m+offset
            goal=self.root_goal.copy()
            goal[0]+=np.clip(.04*(self.task.ring_center[0]-tip[0]),-.00015,.00015)
            goal[2]+=np.clip(.04*(self.task.ring_center[2]-tip[2]),-.00015,.00015)
            goal[1]=y0+(self.task.ring_center[1]+side*press-y0)*smooth(min(1.,(k+1)/(.7*count)))
            self.root_correction=np.clip(self.root_correction+np.clip(.02*(self.root_goal-root),-.00005,.00005),-.012,.012)
            rot=self.root_rotation
            link_goal=goal+self.root_correction-rot.apply(self.head_from_grasp)
            self.command_hand(link_goal+rot.apply(self.relative_hand_p),rot*self.relative_hand_r)
            self.root_goal=goal
            for _ in range(round(.01/self.args.dt)):self.step()
        self.finish_phase()

    def run(self):
        failure = None
        try:
            self.grasp()
            self.initialize_root_control()
            self.park()
            getattr(self, self.args.mode)()
            if not self.last_status["success"]:
                failure = "Policy completed without a verified full threading state"
        except RuntimeError as error:
            failure = str(error)
            print("ATTEMPT STOPPED: "+failure, flush=True)
        self.record()
        self.save()
        report = self.finish_report(failure)
        report.update(scope="whole_bundle_real_robot_IK_exploration",
                      bundle_metrics=self.bundle_metrics, whole_bundle_policy=True,
                      turn_ik_audits=self.turn_ik_audits)
        (self.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Exact generated scene config")
    parser.add_argument("--stability", type=Path, default=Path("runs/environment-solvability/fiber_bundling/ik_stability/result.json"))
    parser.add_argument("--mode", choices=("axial", "spiral", "side_sweep", "adaptive_sweep", "greedy_rim", "greedy_orbit", "greedy_hybrid", "tug"), default="spiral")
    parser.add_argument("--dt", type=float, choices=(.002, .001), default=.002)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--orbit-radius", type=float, default=.022)
    parser.add_argument("--tilt", type=float, default=18.)
    parser.add_argument("--entry-start", type=float, default=.070)
    parser.add_argument("--entry-end", type=float, default=.025)
    parser.add_argument("--roll-span", type=float, default=70.)
    parser.add_argument("--press-radius", type=float, default=.034)
    parser.add_argument("--feed-speed", type=float, default=.012)
    parser.add_argument("--max-presses", type=int, default=10)
    parser.add_argument("--entry-envelope", type=float, default=.016)
    parser.add_argument("--grasp-link", choices=("trunk_03", "trunk_04", "trunk_05"), default="trunk_03")
    parser.add_argument("--grasp-angle", type=float, default=150.)
    parser.add_argument("--assist", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a fresh output directory")
    if args.cycles < 1 or not .005 <= args.feed_speed <= .03:
        parser.error("Positive cycle count and 5–30 mm/s feed required")
    if args.max_presses < 1 or not .010 <= args.entry_envelope <= .017:
        parser.error("Require a positive press budget and an inward-guiding entry envelope")
    if not 0 <= args.orbit_radius <= .06 or not 0 <= args.tilt <= 35 or not 0 < args.roll_span <= 90:
        parser.error("Invalid orbit radius, tilt or roll span")
    if not .01 <= args.entry_end <= args.entry_start <= .11 or not .025 <= args.press_radius <= .060:
        parser.error("Invalid entry distances or press radius")
    args.backend, args.performance_mode, args.stage = "cpu", True, "full"
    args.grip_x, args.regrasp_back, args.motion_scale = .015, False, 1.
    args.rear_link, args.rear_x, args.park_clearance, args.feed_depth = "trunk_04", .015, .110, .034
    args.selection, args.order, args.preparation_passes = "orbit", None, 1
    if not BundleIKTrial(args).run()["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

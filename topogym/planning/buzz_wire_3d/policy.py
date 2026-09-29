"""One native EE action per observation; no scene writes or historical qpos."""
import numpy as np
from collections import deque
from scipy.spatial.transform import Rotation, Slerp

from topogym.assets.geometry.buzz_wire_3d import endpoint_pose


def rotation(q):
    return Rotation.from_quat(np.asarray(q)[[1, 2, 3, 0]])


class BuzzWirePolicy:
    def __init__(self, *, route, origin, part="all", grasp_height=.012, grasp_tilt=75., plan=None, grasp_y=255.,
                 grasp_yaw=0., grasp_roll=180., grasp_fraction=.4, lift_height=.025,
                 instructions=None, progress_error_m=.0015, arrival_error_m=.0004,
                 close_on_contact=False, stop_after_route=False, grasp_advance=0., route_seconds=None,
                 settle_timeout_s=15., joint_seed_fraction=.02, clearance_tracking_fraction=None,
                 stop_after_transfer=False, free_tool_motion_limit_m=None,
                 stop_approach_on_grasp=True):
        self.route, self.origin = route, np.asarray(origin)
        self.part, self.grasp_height, self.grasp_tilt = part, grasp_height, grasp_tilt
        self.phase, self.tracking = "created", {}
        self.samples = []
        self.plan = plan
        self.grasp_y = grasp_y
        self.grasp_yaw,self.grasp_roll,self.grasp_fraction = grasp_yaw,grasp_roll,grasp_fraction
        self.lift_height,self.instructions = lift_height,instructions
        self.progress_error_m,self.arrival_error_m = progress_error_m,arrival_error_m
        self.close_on_contact = close_on_contact
        self.stop_after_route = stop_after_route
        self.grasp_advance = grasp_advance
        self.route_seconds = route_seconds
        self.settle_timeout_s = settle_timeout_s
        self.joint_seed_fraction = joint_seed_fraction
        self.clearance_tracking_fraction = clearance_tracking_fraction
        self.stop_after_transfer = stop_after_transfer
        self.free_tool_motion_limit_m = free_tool_motion_limit_m
        self.stop_approach_on_grasp = stop_approach_on_grasp

    def initialize(self, context):
        if (context["action_spec"]["robot_id"] != "panda_robotiq"
                or context["action_spec"]["mode"] != "EE_ABS"):
            raise ValueError("Buzz policy requires Panda Robotiq EE_ABS")
        self.dt = context["timing_spec"]["control_dt_s"]
        self.grip, self.program = (.8 if self.part in {"solve", "regrasp", "park", "finish"} else 0.), None
        self.bias, self.angle_bias = np.zeros(3), np.zeros(3)
        self.reference_arm_seed = None

    def act(self, obs):
        self.obs = obs
        events = obs["privileged"]["world"]["contact_events"]["events"]
        if any(event["touching"] and {event["role_a"],event["role_b"]} == {"robot","wire_metal"}
               for event in events):
            raise RuntimeError("Robot touched the wire; this execution cannot qualify")
        if self.program is None:
            self.program = self.actions()
        return next(self.program, None)

    def time(self):
        return self.obs["state"]["sim_time_s"]

    def body(self):
        b = self.obs["privileged"]["world"]["bodies"]["wand"]
        return np.asarray(b["position_m"]), rotation(b["quaternion_wxyz"])

    def tcp(self):
        b = self.obs["robot"]["arm"]
        return np.asarray(b["tcp_position_world_m"]), rotation(b["tcp_orientation_wxyz"])

    def command(self, p, r, *, nominal=None):
        self.nominal_tcp_target = nominal
        return {"arm": dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3,0,1,2]].tolist(),
                            gripper_position_rad=self.grip)}

    def hold(self, seconds):
        start = self.time()
        while self.time()-start < seconds-1e-8:
            yield {}

    def settle_gripper(self):
        """Wait for actual passive geometry before an owner collision query."""
        start, window = self.time(), deque()
        while True:
            joints = self.obs["privileged"]["world"]["articulations"]["robot"]["joints"]
            names = sorted(name for name in joints if name.startswith(("finger_", "r85_")))
            positions = [v for name in names for v in joints[name]["position"]]
            velocities = [abs(v) for name in names for v in joints[name]["velocity"]]
            window.append((self.time(),positions))
            while window and window[0][0] < self.time()-.5-1e-8:
                window.popleft()
            spread = float(np.ptp(np.asarray([row[1] for row in window]),axis=0).max())
            speed = max(velocities,default=float("inf"))
            self.tracking = dict(phase=self.phase, gripper_position_range_rad=spread, gripper_speed_rad_s=speed)
            if self.time()-window[0][0] >= .5-1e-8 and spread < .002 and speed < .01:
                return
            if self.time()-start > self.settle_timeout_s:
                raise RuntimeError("Gripper passive joints did not settle")
            yield {}

    def acquire_grip(self):
        if not self.close_on_contact:
            self.grip = .8
            yield {"arm":{"gripper_position_rad":self.grip}}
        else:
            while self.grip < .8:
                hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
                if hand["phase"] in {"registered", "holding"}:
                    break
                # The driven joint can lag far behind its command under load.
                # Small separated increments avoid storing a large closing
                # error that would squeeze the tool out after acquisition.
                self.grip = min(.8,self.grip+.004)
                yield {"arm":{"gripper_position_rad":self.grip}}
                started = self.time()
                while self.time()-started < .5:
                    hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
                    if hand["phase"] in {"registered", "holding"}:
                        break
                    yield {}
        yield from self.hold(2.)

    def move(self, target, seconds, phase):
        self.phase = phase
        p0, r0 = self.tcp()
        p, r = target
        turn = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), r.as_quat()]))
        start = self.time()
        while True:
            t = min(1., (self.time()-start+self.dt)/seconds)
            u = t*t*(3-2*t)
            yield self.command(p0+u*(p-p0), turn(u))
            if t >= 1:
                break
        yield from self.hold(.3)
        actual_p, actual_r = self.tcp()
        if np.linalg.norm(actual_p-p) > .005 or (actual_r*r.inv()).magnitude() > .04:
            raise RuntimeError(f"TCP did not reach {phase}: {np.linalg.norm(actual_p-p):.6f} m")

    def tool_supported(self):
        """The Task's support test: tool metal or handle touching the finish deck."""
        return any(event["touching"] and {event["role_a"], event["role_b"]} & {"wand_metal", "wand_handle"}
                   and "finish_support" in (event["role_a"], event["role_b"])
                   for event in self.obs["privileged"]["world"]["contact_events"]["events"])

    def follow(self, pose_at, seconds, phase, stop=None):
        self.phase = phase
        elapsed, start, last_advance = 0., self.time(), self.time()
        while True:
            hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
            if hand["phase"] != "holding":
                raise RuntimeError(f"Grasp lost during {phase}: {hand['phase']} / {hand.get('rejection')}")
            if stop is not None and stop():
                # Stop commanding further motion; the tracking integral would
                # otherwise keep pushing against the contact.
                self.samples.append(dict(time_s=self.time(), stopped=True, **self.tracking))
                return
            u = min(1., elapsed/seconds)
            p, r = pose_at(u)
            if self.reference_arm_seed is not None:
                actual = np.asarray(self.obs["robot"]["arm"]["joint_position_rad"])
                self.desired_arm_seed = (1-self.joint_seed_fraction)*actual+self.joint_seed_fraction*self.reference_arm_seed
            ap, ar = self.body()
            error, angle = p-ap, (r*ar.inv()).as_rotvec()
            material_error = float(np.linalg.norm(error)+.09*np.linalg.norm(angle))
            self.tracking = dict(phase=phase, progress=u, material_error_m=material_error,
                                 position_error_m=float(np.linalg.norm(error)), angle_error_rad=float(np.linalg.norm(angle)))
            if u >= 1 and material_error < self.arrival_error_m:
                self.samples.append(dict(time_s=self.time(), **self.tracking))
                return
            progress_error = self.progress_error_m
            if self.clearance_tracking_fraction is not None and getattr(self,"reference_clearance",None) is not None:
                progress_error = min(progress_error,max(.00025,self.clearance_tracking_fraction*self.reference_clearance))
            if material_error < progress_error:
                elapsed = min(seconds, elapsed+self.dt)
                last_advance = self.time()
            if self.time()-last_advance > 8. or self.time()-start > max(30., seconds*10):
                raise RuntimeError(f"Buzz tracking stalled: {self.tracking}")
            self.bias = np.clip(self.bias+4*self.dt*error, -.03, .03)
            self.angle_bias = np.clip(self.angle_bias+4*self.dt*angle, -.2, .2)
            cr = Rotation.from_rotvec(self.angle_bias+.4*angle)*r
            yield self.command(p+self.bias+.4*error+cr.apply(self.offset_p), cr*self.offset_r,
                               nominal=(p+r.apply(self.offset_p),r*self.offset_r))

    def move_body(self, target, seconds, phase, stop=None):
        p0, r0 = self.body()
        p, r = target
        turn = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), r.as_quat()]))
        def pose(u):
            u = u*u*(3-2*u)
            return p0+u*(p-p0), turn(u)
        yield from self.follow(pose, seconds, phase, stop)

    def actions(self):
        if self.part in {"solve", "regrasp", "park", "finish", "joint_reference"}:
            self.grip = .8*self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["last_fraction"]
        if self.part == "joint_reference":
            yield from self.joint_reference_actions()
            return
        if self.part == "script":
            yield from self.script_actions()
            return
        if self.part in {"regrasp", "park"}:
            yield from self.regrasp_actions()
            return
        if self.part == "acquire":
            yield from self.acquire_actions()
            return
        if self.part == "finish":
            yield from self.finish_actions()
            return
        if self.part == "solve":
            yield from self.solve_actions()
            return
        self.phase = "open_at_home"
        yield {"arm": {"gripper_position_rad": 0.}}
        yield from self.hold(.5)
        p, r = self.body()
        l = self.route.layout
        point = np.array([l.loop_radius_m+l.stem_length_m+l.grip_length_m*.4, 0, 0])
        grasp_r = r*Rotation.from_euler("y", 180-self.grasp_tilt, degrees=True)*Rotation.from_euler("z", 180, degrees=True)
        grasp_p = p+r.apply(point)+[0, 0, self.grasp_height]
        yield from self.move((self.tcp()[0]+[0, 0, .25], self.tcp()[1]), 2., "clear_home")
        outside = grasp_p-grasp_r.apply([0, 0, .12])
        yield from self.move((outside+[0, 0, .15], grasp_r), 3., "home_to_pregrasp")
        yield from self.move((outside, grasp_r), 3., "descend_outside_wire")
        yield from self.move((grasp_p, grasp_r), 3., "approach_handle")
        self.phase, self.grip = "close_and_acquire", .8
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self.hold(2.)
        hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
        if hand["phase"] != "holding":
            raise RuntimeError("Buzz grasp not acquired: "+str(hand))
        p, r = self.body()
        tp, tr = self.tcp()
        self.offset_p, self.offset_r = r.inv().apply(tp-p), r.inv()*tr
        yield from self.move_body((p+[0, 0, .025], r), 2., "lift_from_deck")
        if self.part == "pickup":
            return
        yield from self.solve_actions()

    def regrasp_actions(self):
        """Park the handle across the clear side of the post, then grasp its end."""
        p, r = self.body()
        tp, tr = self.tcp()
        self.offset_p, self.offset_r = r.inv().apply(tp-p), r.inv()*tr
        l = self.route.layout
        rest_p, rest_r = endpoint_pose(self.route, 0)
        pitch = np.arcsin(rest_r.apply([1, 0, 0])[2])
        parked_r = Rotation.from_euler("z", 90, degrees=True)*Rotation.from_euler("y", -pitch)
        yield from self.move_body((p, parked_r), 5., "turn_handle_for_regrasp")
        yield from self.move_body((rest_p+self.origin, parked_r), 3., "park_for_regrasp")
        self.phase, self.grip = "release_for_regrasp", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self.hold(1.5)
        if self.part == "park":
            tp, tr = self.tcp()
            yield from self.move((tp-tr.apply([0,0,.025]), tr), 1., "park_short_withdraw")
            self.phase = "settle_open_gripper"
            yield from self.settle_gripper()
            return
        tp, tr = self.tcp()
        yield from self.move((tp-tr.apply([0,0,.12]), tr), 2., "regrasp_withdraw")
        tp, tr = self.tcp()
        yield from self.move((tp+[0,0,.18], tr), 2., "regrasp_rise")
        p, r = self.body()
        gr = r*Rotation.from_euler("y", 255, degrees=True)*Rotation.from_euler("z", 180, degrees=True)
        gp = p+r.apply([l.loop_radius_m+l.stem_length_m+l.grip_length_m*.4,0,0])+[0,0,.012]
        outside = gp-gr.apply([0,0,.12])
        yield from self.move((outside+[0,0,.15], gr), 3., "regrasp_preapproach")
        yield from self.move((outside, gr), 3., "regrasp_descend")
        yield from self.move((gp, gr), 3., "regrasp_approach")
        self.phase, self.grip = "regrasp_acquire", .8
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self.hold(2.)
        hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
        if hand["phase"] != "holding":
            raise RuntimeError("Regrasp failed: "+str(hand))
        p, r = self.body()
        tp, tr = self.tcp()
        self.offset_p, self.offset_r = r.inv().apply(tp-p), r.inv()*tr
        self.bias[:], self.angle_bias[:] = 0., 0.
        yield from self.move_body((p+[0,0,.025], r), 2., "lift_after_regrasp")
        self.phase = "settle_closed_gripper"
        yield from self.settle_gripper()

    def acquire_actions(self):
        """Execute the owner-planned open-hand transfer, then close on contact."""
        if self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["binding"] is not None:
            raise RuntimeError("Free-hand transfer requires a released tool")
        self.grip = .8*self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["last_fraction"]
        self.phase = "regrasp_free_transfer"
        tp, tr = self.tcp()
        rows = [dict(time_s=0.,position_m=tp,quaternion_wxyz=tr.as_quat()[[3,0,1,2]])]+self.plan
        times = np.array([row["time_s"] for row in rows])
        positions = np.array([row["position_m"] for row in rows])
        joint_seeds = np.array([self.obs["robot"]["arm"]["joint_position_rad"]]+
                               [row["qpos"][:7] for row in self.plan])
        turns = Slerp(times, Rotation.from_quat(np.array([row["quaternion_wxyz"] for row in rows])[:,[1,2,3,0]]))
        elapsed, last_advance = 0., self.time()
        bias, angle_bias = np.zeros(3), np.zeros(3)
        free_body = self.body() if self.free_tool_motion_limit_m is not None else None
        while True:
            if free_body is not None:
                bp, br = self.body()
                moved = np.linalg.norm(bp-free_body[0])+.09*(br*free_body[1].inv()).magnitude()
                if moved > self.free_tool_motion_limit_m:
                    raise RuntimeError(f"Free transfer moved the released tool: {moved:.6f} m")
            p = np.array([np.interp(elapsed,times,positions[:,i]) for i in range(3)])
            r = turns(elapsed)
            self.desired_arm_seed = np.array([np.interp(elapsed,times,joint_seeds[:,i]) for i in range(7)])
            ap, ar = self.tcp()
            error = np.linalg.norm(p-ap)+.15*(r*ar.inv()).magnitude()
            self.tracking = dict(phase=self.phase,progress=float(elapsed/times[-1]),material_error_m=float(error))
            if elapsed >= times[-1] and error < .001:
                break
            if error < .0015:
                elapsed = min(times[-1],elapsed+self.dt)
                last_advance = self.time()
            if self.time()-last_advance > 8:
                raise RuntimeError(f"Open-hand transfer stalled: {self.tracking}")
            delta, angle = p-ap,(r*ar.inv()).as_rotvec()
            bias = np.clip(bias+4*self.dt*delta,-.02,.02)
            angle_bias = np.clip(angle_bias+4*self.dt*angle,-.15,.15)
            yield self.command(p+bias+.4*delta,Rotation.from_rotvec(angle_bias+.4*angle)*r)
        self.desired_arm_seed = None
        if self.stop_after_transfer:
            return
        p,r = self.body()
        l = self.route.layout
        gr = (r*Rotation.from_euler("z",self.grasp_yaw,degrees=True)*
              Rotation.from_euler("y",self.grasp_y,degrees=True)*Rotation.from_euler("z",self.grasp_roll,degrees=True))
        gp = p+r.apply([l.loop_radius_m+l.stem_length_m+l.grip_length_m*self.grasp_fraction,0,0])+[0,0,self.grasp_height]
        gp += gr.apply([0,0,self.grasp_advance])
        yield from self.approach_grasp((gp,gr))
        self.phase = "regrasp_acquire"
        yield from self.acquire_grip()
        hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
        if hand["phase"] != "holding":
            raise RuntimeError("Regrasp failed: "+str(hand))
        p,r = self.body();tp,tr = self.tcp()
        self.offset_p,self.offset_r = r.inv().apply(tp-p),r.inv()*tr
        if self.lift_height:
            yield from self.move_body((p+[0,0,self.lift_height],r),2.,"lift_after_regrasp")
        self.phase = "settle_closed_gripper"
        yield from self.settle_gripper()
        if self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["phase"] != "holding":
            raise RuntimeError("Grasp lost while the fingers settled")

    def approach_grasp(self, target):
        """Stop advancing a preclosed hand once real contact registers a grasp."""
        motion = self.move(target,3.,"regrasp_approach")
        if not self.stop_approach_on_grasp:
            yield from motion
            return
        while self.obs["privileged"]["world"]["grasp"]["hands"]["arm"].get("phase") not in {"registered", "holding"}:
            try:
                action = next(motion)
            except StopIteration:
                return
            yield action
        self.phase = "regrasp_contact_stop"

    def script_actions(self):
        """Observation-based diagnostic waypoints, using the same action path."""
        self.grip = .8*self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["last_fraction"]
        fresh = True
        for index,row in enumerate(self.instructions or ()):
            operation = row["operation"]
            phase = row.get("phase",f"script_{index}_{operation}")
            seconds = row.get("seconds",2.)
            if operation == "grip":
                self.phase,self.grip = phase,float(row["value"])
                yield {"arm":{"gripper_position_rad":self.grip}}
                yield from self.hold(seconds)
                fresh = True
            elif operation == "hold":
                self.phase = phase
                yield from self.hold(seconds)
            elif operation == "settle_gripper":
                self.phase = phase
                yield from self.settle_gripper()
            elif operation in {"body","tcp"}:
                if "gripper_position_rad" in row:
                    self.grip = float(row["gripper_position_rad"])
                p,r = self.body() if operation == "body" else self.tcp()
                delta = np.asarray(row.get("translation_m",[0,0,0]))+r.apply(row.get("local_translation_m",[0,0,0]))
                target_p = np.asarray(row["position_m"]) if "position_m" in row else p+delta
                target_r = rotation(row["quaternion_wxyz"]) if "quaternion_wxyz" in row else r
                if operation == "body":
                    if fresh:
                        tp,tr = self.tcp()
                        self.offset_p,self.offset_r = r.inv().apply(tp-p),r.inv()*tr
                        self.bias[:],self.angle_bias[:] = 0.,0.
                        fresh = False
                    stop = self.tool_supported if row.get("stop_when_supported") else None
                    yield from self.move_body((target_p,target_r),seconds,phase,stop)
                else:
                    yield from self.move((target_p,target_r),seconds,phase)
                    fresh = True
            else:
                raise ValueError(f"Unknown diagnostic operation: {operation}")

    def solve_actions(self):
        p, r = self.body()
        tp, tr = self.tcp()
        self.offset_p, self.offset_r = r.inv().apply(tp-p), r.inv()*tr
        if self.plan:
            values = np.array([row["progress"] for row in self.plan])
            route_fraction = values[-1]-values[0]
            values = (values-values[0])/route_fraction
            positions = np.array([row["position_m"] for row in self.plan])
            joint_seeds = np.array([row["qpos"][:7] for row in self.plan])
            clearances = np.array([row.get("clearance_m",.001) for row in self.plan])
            turns = Slerp(values, Rotation.from_quat(np.array([row["quaternion_wxyz"] for row in self.plan])[:,[1,2,3,0]]))
            def route_pose(u):
                self.reference_arm_seed = np.array([np.interp(u,values,joint_seeds[:,i]) for i in range(7)])
                self.reference_clearance = float(np.interp(u,values,clearances))
                return np.array([np.interp(u, values, positions[:,i]) for i in range(3)]), turns(u)
        else:
            route_fraction = 1.
            def route_pose(u):
                p, q = self.route.pose(u)
                return p+self.origin, rotation(q)
        yield from self.move_body(route_pose(0.), 5., "thread_start_post")
        yield from self.follow(route_pose, self.route_seconds or self.route.length*route_fraction/.018, "traverse_wire")
        self.reference_arm_seed, self.desired_arm_seed = None, None
        if self.stop_after_route:
            return
        p, _ = endpoint_pose(self.route, 1)
        _, r = self.body()
        r = r*Rotation.from_euler("y",20,degrees=True)
        # Preserve the reachable route-end tilt. Regrasp after the tool rests
        # on the deck, before aligning the handle with the final support pose.
        yield from self.move_body((p+self.origin+[0, 0, .06], r), 3., "lower_on_finish_post")
        self.phase, self.grip = "release", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self.hold(3.)

    def joint_reference_actions(self):
        """Follow dense FK-checked joint references through ordinary actions."""
        times = np.array([row["time_s"] for row in self.plan])
        qs = np.array([row["qpos"][:7] for row in self.plan])
        positions = np.array([row["position_m"] for row in self.plan])
        turns = Slerp(times,Rotation.from_quat(np.array([row["quaternion_wxyz"] for row in self.plan])[:,[1,2,3,0]]))
        elapsed, last_advance = 0., self.time()
        self.phase = "follow_checked_joint_references"
        while True:
            if self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["phase"] != "holding":
                raise RuntimeError("Grasp lost while following joint references")
            p = np.array([np.interp(elapsed,times,positions[:,i]) for i in range(3)])
            r = turns(elapsed)
            ap, ar = self.body()
            error = float(np.linalg.norm(p-ap)+.09*(r*ar.inv()).magnitude())
            self.tracking = dict(progress=float(elapsed/times[-1]),material_error_m=error)
            if elapsed >= times[-1] and error < self.arrival_error_m:
                return
            reference = np.array([np.interp(elapsed,times,qs[:,i]) for i in range(7)])
            if error < self.progress_error_m:
                elapsed = min(times[-1],elapsed+self.dt)
                last_advance = self.time()
            if self.time()-last_advance > 8:
                raise RuntimeError(f"Joint reference tracking stalled: {self.tracking}")
            yield {"arm":{"joint_position_rad":reference.tolist(),"gripper_position_rad":self.grip}}

    def finish_actions(self):
        p,r = self.body();tp,tr = self.tcp()
        self.offset_p,self.offset_r = r.inv().apply(tp-p),r.inv()*tr
        end_p,end_r = endpoint_pose(self.route,1)
        if r.apply([0,0,1])[2]<0:
            end_r = end_r*Rotation.from_euler("x",180,degrees=True)
        yield from self.move_body((p,end_r),4.,"align_finish_after_regrasp")
        yield from self.move_body((end_p+self.origin,end_r),3.,"place_on_finish_deck")
        self.phase,self.grip = "final_release",0.
        yield {"arm":{"gripper_position_rad":self.grip}}
        yield from self.hold(1.)
        tp, tr = self.tcp()
        yield from self.move((tp-tr.apply([0,0,.08]),tr),2.,"withdraw")
        tp,tr = self.tcp()
        yield from self.move((tp+[0,0,.15],tr),2.,"withdraw_up")
        self.phase = "settle"
        yield from self.hold(5.)

"""Measured friction grasps and bounded EE_ABS references; no simulator access.

All geometry, finger identities and route poses are explicit manager oracle
inputs. Finishing a reference is deliberately separate from Task qualification.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.evaluation.task_metrics import placement_candidate
from topogym.utils.geometry.regions import GoalRegion


def pose(position, quaternion):
    p, q = np.asarray(position, float), np.asarray(quaternion, float)
    if (p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all()
            or not np.isclose(np.linalg.norm(q), 1., atol=1e-6, rtol=0)):
        raise ValueError("Expected metres and a finite unit wxyz quaternion")
    return p, Rotation.from_quat(q[[1, 2, 3, 0]])


def body_pose(body):
    return pose(body["position_m"], body["quaternion_wxyz"])


def tcp_pose(arm):
    return pose(arm["tcp_position_world_m"], arm["tcp_orientation_wxyz"])


def relative_pose(parent, child):
    p, r = parent
    cp, cr = child
    return r.inv().apply(cp-p), r.inv()*cr


def errors(actual, target):
    return float(np.linalg.norm(actual[0]-target[0])), float((actual[1].inv()*target[1]).magnitude())


@dataclass(frozen=True)
class Limits:
    grasp_translation_m: float = .002
    grasp_rotation_rad: float = np.deg2rad(3.)
    contact_grace_s: float = .15
    grasp_acquisition_s: float = 1.
    passive_hold_s: float = 2.
    translation_speed_m_s: float = .015
    angular_speed_rad_s: float = .12
    translation_acceleration_m_s2: float = .04
    angular_acceleration_rad_s2: float = .3
    tracking_translation_m: float = .003
    tracking_rotation_rad: float = .03
    target_translation_m: float = .001
    target_rotation_rad: float = .01
    stagnation_s: float = 3.
    penetration_m: float = .002

    def __post_init__(self):
        if any(not np.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError("Policy limits must be finite and positive")
        if self.passive_hold_s < 2.:
            raise ValueError("Friction grasp baseline requires at least 2 seconds")


class PolicyFailure(RuntimeError):
    pass


def bilateral_contacts(world, entity, fingers):
    """Use actual body/finger link IDs. Missing evidence is never a zero force."""
    links = set(world["bodies"][entity]["link_indices"])
    contacts = world["contacts"]
    a, b = np.asarray(contacts["link_a"]), np.asarray(contacts["link_b"])
    depth, force = np.asarray(contacts["penetration"]), np.asarray(contacts["force"])
    # Genesis exports a leading singleton environment dimension on some builds.
    a, b, depth = a.reshape(-1), b.reshape(-1), depth.reshape(-1)
    force = force.reshape(-1, 3)
    if (len({len(a), len(b), len(depth), len(force)}) != 1
            or not np.isfinite(depth).all() or not np.isfinite(force).all()):
        raise ValueError("Invalid contact evidence")
    seen = set()
    for x, y, f in zip(a, b, force):
        if np.linalg.norm(f) <= 1e-8:
            continue
        if int(x) in links and int(y) in fingers:
            seen.add(int(y))
        if int(y) in links and int(x) in fingers:
            seen.add(int(x))
    return set(fingers) <= seen


class FrictionReferencePolicy:
    """Feedback executor with a separately useful passive-hold diagnostic.

    Routes contain world TCP targets, measured object targets and explicit
    grasp acquisition points. No route is silently substituted for a model.
    """
    task_id = robot_id = model_revision = None

    def __init__(self, *, oracle, route=None, part="solve", limits=None):
        if part not in {"solve", "hold"}:
            raise ValueError("part must be solve or hold")
        self.oracle, self.route = deepcopy(oracle), deepcopy(route)
        self.part, self.limits = part, limits or Limits()
        if oracle["task_id"] != self.task_id or oracle["model_revision"] != self.model_revision:
            raise ValueError("Unsupported task/model revision; no historical route fallback")
        if not oracle.get("grasps"):
            raise ValueError("Explicit object ownership and opposing finger identities are required")
        for grasp in oracle["grasps"].values():
            fingers = grasp["finger_link_indices"]
            if len(fingers) != 2 or len(set(fingers)) != 2 or any(type(i) is not int or i < 0 for i in fingers):
                raise ValueError("A friction grasp requires two distinct native finger links")
        if part == "solve":
            if not route or not route.get("waypoints"):
                raise ValueError("solve requires an explicit geometrically checked route")
            if route["identity"] != oracle["identity"]:
                raise ValueError("Route does not match frozen instance/geometry/goal identity")
            for waypoint in route["waypoints"]:
                timeout, hold = waypoint["timeout_s"], waypoint.get("hold_s", .1)
                if (not waypoint.get("phase") or not waypoint.get("tcp")
                        or not np.isfinite([timeout, hold]).all() or timeout <= 0 or hold < 0):
                    raise ValueError("Incomplete route waypoint")
                for target in (*waypoint["tcp"].values(), *waypoint.get("bodies", {}).values()):
                    body_pose(target)
                if not set(waypoint.get("grasps", ())) <= set(oracle["grasps"]):
                    raise ValueError("Unknown route grasp")
        self.phase, self.completed = "created", False
        self.events, self.samples = [], []

    def initialize(self, context):
        spec = context["action_spec"]
        if (spec["robot_id"] != self.robot_id or spec["mode"] != "EE_ABS"
                or spec["coordinate_frame"] != "world" or "wxyz" not in spec["orientation"]):
            raise ValueError("Policy requires the declared robot, world metres and EE_ABS/wxyz")
        if context["mode"] != "unlimited" or "world" not in context["observation_spec"]["privileged_fields"]:
            raise ValueError("Policy requires explicitly authorized unlimited world observations")
        if spec["grasp_assist"]["model"] != "none":
            raise ValueError("Friction baseline requires grasp assist disabled")
        self.dt = float(context["timing_spec"]["control_dt_s"])
        if not np.isfinite(self.dt) or self.dt <= 0:
            raise ValueError("Invalid control period")
        self.groups = spec["groups"]
        if self.part == "solve":
            for w in self.route["waypoints"]:
                if not set(w["tcp"]) <= set(self.groups):
                    raise ValueError("Unknown route arm")
                for arm, value in w.get("gripper", {}).items():
                    lo, hi = self.groups[arm]["gripper_limits"]
                    if not np.isfinite(value) or not lo <= value <= hi:
                        raise ValueError("Route gripper target outside native limits")
        self.phase, self.completed = "initial_review", False
        self.events, self.samples = [], []
        self.references, self.last_contact, self.commands, self.velocity = {}, {}, {}, {}
        self.index, self.started, self.stable_since, self.last_time = 0, None, None, None
        self.best_error, self.last_progress = np.inf, None
        self.max_drift = {name: [0., 0.] for name in self.oracle["grasps"]}
        self.failure = None

    def fail(self, reason):
        self.failure = reason
        raise PolicyFailure(f"{self.phase}: {reason}")

    def _grasp(self, obs, name, now, *, diagnostic=False):
        g = self.oracle["grasps"][name]
        world = obs["privileged"]["world"]
        # T_object_tcp measures motion of the grasp point in object coordinates.
        # T_tcp_object translation would count a long object's rotation around
        # an unmoving grasp point as fictitious translational finger slip.
        measured = relative_pose(body_pose(world["bodies"][name]), tcp_pose(obs["robot"][g["arm"]]))
        if name not in self.references:
            self.references[name] = measured
        drift = errors(measured, self.references[name])
        self.max_drift[name] = np.maximum(self.max_drift[name], drift).tolist()
        def violation(reason):
            if not diagnostic:
                self.fail(reason)
            # Stationary diagnosis retains the entire requested two-second
            # window. A violation is latched and can never become a pass.
            if self.failure is None:
                self.failure = reason
        if drift[0] > self.limits.grasp_translation_m or drift[1] > self.limits.grasp_rotation_rad:
            violation(f"grasp_slip:{name}:translation_m={drift[0]:.6g}:rotation_rad={drift[1]:.6g}")
        bilateral = bilateral_contacts(world, name, g["finger_link_indices"])
        if bilateral:
            self.last_contact[name] = now
        elif name not in self.last_contact:
            if now-self.started > self.limits.grasp_acquisition_s:
                violation("bilateral_contact_not_acquired:"+name)
        elif now-self.last_contact[name] > self.limits.contact_grace_s:
            violation("bilateral_contact_lost:"+name)
        return bilateral

    def _guard(self, obs, now):
        world = obs["privileged"]["world"]
        if world["assist_active"] or world["assist_model"] != "none":
            self.fail("unexpected_grasp_assistance")
        for body in world["bodies"].values():
            body_pose(body)
        contacts = world["contacts"]
        # Every rigid contact is present in the evidence; excessive overlap is
        # prohibited even at the fingers. No finite depth is invented for gaps.
        penetration = np.asarray(contacts["penetration"], float)
        if not np.isfinite(penetration).all():
            self.fail("nonfinite_contact_depth")
        if np.any(penetration > self.limits.penetration_m):
            self.fail("contact_penetration_limit")
        if self.last_time is not None and now <= self.last_time:
            self.fail("nonmonotonic_observation_time:new_policy_required_after_rewind")
        self.last_time = now

    def act(self, obs):
        now = float(obs["state"]["sim_time_s"])
        if not np.isfinite(now):
            self.fail("invalid_simulation_time")
        if self.started is None:
            self.started = self.last_progress = now
        self._guard(obs, now)
        self.samples.append(dict(state=dict(obs["state"]), phase=self.phase,
                                 drift=deepcopy(self.max_drift)))
        if self.part == "hold":
            self.phase = "C0_passive_friction_hold"
            # Evaluate every grasp, even when the first one lacks contacts.
            held = [self._grasp(obs, name, now, diagnostic=True) for name in self.oracle["grasps"]]
            self.stable_since = (now if self.stable_since is None else self.stable_since) if all(held) else None
            if self.failure is not None and now-self.started >= self.limits.passive_hold_s-1e-9:
                self.fail(self.failure)
            if now-self.started > self.limits.grasp_acquisition_s+self.limits.passive_hold_s+1.:
                self.fail("passive_hold_timeout")
            if self.stable_since is not None and now-self.stable_since >= self.limits.passive_hold_s-1e-9:
                self.completed = True
                return None
            return {}
        if self.index == len(self.route["waypoints"]):
            return self._finish(obs, now)
        w = self.route["waypoints"][self.index]
        self.phase = w["phase"]
        if now-self.started > w["timeout_s"]:
            self.fail("stage_timeout")
        grasp_ok = [self._grasp(obs, name, now) for name in w.get("grasps", ())]
        robot_errors = [errors(tcp_pose(obs["robot"][arm]), body_pose(target)) for arm, target in w["tcp"].items()]
        object_errors = [errors(body_pose(obs["privileged"]["world"]["bodies"][name]), body_pose(target))
                         for name, target in w.get("bodies", {}).items()]
        error = max((p+a*.1 for p, a in (*robot_errors, *object_errors)), default=0.)
        if error < self.best_error-1e-5:
            self.best_error, self.last_progress = error, now
        reached = all(p <= self.limits.target_translation_m and a <= self.limits.target_rotation_rad
                      for p, a in (*robot_errors, *object_errors)) and all(grasp_ok)
        self.stable_since = (now if self.stable_since is None else self.stable_since) if reached else None
        motion_stopped = all(np.linalg.norm(v) < 1e-8 for v in self.velocity.values())
        if self.stable_since is not None and motion_stopped and now-self.stable_since >= w.get("hold_s", .1)-1e-9:
            self.events.append(dict(phase=self.phase, state=dict(obs["state"]), event="measured_target_reached"))
            self.index += 1
            self.started = self.last_progress = now
            self.best_error, self.stable_since = np.inf, None
            self.velocity = {}  # References finish at zero speed before proceeding.
            return {}
        if not reached and now-self.last_progress > self.limits.stagnation_s:
            self.fail("measured_progress_stalled")
        action = {}
        for arm, target in w["tcp"].items():
            actual = tcp_pose(obs["robot"][arm])
            command = self.commands.setdefault(arm, actual)
            track = errors(actual, command)
            if track[0] > self.limits.tracking_translation_m or track[1] > self.limits.tracking_rotation_rad:
                # Hold the last target. Do not keep pushing or reset command to
                # the lagging measurement; the stagnation gate bounds this wait.
                self.velocity[arm] = np.zeros(6)
                continue
            p, r = command
            tp, tr = body_pose(target)
            delta = np.r_[tp-p, (tr*r.inv()).as_rotvec()]
            old = self.velocity.get(arm, np.zeros(6))
            v = np.zeros(6)
            for sl, speed, acceleration in ((slice(0, 3), self.limits.translation_speed_m_s, self.limits.translation_acceleration_m_s2),
                    (slice(3, 6), self.limits.angular_speed_rad_s, self.limits.angular_acceleration_rad_s2)):
                length = np.linalg.norm(delta[sl])
                # Reserve one discrete control interval of braking distance.
                safe_speed = np.sqrt((acceleration*self.dt/2)**2+2*acceleration*length)-acceleration*self.dt/2
                desired = delta[sl]/max(length, 1e-15)*min(speed, safe_speed, length/self.dt)
                change = desired-old[sl]
                v[sl] = old[sl]+change*min(1., acceleration*self.dt/max(np.linalg.norm(change), 1e-15))
            p, r = p+v[:3]*self.dt, Rotation.from_rotvec(v[3:]*self.dt)*r
            self.commands[arm], self.velocity[arm] = (p, r), v
            action[arm] = dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
        for arm, value in w.get("gripper", {}).items():
            action.setdefault(arm, {})[self.groups[arm]["gripper_field"]] = value
        return action

    def _finish(self, obs, now):
        self.phase = "placement_stability"
        held = [self._grasp(obs, name, now) for name in self.references]
        reached, failure, _ = placement_candidate(obs["privileged"]["world"],
            GoalRegion(**self.oracle["goal_region"]), self.oracle["vertices"],
            self.oracle["targets"], self.oracle["remainder"])
        if failure:
            self.fail("placement:"+failure)
        self.stable_since = (now if self.stable_since is None else self.stable_since) if reached and all(held) else None
        if self.stable_since is not None and now-self.stable_since >= self.oracle["stable_duration_s"]-1e-9:
            self.completed = True
            return None
        if now-self.started > self.oracle["stable_duration_s"]+10.:
            self.fail("placement_not_stable")
        return {}

    def on_segment_end(self, obs, result):
        self.segment_reason = result["reason"]

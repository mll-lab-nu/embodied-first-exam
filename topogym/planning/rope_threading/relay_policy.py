"""Passive EE_ABS relay policy replaying checked IK samples with grasp feedback.

Inputs are the relay samples of plan_rope_threading_ik.py: for every sample a
phase name, the moving hand, both TCP poses and the modelled rope station.
Before a hand pinches, its approach is shifted towards the measured FEM
station so the pads meet the real rope; the shift decays over the first part
of the hold. Grasp acquisition and release are awaited through the assist
state. Only standard actions are emitted; no simulator write.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from .relay_artifact import load_plan


class RopeRelayPolicy:
    def __init__(self, samples, *, speed_m_s=.04, control_dt_s=.025, pinch_opening_m=.0123, free_opening_m=.03,
                 acquire_wait_s=3., release_wait_s=1.5, settle_s=1.5, feedback_decay_m=.10, max_feedback_m=.08,
                 angular_speed_rad_s=.8):
        if not samples or not all(np.isfinite(v) and v > 0 for v in
                (speed_m_s, control_dt_s, acquire_wait_s, release_wait_s, settle_s, feedback_decay_m, angular_speed_rad_s)):
            raise ValueError("Samples must be nonempty and timing/speeds must be finite and positive")
        self.samples = samples
        self.speed, self.dt = float(speed_m_s), float(control_dt_s)
        self.pinch, self.free = float(pinch_opening_m), float(free_opening_m)
        self.acquire_wait = int(round(acquire_wait_s/self.dt))
        self.release_wait = int(round(release_wait_s/self.dt))
        self.settle = int(round(settle_s/self.dt))
        self.decay, self.max_feedback = float(feedback_decay_m), float(max_feedback_m)
        self.index = 0             # next sample to reach
        self.sub, self.substeps = 0, 1
        self.phase = "start"
        self.offset = {"left": np.zeros(3), "right": np.zeros(3)}
        self.offset_origin = {"left": 0., "right": 0.}
        self.waiting = None        # (kind, side, remaining ticks)
        self.targets = {}          # side -> (p, r, opening) currently commanded
        self.expected_holders = set()
        self.angular_speed = float(angular_speed_rad_s)
        self.tracking = dict(feedback_m={}, acquisitions=[], releases=[], failures=[])
        self.done = False
        self.settle_left = None

    def initialize(self, context):
        if context["action_spec"]["mode"] != "EE_ABS":
            raise ValueError("RopeRelayPolicy requires EE_ABS")

    # ----- measurement helpers -------------------------------------------
    @staticmethod
    def _station_position(world, station_m, half_width=.003):
        rope = world["fem"]["rope"]
        s = np.asarray(rope["material_s_m"], float).reshape(-1)
        x = np.asarray(rope["position_m"], float).reshape(-1, 3)
        mask = np.abs(s-station_m) <= half_width
        if not mask.any():
            mask = np.argsort(np.abs(s-station_m))[:24]
        return x[mask].mean(axis=0)

    @staticmethod
    def _binding(world, side):
        return world["grasp"]["hands"][side]["binding"]

    @staticmethod
    def _holding(world, side):
        state = world["grasp"]["hands"][side]
        binding = state["binding"]
        return (state["phase"] == "holding" and state.get("solved_ticks", 0) > 0
                and binding is not None and binding.get("target", [None])[0] == "rope")

    def _pose(self, sample, side):
        row = sample["tcp_"+side]
        return np.asarray(row[:3], float), Rotation.from_quat(np.asarray(row[3:7])[[1, 2, 3, 0]]), float(row[7])

    def _action(self):
        return {side: dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                           gripper_position_m=opening) for side, (p, r, opening) in self.targets.items()}

    # ----- main -----------------------------------------------------------
    def act(self, obs):
        if self.done:
            return None
        world = obs["privileged"]["world"]
        for side in self.expected_holders:
            if not self._holding(world, side):
                raise RuntimeError(f"Rope grasp lost for {side} in {self.phase}")
        if not self.targets:
            for side in ("left", "right"):
                arm = obs["robot"][side]
                self.targets[side] = (np.asarray(arm["tcp_position_world_m"], float),
                                      Rotation.from_quat(np.asarray(arm["tcp_orientation_wxyz"])[[1, 2, 3, 0]]), self.free)
        if self.settle_left is not None:
            self.settle_left -= 1
            if self.settle_left <= 0:
                self.done = True
                return None
            return self._action()
        if self.waiting is not None:
            kind, side, remaining = self.waiting
            binding = self._binding(world, side)
            if (kind == "acquire" and self._holding(world, side)) or (kind == "release" and binding is None):
                self.tracking["acquisitions" if kind == "acquire" else "releases"].append(dict(side=side, index=self.index))
                if kind == "acquire":
                    self.expected_holders.add(side)
                self.waiting = None
            elif remaining <= 0:
                self.tracking["failures"].append(dict(kind=kind, side=side, index=self.index))
                raise RuntimeError(f"grasp assist did not {kind} for {side}")
            else:
                self.waiting = (kind, side, remaining-1)
                return self._action()
        if self.index >= len(self.samples):
            self.settle_left = self.settle
            return self._action()
        sample = self.samples[self.index]
        phase, side = str(sample["phase"]), str(sample["side"])
        kind = phase.split("/")[0].split(":")[0]
        if self.sub == 0:
            # Entering a new sample: decide feedback and gripper events.
            self.phase = phase
            if side:
                if kind in ("transit", "approach") and np.isfinite(sample["station"]).all():
                    measured = self._station_position(world, float(sample["station"][3]))
                    delta = measured-np.asarray(sample["station"][:3])
                    norm = float(np.linalg.norm(delta))
                    if norm > self.max_feedback:
                        delta *= self.max_feedback/norm
                    self.offset[side] = delta
                    self.offset_origin[side] = float(sample["sigma"])
                    self.tracking["feedback_m"][side] = norm
                if kind == "pinch":
                    p, r, _ = self._pose(sample, side)
                    self.targets[side] = (p+self.offset[side], r, self.pinch)
                    self.waiting = ("acquire", side, self.acquire_wait)
                    self.index += 1
                    return self._action()
                if kind == "retreat" and self.targets[side][2] != self.free:
                    p, r, _ = self.targets[side]
                    self.targets[side] = (p, r, self.free)
                    self.waiting = ("release", side, self.release_wait)
                    self.expected_holders.discard(side)
                    return self._action()
            self.segment_start = self.targets[side] if side else None
            p, r, _ = self._pose(sample, side) if side else (None, None, None)
            scale = (max(0., 1.-(float(sample["sigma"])-self.offset_origin[side])/self.decay)
                     if side and kind == "hold" else 1.)
            self.segment_end = (p+self.offset[side]*scale, r) if side else None
            distance = 0. if not side else float(np.linalg.norm(self.segment_end[0]-self.segment_start[0]))
            angle = 0. if not side else float((r*self.segment_start[1].inv()).magnitude())
            self.substeps = max(1, int(np.ceil(distance/(self.speed*self.dt))),
                               int(np.ceil(angle/(self.angular_speed*self.dt))))
        if side:
            p, r = self.segment_end
            start_p, start_r, _ = self.segment_start
            u = (self.sub+1)/self.substeps
            target_p = start_p+u*(p-start_p)
            target_r = Slerp([0., 1.], Rotation.concatenate([start_r, r]))(u)
            current = self.pinch if kind == "hold" else self.free
            self.targets[side] = (target_p, target_r, current)
        self.sub += 1
        if self.sub >= self.substeps:
            self.sub = 0
            self.index += 1
        return self._action()


def load_samples(path):
    return load_plan(path)[0]

"""ALOHA/FEM segment execution and contact-selected, measured-pose assistance.

No grasp sites or routes are chosen by a task planner. Bands uniformly cover
the material curve; actual bilateral surface proximity selects one at runtime.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

from .adapters import GenesisAdapter
from .aloha_contract import validate_action
from .robot_adapter import StableVerdict, array


def rotation(quat):
    return Rotation.from_quat(np.asarray(quat)[[1, 2, 3, 0]])


class RopeGraspBank:
    def __init__(self, surface_checker):
        self.surface_checker = surface_checker
        self.bands = []
        self.owners, self.offsets, self.checkers = {}, {}, {}

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centerline, axis=0), axis=1))]
        indices = np.unique([np.argmin(abs(arc-s)) for s in np.r_[np.arange(0, arc[-1], .006), arc[-1]]])
        self.bands = [FEMRopeAttachment(rope, centerline[i], radius=.008, strength=100.) for i in indices]

    def release(self, side):
        for i in [i for i, owner in self.owners.items() if owner == side]:
            self.bands[i].release()
            del self.owners[i]
            del self.offsets[i]

    def drive(self, ctrl):
        for i, side in self.owners.items():
            arm = ctrl.arms[side]
            self.bands[i]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[i]))

    def try_attach(self, side, ctrl, monitor, distance):
        if side in self.owners.values():
            return False
        arm = ctrl.arms[side]
        center = arm.grasp_center_pos()
        positions = monitor.last_positions
        occupied = set(int(v) for i in self.owners for v in self.bands[i].indices)
        candidates = sorted((np.linalg.norm(positions[b.indices].mean(0)-center), i)
                            for i, b in enumerate(self.bands))
        for gap, i in candidates:
            if gap > .025:
                break
            band = self.bands[i]
            if occupied.intersection(band.indices):
                continue
            faces = monitor.faces[np.all(np.isin(monitor.faces, band.indices), axis=1)]
            if not len(faces):
                continue
            near = True
            for finger in ("left", "right"):
                part = next(p for p in monitor.ccd.parts if p["name"] == f"{side}/{finger}_finger_link")
                points = np.vstack((positions, part["previous"]))
                key = side, finger
                old = self.checkers.get(key)
                if old is None or old[0] != i:
                    if old:
                        old[1].close()
                    checker = self.surface_checker(points, np.vstack((faces, part["faces"]+len(positions))),
                        primary_vertices=np.arange(len(points))<len(positions), cross_only=True)
                    self.checkers[key] = i, checker
                checker = self.checkers[key][1]
                measured = checker.minimum_distance(points, distance+1e-6)
                if checker.initial_intersections or measured is None or measured > distance+1e-6:
                    near = False
                    break
            if near:
                self.offsets[i] = rotation(arm.hand_quat()).inv().apply(positions[band.indices]-arm.hand_pos())
                band._handle.engage(positions[band.indices])
                band.active = True
                self.owners[i] = side
                # Freeze actual finger separation to avoid continued crushing.
                arm.set_gripper(float(arm.gripper_qpos()[0]))
                return True
        return False

    def close(self):
        for _, checker in self.checkers.values():
            checker.close()
        self.checkers.clear()


class FEMRobotAdapter(GenesisAdapter):
    def __init__(self, task, cfg, ctrl, monitor, bank, folder, *, description):
        self.task, self.cfg, self.ctrl, self.monitor, self.bank = task, cfg, ctrl, monitor, bank
        self.tick, self.tracking_ticks = 0, 0
        self.failure = None
        self.armed = {s:False for s in ctrl.arms}
        self.targets = {s:arm.arm_qpos().copy() for s,arm in ctrl.arms.items()}
        self.verdict = StableVerdict(float(cfg.env.sim.dt), duration=2., reason="Released rope is uncrossed and settled for 2 s (pilot)")
        self.audit = Path(folder)/"adapter_events.jsonl"
        super().__init__(scene=task.scene, cameras=task.cameras, description=description,
            validate_action=lambda a:validate_action(a, description["action_schema"]),
            apply_action=self._apply, observe=self._public_observation, evaluate=self._evaluate)

    def _apply(self, action):
        for side, command in action.items():
            arm = self.ctrl.arms[side]
            if "gripper" in command:
                value = command["gripper"]
                if value > arm.current_gripper_qpos+1e-9:
                    self.bank.release(side)
                    self.armed[side] = False
                elif value < arm.current_gripper_qpos-1e-9:
                    self.armed[side] = True
                # env.step(action, steps=N) repeats this command each tick.
                # Keep the measured separation captured at attachment even if
                # the segment keeps requesting closure; opening releases it.
                if side not in self.bank.owners.values():
                    arm.set_gripper(value)
            if "qpos" in command:
                self.targets[side] = np.asarray(command["qpos"])
                arm.set_arm_qpos(command["qpos"])

    def _public_observation(self):
        return dict(robot=self.ctrl.state(), grasp_assistance={s:dict(active=s in self.bank.owners.values(), armed=self.armed[s])
                    for s in self.ctrl.arms})

    def _failure_and_goal(self):
        raise NotImplementedError

    def step(self, action):
        self._apply(action)
        self.bank.drive(self.ctrl)
        self.scene.step()
        self.tick += 1
        failure, reached = self._failure_and_goal()
        error = max(float(np.max(abs(arm.arm_qpos()-self.targets[s]))) for s,arm in self.ctrl.arms.items())
        self.tracking_ticks = self.tracking_ticks+1 if error>.2 else 0
        if self.tracking_ticks*self.scene.dt>.2:
            failure = failure or "Arm tracking error exceeded 0.2 rad for 0.2 s"
        if not failure:
            for side in self.ctrl.arms:
                if self.armed[side] and self.bank.try_attach(side, self.ctrl, self.monitor,
                        float(self.cfg.task.rope.fem.contact_d_hat)):
                    reached = False
                    with self.audit.open("a") as stream:
                        stream.write(json.dumps(dict(tick=self.tick, event="bilateral_surface_assistance", hand=side))+"\n")
        self.verdict.update(self.tick, reached, failure)

    def _evaluate(self):
        return self.verdict.terminal or dict(status="running")

    def close(self):
        self.bank.close()
        self.monitor.close()

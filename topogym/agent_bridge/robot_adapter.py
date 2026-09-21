"""Shared rigid-task runtime: robot ports, contact grasping and tick lifecycle.

Task modules supply their scene, explicit grasp policy and private goal/failure
callback. This module never imports a task's planner, demo or geometry.
"""
import json
from pathlib import Path
import numpy as np

from .adapters import GenesisAdapter
from .aloha_contract import validate_action


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def supported_bodies(fingers, candidates, contacts):
    """Bodies on simple loaded paths between both pads; dangling contacts excluded."""
    nodes = set(fingers) | set(candidates)
    graph = {n: set() for n in nodes}
    for a, b, force in zip(contacts["link_a"], contacts["link_b"], contacts["force"]):
        if a in nodes and b in nodes and np.linalg.norm(force) > .01:
            graph[a].add(b)
            graph[b].add(a)
    first, last = sorted(fingers)
    supported = set()

    def visit(node, path):
        if node == last:
            supported.update(path)
            return
        for peer in graph[node]-set(path):
            visit(peer, path+[peer])

    visit(first, [first])
    return supported & set(candidates)


class StableVerdict:
    """Idempotent reads, contiguous physical ticks, irreversible terminal verdicts."""
    def __init__(self, dt, *, duration=.5, reason="Goal stable for 0.5 s (pilot)"):
        self.dt, self.last_tick, self.stable_ticks = dt, 0, 0
        self.duration, self.reason = duration, reason
        self.terminal = None

    def update(self, tick, reached, failure=None):
        if self.terminal:
            return self.terminal
        if failure:
            self.terminal = dict(status="failed", reason=failure)
        elif tick != self.last_tick:
            self.stable_ticks = self.stable_ticks+1 if reached and tick == self.last_tick+1 else 0
            self.last_tick = tick
            if self.stable_ticks*self.dt >= self.duration:
                self.terminal = dict(status="succeeded", reason=self.reason)
        return self.terminal or dict(status="running")


class RigidRobotAdapter(GenesisAdapter):
    def __init__(self, task, cfg, ctrl, folder, *, description, grasp_candidates,
                 initial_grasps=(), initially_armed=False,
                 success_reason="Goal stable for 0.5 s (pilot)", stable_duration=.5,
                 hand_links=None, finger_links=None, validate_command=None):
        self.task, self.cfg, self.ctrl = task, cfg, ctrl
        self.robot = task.manifest.get("robot")
        self.solver = task.scene.sim.rigid_solver
        self.tick, self.tracking_ticks = 0, 0
        self.verdict = StableVerdict(float(cfg.env.sim.dt), duration=stable_duration, reason=success_reason)
        self.registrations = []
        self.attempt_grasp = {s: initially_armed for s in ctrl.arms}
        self.targets = {s: arm.arm_qpos().copy() for s, arm in ctrl.arms.items()}
        hand_links = hand_links or {s: s+"/gripper_link" for s in ctrl.arms}
        finger_links = finger_links or {s: [f"{s}/{f}_finger_link" for f in ("left", "right")] for s in ctrl.arms}
        self.hands = {s: self.robot.get_link(hand_links[s]).idx for s in ctrl.arms}
        self.fingers = {s: {self.robot.get_link(n).idx for n in finger_links[s]} for s in ctrl.arms}
        self.bodylinks = {b.base_link_idx for b in task.bodies.values()}
        self.candidates = {task.bodies[n].base_link_idx for n in grasp_candidates}
        self.robotlinks = {l.idx for l in self.robot.links if "base_link" not in l.name}
        self.table = task.manifest.get("table").base_link_idx
        self.audit_path = Path(folder)/"adapter_events.jsonl"
        if initial_grasps:
            self._replace([(self.hands[s],
                            task.bodies[n].base_link_idx) for s, n in initial_grasps],
                          "declared initial pregrasp")
        super().__init__(scene=task.scene, cameras=task.cameras, description=description,
            validate_action=validate_command or (lambda a: validate_action(a, description["action_schema"])),
            apply_action=self._apply, observe=self._public_observation, evaluate=self._evaluate)

    def _failure_and_goal(self, contacts):
        """Return (private failure reason or None, goal reached) for current state."""
        raise NotImplementedError


    def _contacts(self):
        values = self.solver.collider.get_contacts(as_tensor=True, to_torch=True)
        return {k: array(values[k]) for k in ("link_a", "link_b", "penetration", "force")}


    def _replace(self, pairs, reason, contacts=None):
        from topogym.robot.grasp_constraints import release_grasps, active_grasps
        if self.registrations:
            release_grasps(self.solver, self.registrations)
        self.registrations = list(pairs)
        for a, b in pairs:
            self.solver.add_weld_constraint(a, b)
        if {tuple(p) for p in active_grasps(self.solver, self.bodylinks)} != set(pairs):
            raise RuntimeError("Auxiliary grasp constraint verification failed")
        with self.audit_path.open("a") as f:
            evidence = [] if contacts is None else [dict(a=int(a), b=int(b), force_N=float(np.linalg.norm(force)))
                for a, b, force in zip(contacts["link_a"], contacts["link_b"], contacts["force"])
                if np.linalg.norm(force) > .01]
            f.write(json.dumps(dict(tick=self.tick, reason=reason, constraints=pairs, contact_evidence=evidence))+"\n")


    def _apply(self, action):
        for side, command in action.items():
            arm = self.ctrl.arms[side]
            if "gripper" in command:
                target = command["gripper"]
                if target > arm.current_gripper_qpos+1e-9:
                    hand = self.hands[side]
                    pairs = [p for p in self.registrations if p[0] != hand]
                    if pairs != self.registrations:
                        self._replace(pairs, "gripper opening: release "+side)
                    self.attempt_grasp[side] = False
                elif target < arm.current_gripper_qpos-1e-9:
                    self.attempt_grasp[side] = bool(self.candidates)
                arm.set_gripper(target)
            if "qpos" in command:
                self.targets[side] = np.asarray(command["qpos"])
                arm.set_arm_qpos(command["qpos"])


    def _public_observation(self):
        hands = self.hands
        return dict(robot=self.ctrl.state(), grasp_assistance={s: dict(
            active=any(a == hand for a, _ in self.registrations), armed=self.attempt_grasp[s])
            for s, hand in hands.items()})


    def step(self, action):
        self._apply(action)
        self.scene.step()
        self.tick += 1
        contacts = self._contacts()
        failure, reached = self._failure_and_goal(contacts)
        error = max(float(np.max(np.abs(arm.arm_qpos()-self.targets[s]))) for s, arm in self.ctrl.arms.items())
        self.tracking_ticks = self.tracking_ticks+1 if error > .2 else 0
        if self.tracking_ticks*self.scene.dt > .2:
            failure = failure or "Arm tracking error >0.2 rad for more than 0.2 s"
        if not failure:
            pairs = list(self.registrations)
            for side in self.ctrl.arms:
                if self.attempt_grasp[side]:
                    hand = self.hands[side]
                    for body in sorted(supported_bodies(self.fingers[side], self.candidates, contacts)):
                        if (hand, body) not in pairs:
                            pairs.append((hand, body))
            if pairs != self.registrations:
                self._replace(pairs, "loaded bilateral contact", contacts)
                reached = False
        # Latch failures without throwing: Session still saves all this tick's views.
        self.verdict.update(self.tick, reached, failure)


    def _evaluate(self):
        if self.tick == 0 and not self.verdict.terminal:
            failure, _ = self._failure_and_goal(self._contacts())
            self.verdict.update(0, False, failure)
        return self.verdict.terminal or dict(status="running")


class AlohaRigidAdapter(RigidRobotAdapter):
    """ALOHA naming and action defaults retained for existing task adapters."""

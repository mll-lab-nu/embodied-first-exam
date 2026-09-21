"""Compact friction-grasp episode on the shared Panda execution loop."""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.agent_bridge.panda_contract import PandaPort, validate_action
from topogym.agent_bridge.robot_adapter import RigidRobotAdapter, array
from topogym.tasks._rigid_geometry import disk_linking_number
from .agent_scene import load_seed, prepare_scene
from .agent_spec import describe_task

ROOT = Path(__file__).resolve().parents[3]


def configuration(*, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    seed = load_seed()
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="buzz_wire_3d_preview")
    cfg.task = OmegaConf.create(dict(variant=seed["geometry"]["template_id"],
        origin_xy_m=seed["origin_xy_m"], yaw_deg=seed["yaw_deg"],
        geometry=seed["geometry"], physics=seed["physics"]))
    cfg.robot_control = OmegaConf.create(seed["robot_control"])
    cfg.env.robot_mount = OmegaConf.create(seed["robot_mount"])
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.env.sim.dt, cfg.env.sim.substeps = seed["control_dt_s"], seed["substeps"]
    cfg.env.sim.gravity, cfg.env.genesis.precision = [0., 0., -9.81], "64"
    wrist = OmegaConf.to_container(cfg.env.cameras.wrist, resolve=True)
    wrist.update(res=list(resolution), fov=80, near=.005)
    # A fixed side mount shows the aperture instead of looking along its plane.
    # It moves only with the hand, never tracks the private wand pose.
    wrist["attach"].update(offset_pos=[.05, -.12, .025],
        offset_lookat=[0., 0., .17], offset_up=[1., 0., 0.])
    cfg.env.cameras = OmegaConf.create(dict(
        agentview=dict(res=list(resolution), pos=[.95, -1.10, 1.72],
            lookat=[-.24, 0., 1.14], up=[0., 0., 1.], fov=48, near=.005, far=12.),
        front_oblique=dict(res=list(resolution), pos=[.95, 1.10, 1.72],
            lookat=[-.24, 0., 1.14], up=[0., 0., 1.], fov=48, near=.005, far=12.),
        wrist=wrist))
    cfg.run.viewer, cfg.run.include_robot = False, True
    return cfg, seed


class RailTraversal:
    """Track measured aperture crossings of the physical rail, never a pose guide."""
    def __init__(self, rail, radius, base_z, initial_center, initial_normal):
        self.rail, self.radius = np.asarray(rail), radius
        self.lengths = np.linalg.norm(np.diff(self.rail, axis=0), axis=1)
        self.arc = np.r_[0., np.cumsum(self.lengths)]
        self.closure = np.vstack((self.rail, [*self.rail[-1, :2], base_z], [*self.rail[0, :2], base_z]))
        delta = np.diff(self.rail, axis=0)
        vertical = (np.linalg.norm(delta[:, :2], axis=1)/self.lengths < .02) & (delta[:, 2] < 0)
        index = len(delta)-1
        if not vertical[index]:
            raise ValueError("Buzz Wire baseline needs a final downward post")
        while index > 0 and vertical[index-1]:
            index -= 1
        self.terminal_start = self.arc[index]
        start = self.crossings(initial_center, initial_normal)
        if len(start) != 1 or abs(disk_linking_number(initial_center, initial_normal, radius, self.closure)) != 1:
            raise ValueError("Initial ring must thread the physical wire exactly once")
        self.last_s = float(start[0])
        self.highest_s, self.terminal_reached = self.last_s, False

    def crossings(self, center, normal):
        p, q = self.rail[:-1]-center, self.rail[1:]-center
        a, b = p@normal, q@normal
        mask = ((a <= 0) & (b > 0)) | ((a > 0) & (b <= 0))
        ids = np.flatnonzero(mask)
        t = a[mask]/(a[mask]-b[mask])
        inside = np.linalg.norm(p[mask]+t[:, None]*(q[mask]-p[mask]), axis=1) < self.radius
        return self.arc[ids[inside]]+t[inside]*self.lengths[ids[inside]]

    def update(self, center, normal):
        if abs(disk_linking_number(center, normal, self.radius, self.closure)) != 1:
            return "Ring lost the threaded state"
        arcs = self.crossings(center, normal)
        if not len(arcs):
            return "No aperture crossing on the playable wire"
        current = float(arcs[np.argmin(abs(arcs-self.last_s))])
        if abs(current-self.last_s) > .03:
            return "Nonlocal wire crossing jump exceeded 30 mm per control step"
        self.last_s = current
        self.highest_s = max(self.highest_s, current)
        self.terminal_reached |= current >= self.terminal_start
        return None


class BuzzWireAdapter(RigidRobotAdapter):
    def __init__(self, task, cfg, controller, folder):
        self.fixed = [(body, array(body.get_pos()).copy(), array(body.get_quat()).copy())
                      for body in (task.wire, task.base)]
        self.rail = task.origin+task.rotation.apply(task.route.rail)
        normal = Rotation.from_quat(array(task.wand.get_quat())[[1, 2, 3, 0]]).apply([0., 0., 1.])
        self.traversal = RailTraversal(self.rail, task.route.layout.loop_radius_m,
            task.origin[2]+task.route.layout.base_size_m[2]/2, array(task.wand.get_pos()), normal)
        self.mass = float(task.geometry_report["wand_mass_kg"])
        self.com = np.asarray(task.geometry_report["wand_center_of_mass_m"])
        self.inertia = np.asarray(task.geometry_report["wand_inertia_kg_m2"])
        self.passive_energy = None
        self.evidence_path, self.last_audit_tick = Path(folder)/"adapter_evaluation.jsonl", -1
        spec = describe_task(cfg)
        super().__init__(task, cfg, PandaPort(controller), folder, description=spec,
            grasp_candidates=(), hand_links={"arm": "hand"},
            finger_links={"arm": ["left_finger", "right_finger"]},
            validate_command=lambda a: validate_action(a, spec["action_schema"]),
            stable_duration=1., success_reason="Wire traversed, ring released and resting at orange stop for 1 s (pilot)")
        self.robotlinks = {link.idx for link in self.robot.links if link.idx != self.robot.base_link_idx}
        self.fixtures = {task.wire.base_link_idx, task.base.base_link_idx, self.table}

    def _failure_and_goal(self, contacts):
        wand = self.task.wand
        p, q, v, w = (array(getattr(wand, "get_"+k)()) for k in ("pos", "quat", "vel", "ang"))
        a, b, pen, force = (contacts[k] for k in ("link_a", "link_b", "penetration", "force"))
        if not np.isfinite(np.r_[p, q, v, w, pen, force.ravel(), array(self.robot.get_qpos()).ravel()]).all() or np.linalg.norm(q) < 1e-12:
            return "Non-finite or invalid physical state", False
        for body, pos, quat in self.fixed:
            now, rotation = array(body.get_pos()), array(body.get_quat())
            if (not np.isfinite(np.r_[now, rotation]).all() or np.linalg.norm(now-pos)>1e-6
                    or min(np.linalg.norm(rotation-quat), np.linalg.norm(rotation+quat))>1e-6):
                return "Fixed wire/base moved", False
        if p[2] < self.task.origin[2]-.1:
            return "Ring fell below tabletop", False
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        failure = self.traversal.update(p, r.apply([0., 0., 1.]))
        if failure:
            return failure, False
        norms = np.linalg.norm(force, axis=-1)
        loaded = (pen > 0) | (norms > .001)
        bid, wire = wand.base_link_idx, self.task.wire.base_link_idx
        wa = a == bid
        wb = b == bid
        ra, rb = np.isin(a, list(self.robotlinks)), np.isin(b, list(self.robotlinks))
        robot_wand = (wa & rb) | (wb & ra)
        wire_wand = (wa & (b == wire)) | (wb & (a == wire))
        released = not np.any(loaded & robot_wand)
        terminal = self.traversal.terminal_reached and self.traversal.last_s >= self.traversal.terminal_start
        if np.any(loaded & wire_wand) and not (terminal and released):
            return "Wire touch outside the released terminal post phase", False
        if pen[wa | wb].max(initial=0) > .0005:
            return "Wand contact penetration exceeded 0.5 mm", False
        rf = (ra & np.isin(b, list(self.fixtures))) | (rb & np.isin(a, list(self.fixtures)))
        if pen[rf | (ra & rb)].max(initial=0) > .0002:
            return "Robot fixture/self penetration exceeded 0.2 mm", False
        pads = list(self.fingers["arm"])
        nonpad = robot_wand & ~((wa & np.isin(b, pads)) | (wb & np.isin(a, pads)))
        if np.any(loaded & nonpad):
            return "A non-pad robot link contacted the wand", False
        if np.linalg.norm(v) > 3 or np.linalg.norm(w) > (150 if terminal and released else 30):
            return "Unstable ring speed", False
        if terminal and released:
            cv = v+np.cross(w, r.apply(self.com))
            bw = r.inv().apply(w)
            energy = float(.5*self.mass*(cv@cv)+.5*bw@self.inertia@bw
                +self.mass*9.81*(p[2]+r.apply(self.com)[2]-self.task.origin[2]))
            if self.passive_energy is None:
                self.passive_energy = energy
            if energy > self.passive_energy+.001:
                return "Passive terminal energy grew by more than 1 mJ", False
        else:
            self.passive_energy = None
        upward = float(np.sum(force[wire_wand, 2]*np.where(b[wire_wand] == bid, 1., -1.)))
        at_end = (self.traversal.last_s > self.traversal.arc[-1]-.05
                  and np.linalg.norm(p-self.rail[-1]) < .05)
        other = (wa | wb) & ~wire_wand
        reached = bool(terminal and at_end and released and upward > .01
            and not np.any(loaded & other) and np.linalg.norm(v)<.002 and np.linalg.norm(w)<.02)
        if self.last_audit_tick != self.tick:
            fingers = [int(f) for f in pads if np.any(loaded & (((a == f) & wb) | ((b == f) & wa)))]
            with self.evidence_path.open("a") as stream:
                stream.write(json.dumps(dict(tick=self.tick, wire_arc_m=self.traversal.last_s,
                    terminal_post=bool(terminal), released=bool(released), finger_contact_links=fingers,
                    assist_active=bool(self.registrations), goal_reached=reached))+"\n")
            self.last_audit_tick = self.tick
        return None, reached


def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    import genesis as gs
    from omegaconf import OmegaConf
    from topogym.robot.factory import initialize_robot_controller
    from topogym.robot.gripper import robotiq_joint_targets
    from .scene import BuzzWireSceneBuilder
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    cfg, seed = configuration(backend=backend, renderer=renderer, resolution=resolution)
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=folder/"scene", include_robot=True, static_assets=prepare_scene)
    controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, reset_home=False)
    qpos = array(controller.robot.get_qpos()).copy()
    qpos[:7] = seed["initial_arm_qpos"]
    for name, value in robotiq_joint_targets(seed["initial_gripper_half_gap_m"]).items():
        name = {"right_driver_joint": "finger_joint1", "left_driver_joint": "finger_joint2"}.get(name, "r85_"+name)
        qpos[controller.robot.get_joint(name).qs_idx_local[0]] = value
    controller.robot.set_qpos(qpos, zero_velocity=True)
    controller.robot.control_dofs_position(qpos[:7], controller.arm_dofs)
    controller.set_gripper(seed["initial_gripper_command_m"], steps=0)
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return BuzzWireAdapter(task, cfg, controller, folder)

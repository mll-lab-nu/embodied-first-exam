"""CLASSIC fixed-instance initializer and private verdict on the shared robot loop."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.agent_bridge.robot_adapter import RigidRobotAdapter, array
from topogym.agent_bridge.panda_contract import PandaPort, validate_action
from .agent_spec import describe_task

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT/"assets/tasks/hedgehog_in_cage/classic_3star"


def configuration(*, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    seed = json.loads((ASSETS/"agent_initial_state.json").read_text())
    if hashlib.sha256((ASSETS/"template.json").read_bytes()).hexdigest() != seed["template_sha256"]:
        raise ValueError("Fixed initialization has a different geometry hash")
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="hedgehog_in_cage_classic_preview")
    cfg.task = OmegaConf.create(seed["task"])
    cfg.robot_control = OmegaConf.create(seed["robot_control"])
    cfg.env.robot_mount = OmegaConf.create(seed["robot_mount"])
    cfg.env.cameras = OmegaConf.create(seed["cameras"])
    for camera in cfg.env.cameras.values():
        camera.res = list(resolution)
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.env.sim.dt, cfg.env.sim.substeps = .005, 10
    cfg.env.sim.gravity = [0., 0., -9.81]
    cfg.run.viewer = False
    return cfg, seed


class HedgehogAdapter(RigidRobotAdapter):
    def __init__(self, task, cfg, controller, folder):
        task.bodies = {"hedgehog_ball": task.hedgehog}
        self.ball_vertices = trimesh.load(Path(folder)/"scene/hedgehog.obj", force="mesh").vertices
        cage_vertices = trimesh.load(Path(folder)/"scene/cage.obj", force="mesh").vertices
        self.cage_pos, self.cage_quat = array(task.cage.get_pos()), array(task.cage.get_quat())
        world = Rotation.from_quat(self.cage_quat[[1, 2, 3, 0]]).apply(cage_vertices)+self.cage_pos
        self.cage_bounds = np.array([world.min(0), world.max(0)])
        self.rest_origin = None
        spec = describe_task(cfg)
        super().__init__(task, cfg, PandaPort(controller), folder, description=spec,
            grasp_candidates=("hedgehog_ball",), initially_armed=True,
            hand_links={"arm": "hand"}, finger_links={"arm": ["left_finger", "right_finger"]},
            validate_command=lambda action: validate_action(action, spec["action_schema"]),
            stable_duration=2., success_reason="Hedgehog outside cage, released and resting on table for 2 s (pilot)")
        self.robotlinks = {l.idx for l in self.robot.links if l.idx != self.robot.base_link_idx}
        self.fixtures = {task.cage.base_link_idx, task.manifest.get("hedgehog_mount").base_link_idx, self.table}
        self.fixtures.update(task.manifest.get(f"hedgehog_mount_bolt_{i}").base_link_idx for i in range(4))

    def _failure_and_goal(self, contacts):
        ball, cage = self.task.hedgehog, self.task.cage
        bid, cid = ball.base_link_idx, cage.base_link_idx
        pos, quat, vel, ang = (array(getattr(ball, "get_"+f)()) for f in ("pos", "quat", "vel", "ang"))
        if not np.isfinite(np.r_[pos, quat, vel, ang]).all():
            return "Non-finite physical state", False
        if (np.linalg.norm(array(cage.get_pos())-self.cage_pos) > 1e-6 or
                1-abs(np.dot(array(cage.get_quat()), self.cage_quat)) > 1e-8):
            return "Fixed cage pose changed", False
        floor = self.task.tabletop.frames.table_surface_origin
        if pos[2] < floor[2]-.1:
            return "Hedgehog fell below the tabletop", False
        a, b, pen = (contacts[k] for k in ("link_a", "link_b", "penetration"))
        ball_contact = (a == bid) | (b == bid)
        ball_cage = ball_contact & ((a == cid) | (b == cid))
        rf = (np.isin(a, list(self.robotlinks)) & np.isin(b, list(self.fixtures))) | (np.isin(b, list(self.robotlinks)) & np.isin(a, list(self.fixtures)))
        rr = np.isin(a, list(self.robotlinks)) & np.isin(b, list(self.robotlinks))
        if pen[ball_cage | rf].max(initial=0) > .00015:
            return "Cage/robot-fixture penetration exceeded 0.15 mm", False
        if pen[ball_contact | rr].max(initial=0) > .001:
            return "Ball contact or robot self-penetration exceeded 1 mm", False
        vertices = Rotation.from_quat(quat[[1, 2, 3, 0]]).apply(self.ball_vertices)+pos
        bounds = np.array([vertices.min(0), vertices.max(0)])
        separation = np.maximum(bounds[0]-self.cage_bounds[1], self.cage_bounds[0]-bounds[1]).max()
        size = np.asarray(self.cfg.env.world.table.size)
        on_surface = bool(np.all(bounds[0, :2] >= np.asarray(floor)[:2]-size[:2]/2)
                          and np.all(bounds[1, :2] <= np.asarray(floor)[:2]+size[:2]/2))
        forces = np.linalg.norm(contacts["force"], axis=-1)
        on_table = ((a == bid) & (b == self.table)) | ((b == bid) & (a == self.table))
        released = not any(bid in pair for pair in self.registrations)
        reached = bool(separation > .005 and on_surface and released and forces[on_table].sum() > .01
            and not np.any(forces[ball_contact & ~on_table] > .001)
            and np.linalg.norm(vel) < .001 and np.linalg.norm(ang) < np.deg2rad(.5))
        if not reached:
            self.rest_origin = None
        elif self.rest_origin is None:
            self.rest_origin = pos.copy()
        elif np.linalg.norm(pos-self.rest_origin) > .0002:
            self.rest_origin = None
            reached = False
        return None, reached


def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    import genesis as gs
    from omegaconf import OmegaConf
    from topogym.robot.factory import initialize_robot_controller
    from topogym.robot.gripper import robotiq_joint_targets
    from .scene import HedgehogSceneBuilder
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    cfg, seed = configuration(backend=backend, renderer=renderer, resolution=resolution)
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = HedgehogSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=folder/"scene")
    controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, reset_home=False)
    q = array(controller.robot.get_qpos()).copy()
    q[:7] = seed["arm_qpos"]
    for name, value in robotiq_joint_targets(.0054).items():
        name = {"right_driver_joint": "finger_joint1", "left_driver_joint": "finger_joint2"}.get(name, "r85_"+name)
        q[controller.robot.get_joint(name).qs_idx_local[0]] = value
    controller.robot.set_qpos(q, zero_velocity=True)
    controller.robot.control_dofs_position(q[:7], controller.arm_dofs)
    controller.set_gripper(.0044, steps=0)
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return HedgehogAdapter(task, cfg, controller, folder)

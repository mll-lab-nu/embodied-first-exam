"""Keyhole-specific initialization and evaluator; shared robot runtime owns actions."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.agent_bridge.robot_adapter import AlohaRigidAdapter, array
from .agent_spec import describe_task
from .collision import CompoundCollision

ROOT = Path(__file__).resolve().parents[3]


class KeyholeAdapter(AlohaRigidAdapter):
    def __init__(self, task, cfg, ctrl, folder):
        # Work in each loaded body's own frame, without solution/canonical-path code.
        origins = {b["name"]: np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]}
        cells = {b.name: [m.copy().apply_translation(-origins[b.name]) for m in b.collision]
                 for b in task.assembly.bodies}
        self.collision = CompoundCollision(cells["keyhole_gold"], cells["keyhole_silver"])
        super().__init__(task, cfg, ctrl, folder, description=describe_task(cfg),
            grasp_candidates=("keyhole_gold", "keyhole_silver"), initially_armed=True,
            success_reason="Keyhole pieces separated and stable for 0.5 s; holding allowed (pilot)")

    def _failure_and_goal(self, contacts):
        a, b, pen = (contacts[k] for k in ("link_a", "link_b", "penetration"))
        involved = np.isin(a, list(self.bodylinks)) | np.isin(b, list(self.bodylinks))
        rr = np.isin(a, list(self.robotlinks)) & np.isin(b, list(self.robotlinks))
        rt = ((a == self.table) & np.isin(b, list(self.robotlinks))) | ((b == self.table) & np.isin(a, list(self.robotlinks)))
        if float(pen[involved | rr | rt].max(initial=0)) > .001:
            return "Puzzle/robot collision penetration exceeded 1 mm", False
        poses, quiet = [], True
        for name in ("keyhole_gold", "keyhole_silver"):
            body = self.task.bodies[name]
            pos, quat, vel, ang = (array(getattr(body, "get_"+field)()) for field in ("pos", "quat", "vel", "ang"))
            if not np.isfinite(np.r_[pos, quat, vel, ang]).all():
                return "Non-finite physical state", False
            if pos[2] < self.task.tabletop.frames.table_surface_origin[2]-.1:
                return "A puzzle piece fell below the tabletop", False
            poses.append((pos, Rotation.from_quat(quat[[1, 2, 3, 0]]).as_matrix()))
            quiet = quiet and np.linalg.norm(vel) < .001 and np.linalg.norm(ang) < .02
        (pg, rg), (ps, rs) = poses
        gap = self.collision.gap(rg.T@rs, rg.T@(ps-pg))
        if gap < -.0005:
            return "Interpiece SAT penetration exceeded 0.5 mm", False
        return None, bool(gap > .02 and quiet)


def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 360)):
    import genesis as gs
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from topogym.robot.aloha import AlohaDualArmController
    from topogym.world.aloha_cameras import configure_aloha_rig
    from .geometry import ASSET_ROOT
    from .scene import build_scene

    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="cast_keyhole_aloha")
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.run.include_robot, cfg.run.viewer = True, False
    cfg.env.sim.dt, cfg.env.sim.substeps = .001, 4
    cfg.robot_control.controller.kp = [100000.]*6+[2000.]
    cfg.robot_control.controller.kv = [2000.]*6+[124.]
    configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=20)
    seed = json.loads((ASSET_ROOT/"agent_initial_state.json").read_text())
    if (hashlib.sha256((ASSET_ROOT/"template.json").read_bytes()).hexdigest() != seed["template_sha256"]
            or float(cfg.task.scale) != seed["scene_scale"]):
        raise ValueError("Initialization belongs to a different geometry/scale")
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, folder/"scene")
    robot = task.manifest.get("robot")
    ctrl = AlohaDualArmController(task.scene, robot, cfg.robot_control)
    ctrl.configure()
    robot.set_qpos(np.asarray(seed["qpos"]), zero_velocity=True)
    # Initialization-only canonical-to-loaded transform; no motion file is read.
    rx = Rotation.from_euler("x", 90, degrees=True).as_matrix()
    rz = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    transforms = {"keyhole_gold": (rz@rx, np.array([0, 0, task.assembly.template["gold_offset_z"]])*task.assembly.unit),
                  "keyhole_silver": (rx, np.zeros(3))}
    for item in task.asset_report["bodies"]:
        name = item["name"]
        pose, body = seed["bodies"][name], task.bodies[name]
        a, b = transforms[name]
        rotation = Rotation.from_quat(pose["quat"]).as_matrix()@a.T
        position = np.asarray(cfg.env.robot_mount.pos)+pose["pos"]+rotation@(np.asarray(item["origin_m"])-b)
        body.set_pos(position)
        body.set_quat(Rotation.from_matrix(rotation).as_quat()[[3, 0, 1, 2]])
        body.zero_all_dofs_velocity()
    for arm in ctrl.arms.values():
        arm.set_arm_qpos(arm.arm_qpos())
        arm.set_gripper(.0105)
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return KeyholeAdapter(task, cfg, ctrl, folder)

"""Fixed Claw initialization and private verdict on the shared ALOHA runtime."""
import hashlib
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.agent_bridge.robot_adapter import AlohaRigidAdapter, array
from .agent_spec import describe_task
from .collision import ClawCollision
from .geometry import ASSET_ROOT

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_SHA256 = "4a73079c08627f96a962c859844029d4c9d794f63a669a37725d5c2856a45d8b"


def configuration(*, backend="cpu", renderer="rasterizer", resolution=(640, 360)):
    from hydra import compose, initialize_config_dir
    from topogym.world.aloha_cameras import configure_aloha_rig
    # Static geometry, fixtures, FK and initial poses only; no recorded motion.
    if hashlib.sha256((ASSET_ROOT/"reference_scene.json").read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Claw static initialization checksum mismatch")
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="interlocked_claws_physics")
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.run.include_robot, cfg.run.viewer = True, False
    configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=20)
    # These tall suspended pieces are cropped by the canonical tabletop views.
    # Publish task-specific fixed mounts; retain the standard wrist mounts.
    cfg.env.cameras.cam_high.pos = [-.135, -.35, 2.12]
    cfg.env.cameras.cam_high.lookat = [-.135, -.10, 1.22]
    cfg.env.cameras.cam_high.up = [0., 0., 1.]
    cfg.env.cameras.cam_high.fov = 60.
    cfg.env.cameras.cam_low.pos = [.60, -1., 1.65]
    cfg.env.cameras.cam_low.lookat = [-.135, -.10, 1.25]
    cfg.env.cameras.cam_low.up = [0., 0., 1.]
    cfg.env.cameras.cam_low.fov = 50.
    return cfg


class ClawsAdapter(AlohaRigidAdapter):
    def __init__(self, task, cfg, ctrl, folder):
        self.meshes = [b.mesh for b in task.assembly.bodies]
        self.collision = ClawCollision(task.assembly)
        self.fixture_bodies = [task.manifest.get(n) for n in task.loading_report["fixtures"]]
        self.fixtures = {b.base_link_idx for b in self.fixture_bodies}
        self.fixed_poses = [(array(b.get_pos()).copy(), array(b.get_quat()).copy()) for b in self.fixture_bodies]
        self.obstacles = self.fixtures | {task.manifest.get(n).base_link_idx
            for n in ("left_mounting_block", "right_mounting_block")}
        super().__init__(task, cfg, ctrl, folder, description=describe_task(cfg),
            grasp_candidates=("claw_0", "claw_1"),
            initial_grasps=(("left", "claw_0"), ("right", "claw_1")),
            stable_duration=1., success_reason="Claws completely separated and held still for 1 s (pilot v2)")

    def _failure_and_goal(self, contacts):
        a, b, pen, force = (contacts[k] for k in ("link_a", "link_b", "penetration", "force"))
        if not np.isfinite(np.r_[pen, force.ravel(), array(self.robot.get_qpos()).ravel()]).all():
            return "Non-finite physical/contact state", False
        involved = np.isin(a, list(self.bodylinks)) | np.isin(b, list(self.bodylinks))
        ra, rb = np.isin(a, list(self.robotlinks)), np.isin(b, list(self.robotlinks))
        fixed = list(self.obstacles | {self.table})
        monitored = involved | (ra & rb) | (ra & np.isin(b, fixed)) | (rb & np.isin(a, fixed))
        if pen[monitored].max(initial=0) > .001:
            return "Puzzle/robot collision penetration exceeded 1 mm", False
        for body, (pos, quat) in zip(self.fixture_bodies, self.fixed_poses):
            p, q = array(body.get_pos()), array(body.get_quat())
            if not np.isfinite(np.r_[p, q]).all():
                return "Non-finite fixture state", False
            if np.linalg.norm(p-pos) > 1e-6 or min(np.linalg.norm(q-quat), np.linalg.norm(q+quat)) > 1e-6:
                return "Fixed support fixture moved", False

        poses, bounds, quiet = [], [], True
        for name, mesh in zip(("claw_0", "claw_1"), self.meshes):
            body = self.task.bodies[name]
            pos, quat, vel, ang = (array(getattr(body, "get_"+k)()) for k in ("pos", "quat", "vel", "ang"))
            if not np.isfinite(np.r_[pos, quat, vel, ang]).all() or np.linalg.norm(quat) < 1e-12:
                return "Non-finite or invalid piece state", False
            if pos[2] < self.task.tabletop.frames.table_surface_origin[2]-.1:
                return "A puzzle piece fell below the tabletop", False
            pose = np.eye(4)
            pose[:3, :3] = Rotation.from_quat(quat[[1, 2, 3, 0]]).as_matrix()
            pose[:3, 3] = pos
            vertices = mesh.vertices@pose[:3, :3].T+pos
            poses.append(pose)
            bounds.append(np.array([vertices.min(0), vertices.max(0)]))
            quiet &= np.linalg.norm(vel) < .005 and np.linalg.norm(ang) < .05

        gap = self.collision.clearance(poses)
        if not np.isfinite(gap):
            return "Non-finite triangle clearance", False
        if gap < 0:
            depth = self.collision.contact_depth()
            if not np.isfinite(depth) or depth > .00015:
                return "Interpiece triangle contact depth exceeded 0.15 mm", False
            return None, False
        # Each mesh is a connected closed solid. After ruling out intersecting
        # surfaces, test a vertex from each body to reject full containment.
        for i, j in ((0, 1), (1, 0)):
            point = poses[i][:3, :3]@self.meshes[i].vertices[0]+poses[i][:3, 3]
            if np.all(point > bounds[j][0]) and np.all(point < bounds[j][1]):
                local = (point-poses[j][:3, 3])@poses[j][:3, :3]
                if self.meshes[j].contains([local])[0]:
                    return "One puzzle piece is fully contained in the other", False
        separation = np.maximum(bounds[0][0]-bounds[1][1], bounds[1][0]-bounds[0][1]).max()
        return None, bool(separation > .02 and quiet)


def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 360)):
    import genesis as gs
    from omegaconf import OmegaConf
    from .scene import build_scene
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    cfg = configuration(backend=backend, renderer=renderer, resolution=resolution)
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, folder/"scene")
    # build_scene sets only the static initial pose (zero settling steps).
    # Retain that pose as targets without advancing physics.
    ctrl = task.controller
    for arm in ctrl.arms.values():
        arm.set_arm_qpos(arm.arm_qpos())
        arm.set_gripper(float(arm.gripper_qpos()[0]))
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return ClawsAdapter(task, cfg, ctrl, folder)

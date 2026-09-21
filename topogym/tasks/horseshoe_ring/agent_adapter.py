"""Live horseshoe task: initialization and private task verdict only."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

# Compatibility exports retained for existing tests/tools.
from topogym.agent_bridge.robot_adapter import AlohaRigidAdapter, array, supported_bodies, StableVerdict
from .agent_spec import describe_task

ROOT = Path(__file__).resolve().parents[3]


class HorseshoeAdapter(AlohaRigidAdapter):
    def __init__(self, task, cfg, ctrl, folder):
        self.origins = {b["name"]: np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]}
        self.vertices = {b.name: b.visual.vertices-self.origins[b.name] for b in task.assembly.bodies}
        super().__init__(task, cfg, ctrl, folder, description=describe_task(cfg),
            grasp_candidates=("horseshoe_left", "horseshoe_right", "target_ring"),
            initial_grasps=(("left", "horseshoe_left"), ("right", "horseshoe_right")),
            success_reason="Ring separated, released and resting on table for 0.5 s (pilot)")

    def _failure_and_goal(self, contacts):
        from .demo import current_loops
        a, b, pen = (contacts[k] for k in ("link_a", "link_b", "penetration"))
        involved = np.isin(a, list(self.bodylinks)) | np.isin(b, list(self.bodylinks))
        rr = np.isin(a, list(self.robotlinks)) & np.isin(b, list(self.robotlinks))
        rt = ((a == self.table) & np.isin(b, list(self.robotlinks))) | ((b == self.table) & np.isin(a, list(self.robotlinks)))
        if float(pen[involved | rr | rt].max(initial=0)) > .001:
            return "Puzzle/robot collision penetration exceeded 1 mm", False
        bounds = {}
        table_z = self.task.tabletop.frames.table_surface_origin[2]
        for name, body in self.task.bodies.items():
            pos, quat = array(body.get_pos()), array(body.get_quat())
            if not np.isfinite(np.r_[pos, quat, array(body.get_vel()), array(body.get_ang())]).all():
                return "Non-finite physical state", False
            if pos[2] < table_z-.1:
                return "A puzzle body fell below the tabletop", False
            vertices = Rotation.from_quat(quat[[1, 2, 3, 0]]).apply(self.vertices[name])+pos
            bounds[name] = np.array([vertices.min(0), vertices.max(0)])
        loops = current_loops(self.task)
        if any(abs(int(loops[x].linking(loops[y]))) != 1 for x, y in self.task.assembly.edges):
            return "Physical chain/eye connection lost", False
        ring = self.task.bodies["target_ring"]
        rid = ring.base_link_idx
        target = bounds.pop("target_ring")
        obstacle = np.array([np.min([v[0] for v in bounds.values()], axis=0), np.max([v[1] for v in bounds.values()], axis=0)])
        separation = np.maximum(target[0]-obstacle[1], obstacle[0]-target[1]).max()
        force = np.linalg.norm(contacts["force"], axis=-1)
        on_table = ((a == rid) & (b == self.table)) | ((b == rid) & (a == self.table))
        other = ((a == rid) | (b == rid)) & ~on_table
        released = not any(rid in p for p in self.registrations)
        reached = (separation > .02 and released and force[on_table].sum() > .01
            and not np.any(force[other] > .001) and np.linalg.norm(array(ring.get_vel())) < .01
            and np.linalg.norm(array(ring.get_ang())) < .2)
        return None, bool(reached)



def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 360)):
    import genesis as gs
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from topogym.robot.aloha import AlohaDualArmController
    from topogym.world.aloha_cameras import configure_aloha_rig
    from .scene import build_scene
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="horseshoe_ring_aloha")
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.env.sim.dt, cfg.env.sim.substeps, cfg.env.sim.gravity = .002, 4, [0., 0., -9.81]
    cfg.run.include_robot, cfg.run.viewer = True, False
    cfg.robot_control.controller.kp = [10000, 18000, 14000, 6000, 4000, 2500, 2000]
    cfg.robot_control.controller.kv = [200, 300, 250, 100, 80, 40, 124]
    configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=20)
    # The canonical front mount sees the initially vertical target ring edge-on.
    # A declared oblique low view complements the overhead/wrist views.
    cfg.env.cameras.cam_low.pos = [.30, -.45, 1.15]
    cfg.env.cameras.cam_low.lookat = [-.1356786, .05, 1.12]
    cfg.env.cameras.cam_low.up = [0., 0., 1.]
    cfg.env.cameras.cam_low.fov = 50.
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, folder/"scene")
    seed = json.loads((ROOT/"assets/tasks/horseshoe_ring/tutorial_solvable_v3/agent_initial_state.json").read_text())
    digest = hashlib.sha256(json.dumps(task.assembly.template, sort_keys=True).encode()).hexdigest()
    if digest != seed["source_template_sha256"] or float(cfg.task.scale) != seed["scene_scale"]:
        raise ValueError("Initialization belongs to a different geometry/scale")
    robot = task.manifest.get("robot")
    ctrl = AlohaDualArmController(task.scene, robot, cfg.robot_control)
    ctrl.configure()
    robot.set_qpos(np.asarray(seed["qpos"]), zero_velocity=True)
    for name, body in task.bodies.items():
        pose = seed["bodies"][name]
        body.set_pos(np.asarray(cfg.env.robot_mount.pos)+pose["pos"])
        body.set_quat(np.asarray(pose["quat"])[[3, 0, 1, 2]])
        body.zero_all_dofs_velocity()
    for arm in ctrl.arms.values():
        arm.set_arm_qpos(arm.arm_qpos())
        arm.set_gripper(float(arm.gripper_qpos()[0]))
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return HorseshoeAdapter(task, cfg, ctrl, folder)


"""Fixed open-overhand FEM task on the common protocol; no oracle or route."""
import atexit
import json
from pathlib import Path
import numpy as np

from topogym.agent_bridge.fem_robot_adapter import FEMRobotAdapter, RopeGraspBank, rotation
from topogym.agent_bridge.robot_adapter import array
from .agent_spec import describe_task
from .diagnostics import FemDiagnostics, SurfaceCCD, LIMITS
from .geometry import projected_crossings, minimum_nonlocal_distance

ROOT = Path(__file__).resolve().parents[3]


def configuration(*, backend="cuda", renderer="rasterizer", resolution=(640, 360)):
    if backend != "cuda":
        raise ValueError("knot_untying requires CUDA FEM/IPC; use --backend cuda (no CPU fallback)")
    from hydra import compose, initialize_config_dir
    from omegaconf import open_dict
    from topogym.world.aloha_cameras import configure_aloha_rig
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="knot_untying_preview", overrides=[
            "env_configs@env=world_tabletop_aloha_v1", "robot_control_configs@robot_control=aloha_position_ik"])
    with open_dict(cfg.task):
        cfg.task.origin_xy_m = [-.11, .24]
        cfg.task.robot_collision = dict(decimate=False)
        cfg.task.robot_rigid_collision = dict(enable_collision=True, enable_self_collision=True,
            enable_neutral_collision=True, enable_adjacent_collision=False)
        cfg.task.robot_coupling = "external_articulation"
        cfg.task.rope.fem.contact_eps_velocity = .001
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    for side in ("left", "right"):
        cfg.robot_control.home[side][6:] = [float(cfg.robot_control.gripper.open_qpos)]*2
    configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=12.)
    cfg.env.cameras.cam_high.pos = [-.11, .02, 1.85]
    cfg.env.cameras.cam_high.lookat = [-.11, .20, .93]
    cfg.env.cameras.cam_high.fov = 50.
    cfg.run.viewer = False
    return cfg


def planar_clear(points, radius):
    if projected_crossings(points):
        return False
    flat = points.copy()
    flat[:, 2] = 0.
    if np.any(np.linalg.norm(np.diff(flat, axis=0), axis=1)<1e-9):
        return False
    gap, _ = minimum_nonlocal_distance(flat, 6*radius)
    return gap > 2*radius


class KnotAdapter(FEMRobotAdapter):
    def __init__(self, task, cfg, ctrl, monitor, bank, folder):
        self.rest_origin = None
        super().__init__(task, cfg, ctrl, monitor, bank, folder, description=describe_task(cfg))

    def _failure_and_goal(self):
        m = self.monitor
        if getattr(m, "agent_failure", None):
            return m.agent_failure, False
        if m.min_J <= LIMITS.min_volume_ratio:
            return "FEM volume ratio <=0.2", False
        if m.maxima["max_total_length_relative_change"] > LIMITS.loaded_length_relative_change:
            return "Rope length changed by more than 5%", False
        if m.maxima["max_local_axial_strain"] > LIMITS.local_axial_strain:
            return "Local axial strain exceeded 20%", False
        contacts = self.scene.sim.rigid_solver.collider.get_contacts()
        if array(contacts["penetration"]).max(initial=0) > .0005:
            return "Rigid penetration exceeded 0.5 mm", False
        limits = np.asarray(self.cfg.robot_control.robot.arm_joint_limits)
        for arm in self.ctrl.arms.values():
            angles = arm.arm_qpos()
            if not np.isfinite(angles).all() or np.any(angles<limits[:, 0]-1e-5) or np.any(angles>limits[:, 1]+1e-5):
                return "Actual robot joints invalid or outside limits", False
        for part in m.ccd.parts:
            if part["name"].startswith(("left/", "right/")):
                link = self.ctrl.robot.get_link(part["name"])
                rendered = rotation(array(link.get_quat())).apply(part["local"])+array(link.get_pos())
                if np.linalg.norm(rendered-part["previous"], axis=1).max()>.002:
                    return "Native IPC and visible robot differ by more than 2 mm", False
        for i, side in self.bank.owners.items():
            arm = self.ctrl.arms[side]
            target = arm.hand_pos()+rotation(arm.hand_quat()).apply(self.bank.offsets[i])
            if np.linalg.norm(m.last_positions[self.bank.bands[i].indices]-target, axis=1).max()>.002:
                return "Soft grasp follow error exceeded 2 mm", False
        speed = np.linalg.norm(m.last_velocity, axis=1)
        p = m.last_positions
        center, size = np.asarray(self.cfg.env.world.table.pos), np.asarray(self.cfg.env.world.table.size)
        on_table = np.all(p[:, :2]>=center[:2]-size[:2]/2) and np.all(p[:, :2]<=center[:2]+size[:2]/2)
        # Conservative withdrawal check: disjoint expanded finger/rope bounds
        # rule out unassisted pinning without querying hidden contact forces.
        fingers_clear = all(np.any(np.maximum(part["previous"].min(0)-p.max(0),
            p.min(0)-part["previous"].max(0))>.0008) for part in m.ccd.parts
            if part["name"].endswith(("left_finger_link", "right_finger_link")))
        reached = bool(not self.bank.owners and fingers_clear and on_table and p[:,2].max()<=m.floor+.012
            and np.sqrt(np.mean(speed**2))<.001 and speed.max()<.005
            and planar_clear(m.last_centers, self.task.layout.rope_radius_m))
        if not reached:
            self.rest_origin = None
        elif self.rest_origin is None:
            self.rest_origin = p.copy()
        elif np.linalg.norm(p-self.rest_origin, axis=1).max()>=.002:
            self.rest_origin, reached = None, False
        return None, reached


def create(asset_dir, *, backend="cuda", renderer="rasterizer", resolution=(640, 360)):
    cfg = configuration(backend=backend, renderer=renderer, resolution=resolution)
    import genesis as gs
    import torch
    from omegaconf import OmegaConf
    from topogym.robot import initialize_robot_controller
    from .scene import KnotSceneBuilder
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; a real FEM/IPC episode cannot be created")
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    gs.init(backend=gs.cuda, logging_level="warning", seed=7)
    bank = RopeGraspBank(SurfaceCCD)
    task = KnotSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=folder/"scene", pre_build=bank.declare)
    ctrl = initialize_robot_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, reset_home=False)
    for side, arm in ctrl.arms.items():
        arm.set_arm_qpos(cfg.robot_control.home[side][:6])
        arm.set_gripper(cfg.robot_control.home[side][6])
    monitor = FemDiagnostics(task, loaded=True, audit_rigid=True)
    if monitor.ccd.initial_intersections:
        monitor.close()
        raise ValueError("Initial FEM/rigid surfaces intersect")
    required = {f"{side}/{finger}_finger_link" for side in ("left", "right") for finger in ("left", "right")}
    if not required.issubset({p["name"] for p in monitor.ccd.parts}):
        monitor.close()
        raise ValueError("Native IPC audit is missing a finger surface")
    monitor.last_positions, monitor.last_velocity = monitor.native_state()
    monitor.last_centers = monitor.last_positions[monitor.rings].mean(1)
    adapter = KnotAdapter(task, cfg, ctrl, monitor, bank, folder)
    original = monitor.coupler.couple
    monitor._original_couple = original

    def observed(f):
        bank.drive(ctrl)
        original(f)
        if getattr(monitor, "agent_failure", None):
            return
        try:
            monitor.observe()
            # Persist private diagnostics without accumulating an episode in RAM.
            if monitor.samples:
                with (folder/"fem_metrics.jsonl").open("a") as stream:
                    stream.write(json.dumps(monitor.samples[-1])+"\n")
                monitor.samples.clear()
                monitor.centers.clear()
        except RuntimeError as exc:
            monitor.agent_failure = str(exc)
            (folder/"fem_failure.json").write_text(json.dumps(dict(error=str(exc), substep=monitor.count))+"\n")
    monitor.coupler.couple = observed
    atexit.register(adapter.close)
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return adapter

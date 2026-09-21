"""Fixed 150 mm baseline on the shared Panda loop; no oracle or trajectory."""
from pathlib import Path
import numpy as np

from topogym.agent_bridge.robot_adapter import RigidRobotAdapter, array
from topogym.agent_bridge.panda_contract import PandaPort, validate_action
from .agent_spec import describe_task

ROOT = Path(__file__).resolve().parents[3]


def configuration(*, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="lock_picking_spaced_preview")
    cfg.env.genesis.backend, cfg.env.renderer.type = backend, renderer
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
        for n in ("agentview", "front_oblique", "wrist")})
    for camera in cfg.env.cameras.values():
        camera.res = list(resolution)
    cfg.env.cameras.front_oblique.pos = [1.05, -.8, 1.68]
    cfg.env.cameras.front_oblique.lookat = [.05, .15, 1.12]
    cfg.env.cameras.front_oblique.fov = 55
    cfg.env.cameras.wrist.attach.offset_pos = [.10, -.12, 0.]
    cfg.env.cameras.wrist.attach.offset_lookat = [.20, -.30, .14]
    cfg.env.cameras.wrist.fov = 100
    # Start tangent to the V rests. The old runner drops 0.1 mm and settles
    # before observing; a no-hidden-step episode must not start with that impact.
    cfg.task.initialization.spawn_clearance = 0.
    cfg.run.viewer = False
    return cfg


class LockPickingAdapter(RigidRobotAdapter):
    def __init__(self, task, cfg, controller, folder):
        task.bodies = {"lock_key": task.key}
        spec = describe_task(cfg)
        super().__init__(task, cfg, PandaPort(controller), folder, description=spec,
            grasp_candidates=("lock_key",), hand_links={"arm": "hand"},
            finger_links={"arm": ["left_finger", "right_finger"]},
            validate_command=lambda a: validate_action(a, spec["action_schema"]),
            success_reason="Key at END, released and quiet for 0.5 s (pilot)")
        self.robotlinks = {l.idx for l in self.robot.links if l.idx != self.robot.base_link_idx}
        self.fixtures = {l.idx for n, e in task.manifest.entities.items()
                         if n.startswith("lock_") and n != "lock_key" for l in e.links}
        self.fixed = [(e, array(e.get_pos()).copy(), array(e.get_quat()).copy())
                      for n, e in task.manifest.entities.items() if n.startswith("lock_") and n != "lock_key"]

    def _failure_and_goal(self, contacts):
        task = self.task
        state = task.state()  # Private evaluator only: never added to public obs.
        if not np.isfinite(np.concatenate([np.asarray(v).reshape(-1) for v in state.values()])).all():
            return "Non-finite lock state", False
        for entity, pos, quat in self.fixed:
            now, rotation = array(entity.get_pos()), array(entity.get_quat())
            if (not np.isfinite(np.r_[now, rotation]).all() or np.linalg.norm(now-pos)>1e-6
                    or 1-abs(np.dot(rotation, quat))>1e-8):
                return "Fixed mechanism base moved", False
        if state["key_tip_pos"][2] < task.tabletop.frames.table_surface_origin[2]-.1:
            return "Key fell below tabletop", False
        for angle, stop in zip(state["disc_deg"], task.cfg.rotor_stops):
            lo, hi = stop.bounds_deg
            if hi-lo >= 360.-1e-8:  # A full-turn ring is a continuous joint.
                continue
            if angle < lo-.5 or angle > hi+.5:
                return "Rotor exceeded physical stop range", False
        a, b = contacts["link_a"], contacts["link_b"]
        key = task.key.base_link_idx
        fixture_a, fixture_b = np.isin(a, list(self.fixtures)), np.isin(b, list(self.fixtures))
        robot_a, robot_b = np.isin(a, list(self.robotlinks)), np.isin(b, list(self.robotlinks))
        force = np.linalg.norm(contacts["force"], axis=-1)
        key_fixture = ((a == key) & fixture_b) | ((b == key) & fixture_a)
        key_force = float(force[key_fixture].sum())
        task.last_contacts = contacts
        task.max_key_contact_force = max(task.max_key_contact_force, key_force)
        task.max_contact_penetration = max(task.max_contact_penetration, float(contacts["penetration"].max(initial=0)))
        if key_force > float(task.cfg.physics.max_key_contact_force):
            task.force_limit_triggered = True
            return "Key/fixture contact force exceeded 10 N", False
        if task.max_contact_penetration > float(task.cfg.physics.max_penetration):
            return "Contact penetration exceeded 2 mm", False
        if force[(robot_a & fixture_b) | (robot_b & fixture_a)].sum() > .01:
            return "Robot contacted mechanism directly", False
        cfg = task.cfg.success
        aligned = state["axis_offset"] <= float(cfg.max_axis_offset) and state["axis_tilt_deg"] <= float(cfg.max_axis_tilt_deg)
        # The angular model is coaxial: applying it to pickup/approach poses
        # would falsely call a key above a rotor a penetrating key.
        if aligned and task.layout.clearance(state["depth"], state["key_deg"], state["disc_deg"], tolerance=2.):
            task.geometry_error_steps += 1
            return "Coaxial tab/slot interference", False
        released = not any(key in pair for pair in self.registrations)
        touching_robot = force[((a == key) & robot_b) | ((b == key) & robot_a)].sum() >= .01
        geometry = task.layout.clearance(state["depth"], state["key_deg"], state["disc_deg"], tolerance=.5)
        reached = (aligned and abs(state["depth"]-4.) <= float(cfg.depth_tolerance)
            and not geometry and released and not touching_robot
            and state["linear_speed"] < float(cfg.max_linear_speed)
            and state["angular_speed"] < float(cfg.max_angular_speed))
        return None, bool(reached)


def create(asset_dir, *, backend="cpu", renderer="rasterizer", resolution=(640, 480)):
    import genesis as gs
    from omegaconf import OmegaConf
    from topogym.robot.factory import initialize_robot_controller
    from .scene import LockPickingSceneBuilder
    folder = Path(asset_dir)
    folder.mkdir(parents=True, exist_ok=False)
    cfg = configuration(backend=backend, renderer=renderer, resolution=resolution)
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = LockPickingSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=folder/"scene", contact_guard=False)
    controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, reset_home=False)
    controller.reset_home(settle_steps=0)  # Initialization only; tick=0 is never advanced.
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    return LockPickingAdapter(task, cfg, controller, folder)

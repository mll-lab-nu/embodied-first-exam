"""Live ALOHA Cast Coil adapter; pilot evaluator, without grasp assistance."""
from pathlib import Path


def create(asset_dir, *, backend="cpu", renderer="nyx", objective="assemble", resolution=(320, 180),
           resolved_config=None):
    import genesis as gs
    import numpy as np
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from scipy.spatial.transform import Rotation
    from topogym.agent_bridge.adapters import GenesisAdapter, finite_vector
    from topogym.robot.aloha import AlohaDualArmController
    from topogym.world.aloha_cameras import configure_aloha_rig
    from .scene import build_scene
    from .assembly_task import goal_metrics
    from .verification import box_corners
    from .agent_spec import describe_task

    if resolved_config is None:
        with initialize_config_dir(config_dir=str(Path(__file__).resolve().parents[3]/"configs"), version_base=None):
            cfg = compose(config_name="cast_coil_aloha")
        cfg.task.objective = objective
        cfg.env.genesis.backend = backend
        cfg.env.renderer.type = renderer
        cfg.run.include_robot = True
        cfg.run.viewer = False
        configure_aloha_rig(cfg, keep=(), resolution=resolution, low_pitch_offset_deg=20)
    else:
        # Preparation has already sampled and resolved every scene parameter.
        cfg = OmegaConf.create(resolved_config)
        objective, backend = str(cfg.task.objective), str(cfg.env.genesis.backend)
    gs.init(backend=getattr(gs, backend), logging_level="warning", seed=int(cfg.task.get("seed", 0)), precision="64")
    task = build_scene(cfg, asset_dir)
    ctrl = AlohaDualArmController(task.scene, task.manifest.get("robot"), cfg.robot_control)
    ctrl.configure()
    # Initialization only. Trial reset reconstructs this adapter in a fresh process.
    ctrl.reset_home(settle_steps=0)
    OmegaConf.save(cfg, Path(asset_dir)/"config.yaml", resolve=True)
    description = describe_task(cfg)
    limits = np.asarray(cfg.robot_control.robot.arm_joint_limits)
    grip_min, grip_max = float(cfg.robot_control.gripper.closed_qpos), float(cfg.robot_control.gripper.open_qpos)

    def validate(action):
        if not isinstance(action, dict) or set(action)-{"left", "right"}:
            raise ValueError("Action has only optional left/right arm commands; {} holds targets")
        for side, command in action.items():
            if not isinstance(command, dict) or not command or set(command)-{"qpos", "gripper"}:
                raise ValueError("Each arm command has qpos and/or gripper")
            if "qpos" in command:
                finite_vector(command["qpos"], 6, "qpos")
                q = np.asarray(command["qpos"])
                if np.any(q < limits[:, 0]) or np.any(q > limits[:, 1]):
                    raise ValueError("Arm joint limit exceeded")
            if "gripper" in command:
                finite_vector([command["gripper"]], 1, "gripper")
                if not grip_min <= command["gripper"] <= grip_max:
                    raise ValueError("Finger displacement outside limits")

    def apply(action):
        for side, command in action.items():
            if "qpos" in command:
                ctrl.arms[side].set_arm_qpos(command["qpos"], steps=0)
            if "gripper" in command:
                ctrl.arms[side].set_gripper(command["gripper"], steps=0)

    def arr(x):
        return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    bodies = [task.bodies[n] for n in ("coil_gold", "coil_silver")]
    origins = [np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]]
    stable_steps, terminal = 0, None
    bodylinks = {b.base_link_idx for b in bodies}
    robotlinks = {link.idx for link in ctrl.robot.links}

    def evaluate():
        nonlocal stable_steps, terminal
        if terminal:
            return terminal
        poses = []
        for body, origin in zip(bodies, origins):
            rotation = Rotation.from_quat(arr(body.get_quat())[[1, 2, 3, 0]])
            poses.append((arr(body.get_pos())-rotation.apply(origin), rotation))
        if any(p[2] < task.tabletop.frames.table_surface_origin[2]-.1 for p, _ in poses):
            terminal = dict(status="failed", reason="A piece fell below the tabletop")
            return terminal
        contacts = task.scene.sim.rigid_solver.collider.get_contacts(as_tensor=True, to_torch=True)
        la, lb, pen = (arr(contacts[k]) for k in ("link_a", "link_b", "penetration"))
        pair = np.isin(la, list(bodylinks)) & np.isin(lb, list(bodylinks))
        if float(pen[pair].max(initial=0)) > .001:
            terminal = dict(status="failed", reason="Interpiece penetration exceeded 1 mm")
            return terminal
        held = ((np.isin(la, list(bodylinks)) & np.isin(lb, list(robotlinks))) |
                (np.isin(lb, list(bodylinks)) & np.isin(la, list(robotlinks))))
        force = np.linalg.norm(arr(contacts["force"]), axis=-1)
        released = not np.any(held & (force > .05))
        pg, rg = poses[0]
        ps, rs = poses[1]
        if objective == "assemble":
            reached = goal_metrics(pg, rg, ps, rs)["goal_assembled"]
        else:
            bounds = []
            for body, (p, r) in zip(task.assembly.bodies, poses):
                vertices = r.apply(box_corners(body.boxes))+p
                bounds.append((vertices.min(axis=0), vertices.max(axis=0)))
            reached = bool(np.max(np.maximum(bounds[1][0]-bounds[0][1], bounds[0][0]-bounds[1][1])) > .01)
        quiet = all(np.linalg.norm(arr(b.get_vel())) < .001 and np.linalg.norm(arr(b.get_ang())) < .02 for b in bodies)
        stable_steps = stable_steps+1 if reached and released and quiet else 0
        if stable_steps >= round(.5/float(cfg.env.sim.dt)):
            terminal = dict(status="succeeded", reason="Goal stable and released for 0.5 simulated seconds (pilot evaluator)")
            return terminal
        return dict(status="running")

    adapter = GenesisAdapter(scene=task.scene, cameras=task.cameras,
        description=description,
        validate_action=validate, apply_action=apply, observe=lambda: {"robot": ctrl.state()}, evaluate=evaluate)
    # Operator-only initialization audit, never included in public observations.
    adapter.initial_state = lambda: dict(robot=ctrl.state(), bodies={name: dict(
        pos=arr(body.get_pos()).tolist(), quat=arr(body.get_quat()).tolist(),
        velocity=arr(body.get_vel()).tolist(), angular_velocity=arr(body.get_ang()).tolist())
        for name, body in task.bodies.items()})
    adapter.simulator_spec = dict(
        state_fields=["bodies", "robot", "camera_poses", "contacts"],
        pose_entities=list(task.bodies) + ["left_hand", "right_hand"],
        coordinate_frame="world", position_units="metres", quaternion_order="wxyz",
        velocity_units="metres/second; angular radians/second", force_units="newtons",
        coverage="Cast Coil rigid bodies, ALOHA joint/hand state, camera poses and rigid contacts. "
                 "No solver buffers, arbitrary state writes, target transforms or reference solution.")

    def get_pose(entity):
        if entity in task.bodies:
            body = task.bodies[entity]
            return dict(position=arr(body.get_pos()).tolist(), quaternion_wxyz=arr(body.get_quat()).tolist(),
                        frame="world", origin="Genesis body origin")
        side = entity.removesuffix("_hand")
        state = ctrl.state()[side]
        return dict(position=state["hand_pos"], quaternion_wxyz=state["hand_quat_wxyz"],
                    frame="world", origin="gripper_link origin, not fingertip center")

    def get_state(fields):
        result = {}
        if "bodies" in fields:
            result["bodies"] = adapter.initial_state()["bodies"]
        if "robot" in fields:
            result["robot"] = ctrl.state()
        if "camera_poses" in fields:
            result["camera_poses"] = adapter.observe()["camera_poses"]
        if "contacts" in fields:
            contacts = task.scene.sim.rigid_solver.collider.get_contacts(as_tensor=True, to_torch=True)
            result["contacts"] = {k: arr(contacts[k]).tolist() for k in ("link_a", "link_b", "penetration", "force")}
        return result

    adapter.get_state, adapter.get_pose = get_state, get_pose
    return adapter

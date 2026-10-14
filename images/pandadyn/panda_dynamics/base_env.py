"""Shared single/dual-Panda task infrastructure; no task-name dispatch.

World: right-handed, z up, SI. Quaternions wxyz. Single CPU PhysX scene;
1000 Hz physics/servo, 100 Hz action requests. Each subclass owns its scene,
reset and event predicates. No controller has permission to mutate scene state.
"""

from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
import numpy as np
import sapien
import torch
from gymnasium import spaces
from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.agents.multi_agent import MultiAgent
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.structs.types import SimConfig, SceneConfig
from .config import load_config
from .events import EventLedger
from .telemetry import Telemetry
from .props.primitives import box, body, position, velocity
from .robots.constrained_controller import ConstrainedController
from .robots.kinematics import Kinematics
from .robots.tooled_panda import TooledPanda
from .robots.panda_limits import LOWER, UPPER
from .robots.arm import ArmSetup, ArmRuntime


class PandaDynamicEnv(BaseEnv):
    SUPPORTED_ROBOTS = ["panda", ("panda", "panda")]
    ARM_SETUPS = None
    NAMESPACE = "PandaDynamics"
    PHASES = ()
    ROLE_LABELS = ()
    LAYOUT = "single"
    TASK = ""
    INSTRUCTION = ""
    TOOL = "cup"
    TOOL_HALF = 0.065
    MOUNT = (0.12, 0, 0.04)
    TOOL_START = (0.05, -0.08, 0.18)
    TOOL_QUAT = (1, 0, 0, 0)
    TABLE = True
    ALLOW_FINGER_CONTACTS = False
    ALLOWED_TOOL_FIXTURES = ()
    ALLOWED_FINGER_FIXTURES = ()
    REFERENCE_ACCELERATION = 0.55
    REFERENCE_JERK = 0.05
    WRIST_DAMPING = (12.0, 10.0, 7.0)

    def __init__(
        self,
        *args,
        difficulty="nominal",
        parameters=None,
        physics_hz=1000,
        quality="preview",
        shader="default",
        **kwargs,
    ):
        self.difficulty = difficulty
        self.params = load_config(self.TASK, difficulty, parameters)
        if physics_hz not in (1000, 2000):
            raise ValueError(
                "Accepted physics_hz values: 1000, 2000 (sensitivity check)."
            )
        self.physics_hz = physics_hz
        self.dt = 1.0 / physics_hz
        self.time = 0.0
        self.events = EventLedger()
        self.rng = np.random.default_rng(0)
        self.seed_value = 0
        self.quality, self.shader = quality, shader
        self.capture_hook = None
        self.arm_setups = self.ARM_SETUPS or (
            ArmSetup(
                self.TOOL,
                self.TOOL_START,
                mount=self.MOUNT,
                quaternion=self.TOOL_QUAT,
                half=self.TOOL_HALF,
            ),
        )
        self.arms = {}
        self.contacts = {}
        self.contact_records = []
        self.previous_contacts = set()
        self.objects = {}
        self.fixtures = {}
        self.debug_targets = {}
        self.tool = None
        self.tool_body = None
        self.mount_pose = sapien.Pose(self.MOUNT, [0, 1, 0, 0])
        kwargs.setdefault("obs_mode", "state_dict")
        kwargs.setdefault("render_mode", "rgb_array")
        kwargs.setdefault("reward_mode", "sparse")
        if (
            kwargs.get("num_envs", 1) != 1
            or kwargs.get("sim_backend", "physx_cpu") != "physx_cpu"
        ):
            raise ValueError("This audited backend is single-env physx_cpu only.")
        kwargs.update(
            num_envs=1,
            sim_backend="physx_cpu",
            control_mode="pd_joint_pos",
            robot_uids="panda" if len(self.arm_setups) == 1 else ("panda", "panda"),
        )
        super().__init__(*args, **kwargs)
        self.single_action_space = spaces.Box(
            np.r_[LOWER, 0].astype(np.float32), np.r_[UPPER, 0.08].astype(np.float32)
        )
        if len(self.arms) == 2:
            self.single_action_space = spaces.Dict(
                {uid: deepcopy(self.single_action_space) for uid in self.arms}
            )
        self.action_space = self.single_action_space

    @property
    def env_id(self):
        return f"{self.NAMESPACE}/{self.TASK}-v0"

    @property
    def phase(self):
        return int(self.events.flags.get("phase", 0))

    @property
    def phase_name(self):
        return self.PHASES[self.phase] if self.phase < len(self.PHASES) else "complete"

    @property
    def arm_role_labels(self):
        if not self.ROLE_LABELS:
            return {uid: "operator" for uid in self.arms}
        roles = self.ROLE_LABELS[min(self.phase, len(self.ROLE_LABELS) - 1)]
        return dict(zip(self.arms, roles))

    def advance(self, **metrics):
        """Call only after a task-owned physical predicate passes."""
        self.events.emit(
            "phase:" + self.phase_name,
            self.time,
            index=self.phase,
            roles=self.arm_role_labels,
            **metrics,
        )
        self.events.flags["phase"] = self.phase + 1
        self.events.flags["phase_started"] = self.time

    def phase_hold(self, condition, seconds, **metrics):
        if self.events.hold(
            f"phase_hold:{self.phase}", bool(condition), self.time, seconds
        ):
            self.advance(**metrics)
            return True
        return False

    @property
    def _default_sim_config(self):
        return SimConfig(
            sim_freq=self.physics_hz,
            control_freq=100,
            scene_config=SceneConfig(
                gravity=[0, 0, -9.81],
                bounce_threshold=0.05,
                contact_offset=0.001,
                rest_offset=0.0,
                sleep_threshold=0.0,
                solver_position_iterations=32 if self.physics_hz == 1000 else 64,
                solver_velocity_iterations=8 if self.physics_hz == 1000 else 16,
                enable_ccd=True,
                enable_enhanced_determinism=True,
            ),
        )

    @property
    def _default_sensor_configs(self):
        return [
            CameraConfig(
                "external",
                sapien_utils.look_at([0.85, -0.85, 0.7], [0.05, 0, 0.16]),
                320,
                240,
                1.0,
                0.01,
                10,
            )
        ]

    @property
    def _default_human_render_camera_configs(self):
        from .rendering import quality_preset

        preset = quality_preset(self.quality)
        dual = len(self.arm_setups) == 2
        return [
            CameraConfig(
                "overview",
                sapien_utils.look_at(
                    [1.25, -1.50, 1.10] if dual else [0.90, -1.00, 0.85],
                    [0.02, 0, 0.18],
                ),
                preset.width,
                preset.height,
                0.90 if dual else 0.82,
                0.01,
                10,
                shader_pack=self.shader,
            ),
            CameraConfig(
                "event",
                sapien_utils.look_at([0.6, -0.6, 0.65], [0.1, 0, 0.13]),
                preset.width,
                preset.height,
                0.85,
                0.01,
                10,
                shader_pack=self.shader,
            ),
        ]

    def _load_agent(self, options):
        self.arms = {}
        for i, setup in enumerate(self.arm_setups):
            role = "single" if len(self.arm_setups) == 1 else ("left", "right")[i]
            prefix = "" if role == "single" else role + "_"
            spec = (
                dict(
                    kind=setup.tool,
                    half=self.params.get(
                        prefix + "tool_half", self.params.get("tool_half", setup.half)
                    ),
                    mass=self.params.get(
                        prefix + "tool_mass", self.params.get("tool_mass", setup.mass)
                    ),
                    mu=self.params.get(
                        prefix + "tool_friction", self.params.get("tool_friction", 0.4)
                    ),
                    restitution=self.params.get("tool_restitution", 0.05),
                    mount=sapien.Pose(setup.mount, [0, 1, 0, 0]),
                    side_mount=setup.mount[1],
                    height=self.params.get(
                        prefix + "tool_height", self.params.get("tool_height")
                    ),
                )
                if setup.tool
                else None
            )
            agent = TooledPanda(
                self.scene,
                100,
                control_mode="pd_joint_pos",
                agent_idx=i if len(self.arm_setups) == 2 else None,
                initial_pose=sapien.Pose(
                    setup.base, [np.cos(setup.yaw / 2), 0, 0, np.sin(setup.yaw / 2)]
                ),
                tool_spec=spec,
            )
            robot = agent.robot._objs[0]
            arm = ArmRuntime(f"panda-{i}", role, setup, agent, robot, Kinematics(robot))
            arm.tool = agent.robot.links_map["tool"] if setup.tool else None
            arm.tool_body = body(arm.tool) if arm.tool is not None else None
            self.arms[arm.uid] = arm
        self.primary = next(iter(self.arms.values()))
        self.agent = (
            self.primary.agent
            if len(self.arms) == 1
            else MultiAgent([a.agent for a in self.arms.values()])
        )
        self.robot, self.ik = self.primary.robot, self.primary.ik
        self.mount_pose = self.primary.mount_pose

    def _load_scene(self, options):
        self.objects, self.fixtures, self.debug_targets = {}, {}, {}
        self.table = (
            box(
                self.scene,
                "table",
                [0.62, 0.48, 0.025],
                [0.08, 0, -0.025],
                static=True,
                mu=self.params.get("table_friction", 0.2),
                restitution=self.params.get("table_restitution", 0.05),
                color=[0.38, 0.43, 0.47, 1],
            )
            if self.TABLE
            else None
        )
        box(
            self.scene,
            "floor",
            [2, 2, 0.025],
            [0, 0, -0.55],
            static=True,
            color=[0.15, 0.17, 0.20, 1],
        )
        # Both worktop and independent arm bases have load paths to the floor.
        # Keep the supports below z=0, outside the manipulation volume.
        for i, (x, y) in enumerate(((-0.45, -0.39), (-0.45, 0.39), (0.60, -0.39), (0.60, 0.39))):
            if self.TABLE:
                box(self.scene, f"table_leg_{i}", [0.022, 0.022, 0.2375], [x, y, -0.2875], static=True, color=[0.26, 0.29, 0.31, 1])
        for i, setup in enumerate(self.arm_setups):
            box(self.scene, f"robot_pedestal_{i}", [0.10, 0.10, 0.2625], [setup.base[0], setup.base[1], -0.2625], static=True, color=[0.31, 0.34, 0.36, 1])
        self.tool, self.tool_body = self.primary.tool, self.primary.tool_body
        self.build_task()
        for arm in self.arms.values():
            arm.servo = ConstrainedController(
                arm.robot, self.dt, self.REFERENCE_ACCELERATION, self.REFERENCE_JERK
            )
            arm.servo.kd[4:7] = self.WRIST_DAMPING
        self.servo = self.primary.servo
        self.contact_labels = {}
        self.robot_body_roles = {}
        for arm in self.arms.values():
            for link in arm.robot.links:
                self.contact_labels[link] = (
                    arm.contact_name
                    if link == arm.tool_body
                    else (
                        link.entity.name
                        if len(self.arms) == 1
                        else f"{arm.role}/{link.entity.name}"
                    )
                )
                self.robot_body_roles[link] = arm.role
        # Object keys are the public identities, including free articulation links.
        for name, obj in self.objects.items():
            self.contact_labels[body(obj)] = name
        # Lighting changes only visual components; physics geometry is unchanged.
        self.scene.set_ambient_light([0.45, 0.45, 0.45])
        self.scene.add_directional_light([0.4, 0.5, -1], [1.5, 1.5, 1.5], shadow=True)

    def build_task(self):
        raise NotImplementedError

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.seed_value = int(np.asarray(seed).reshape(-1)[0])
        self.rng = np.random.default_rng(self.seed_value)
        # CPU PhysX does not expose its persistent contact caches. Rebuilding
        # the scene makes seeded resets independent of the previous episode.
        options = dict(options or {})
        options["reconfigure"] = True
        observation, info = super().reset(seed=seed, options=options)
        info["task_metadata"] = dict(
            task_id=self.env_id,
            instruction=self.INSTRUCTION,
            seed=self.seed_value,
            difficulty=self.difficulty,
            parameters=deepcopy(self.params),
            fixture_initial_phase={n: f.phase for n, f in self.fixtures.items()},
            units="SI; quaternion wxyz; world z up",
            action="7 absolute joint targets in rad + total aperture in m",
            arms={uid: arm.role for uid, arm in self.arms.items()},
            layout=self.LAYOUT,
            phases=self.PHASES,
        )
        return observation, info

    def _initialize_episode(self, env_idx, options):
        self.time = 0.0
        self.action_history = []
        self.events = EventLedger()
        self.contacts, self.contact_records, self.previous_contacts = {}, [], set()
        for arm in self.arms.values():
            arm.telemetry = Telemetry(self.dt)
            arm.robot.set_qpos(
                np.array(
                    [
                        0.0,
                        0.392699,
                        0.0,
                        -1.963495,
                        0.0,
                        2.356194,
                        0.785398,
                        0.04,
                        0.04,
                    ],
                    dtype=np.float32,
                )
            )
            arm.robot.set_qvel(np.zeros(9, dtype=np.float32))
            desired = sapien.Pose(arm.setup.start, arm.setup.quaternion)
            tcp_pose = (
                desired * arm.mount_pose.inv()
                if arm.tool is not None
                else sapien.Pose(arm.setup.start, [0, 1, 0, 0])
            )
            arm.robot.set_qpos(arm.ik.solve(tcp_pose))
            arm.robot.set_qvel(np.zeros(9, dtype=np.float32))
            arm.servo.reset()
            arm.initial_tool_position = arm.tool_pose.p.copy()
        self.telemetry = self.primary.telemetry
        self.initial_tool_position = self.tool_pose.p.copy()
        self.reset_task()
        self.events.emit("reset", 0.0, seed=self.seed_value)
        self.previous_positions = {
            name: position(obj) for name, obj in self.objects.items()
        }
        self.previous_local = {
            name: self.local_position(obj) for name, obj in self.objects.items()
        }

    def reset_task(self):
        raise NotImplementedError

    @property
    def tool_pose(self):
        return (
            self.tool_body.entity_pose
            if self.tool is not None
            else self.primary.agent.tcp._objs[0].entity_pose
        )

    def local_position(self, actor, frame=None):
        return ((frame or self.tool_pose).inv() * body(actor).entity_pose).p

    def relative_speed(self, actor, receiver=None):
        receiver = body(receiver) if receiver is not None else self.tool_body
        if receiver is None:
            receiver = self.primary.agent.tcp._objs[0]
        center = (
            (receiver.entity_pose * receiver.cmass_local_pose).p
            if hasattr(receiver, "cmass_local_pose")
            else receiver.entity_pose.p
        )
        offset = position(actor) - center
        return float(
            np.linalg.norm(
                velocity(actor)
                - getattr(receiver, "linear_velocity", np.zeros(3))
                - np.cross(getattr(receiver, "angular_velocity", np.zeros(3)), offset)
            )
        )

    def contact(self, name1, name2):
        return self.contacts.get(tuple(sorted((name1, name2))), 0.0)

    def recently_supported(self, name, receiver="tool", gap=0.02):
        key = f"last_support:{name}:{receiver}"
        if self.contact(name, receiver) > 0:
            self.events.flags[key] = self.time
        return self.time - self.events.flags.get(key, -1.0) <= gap

    def contacted(self, name1, name2):
        return self.events.has(f"contact:{min(name1, name2)}:{max(name1, name2)}")

    def _step_action(self, action):
        actions = action if len(self.arms) > 1 else {"panda-0": action}
        if actions is not None and set(actions) != set(self.arms):
            raise ValueError(f"Action keys must be {list(self.arms)}")
        recorded = {}
        for uid, arm in self.arms.items():
            if actions is not None and actions[uid] is not None:
                arm.servo.set_action(np.asarray(actions[uid], dtype=float))
            recorded[uid] = np.r_[
                arm.servo.input.target_position[:7],
                sum(arm.servo.input.target_position[7:]),
            ].tolist()
        self.action_history.append(
            recorded if len(self.arms) > 1 else recorded["panda-0"]
        )
        for _ in range(self.physics_hz // 100):
            # Both finite-effort motor commands are set BEFORE this shared world step.
            for arm in self.arms.values():
                arm.servo.step()
            self.before_physics()
            self.scene.step()
            self.time += self.dt
            self.read_contacts()
            for arm in self.arms.values():
                arm.telemetry.sample(self, arm)
            self.update_task()
            if any(arm.telemetry.violations for arm in self.arms.values()):
                self.events.fail("limit_violation", self.time, invalid=True)
            for name, obj in self.objects.items():
                p = position(obj)
                if not np.isfinite(p).all():
                    self.events.fail("invalid_physics", self.time, invalid=True)
                elif p[2] < -0.2 or np.linalg.norm(p[:2]) > 1.8:
                    self.events.fail("out_of_bounds", self.time)
            if self.events.physical_success and not self.events.valid:
                self.events.fail("limit_violation", self.time)
            if (
                self.time >= self.params["horizon"] - self.dt / 2
                and not self.events.physical_success
            ):
                self.events.fail("timeout", self.time)
            self.previous_positions = {
                name: position(obj) for name, obj in self.objects.items()
            }
            self.previous_local = {
                name: self.local_position(obj) for name, obj in self.objects.items()
            }
            if self.capture_hook is not None:
                self.capture_hook(self)
        return action

    def before_physics(self):
        for fixture in self.fixtures.values():
            fixture.step(self.time, self.dt)

    def update_task(self):
        raise NotImplementedError

    def read_contacts(self):
        self.contacts = {}
        for contact in self.scene.px.get_contacts():
            names = [
                self.contact_labels.get(rb, rb.entity.name.removeprefix("scene-0_"))
                for rb in contact.bodies
            ]
            pair = tuple(sorted(names))
            impulse = sum(float(np.linalg.norm(pt.impulse)) for pt in contact.points)
            if impulse < 1e-8:
                continue
            self.contacts[pair] = self.contacts.get(pair, 0.0) + impulse
            penetration = min((pt.separation for pt in contact.points), default=0.0)
            self.contact_records.append(
                dict(
                    time=self.time,
                    pair=pair,
                    body_order=names,
                    impulse=impulse,
                    penetration=float(penetration),
                    points=[
                        dict(
                            position=pt.position.tolist(),
                            impulse_vector=pt.impulse.tolist(),
                            separation=float(pt.separation),
                        )
                        for pt in contact.points
                    ],
                )
            )
            if pair not in self.previous_contacts:
                self.events.emit(
                    f"contact:{pair[0]}:{pair[1]}",
                    self.time,
                    impulse=impulse,
                    body_velocities=[
                        getattr(rb, "linear_velocity", np.zeros(3)).tolist()
                        for rb in contact.bodies
                    ],
                    arm_tool_velocities={
                        uid: (
                            arm.tool_body
                            if arm.tool is not None
                            else arm.agent.tcp._objs[0]
                        ).linear_velocity.tolist()
                        for uid, arm in self.arms.items()
                    },
                )
            tool_names = {
                a.contact_name for a in self.arms.values() if a.tool is not None
            }
            robot_names = [
                n
                for n, rb in zip(names, contact.bodies)
                if rb in self.robot_body_roles and n not in tool_names
            ]
            other_names = [n for n in names if n not in robot_names]
            roles = {
                self.robot_body_roles[rb]
                for rb in contact.bodies
                if rb in self.robot_body_roles
            }
            if len(roles) > 1:
                self.events.fail("arm_arm_or_tool_collision", self.time, invalid=True)
            if len(roles) == 1 and all(
                rb in self.robot_body_roles for rb in contact.bodies
            ):
                if not all("finger" in n for n in names):
                    self.events.fail("self_collision", self.time, invalid=True)
            if (
                robot_names
                and other_names
                and not all(rb in self.robot_body_roles for rb in contact.bodies)
            ):
                allowed = (
                    self.ALLOW_FINGER_CONTACTS
                    and all("finger" in n for n in robot_names)
                    and all(
                        n in self.objects or n in self.ALLOWED_FINGER_FIXTURES
                        for n in other_names
                    )
                )
                if not allowed:
                    self.events.fail(
                        "forbidden_arm_scene_contact", self.time, invalid=True
                    )
            if (
                robot_names
                and any(n in self.objects for n in other_names)
                and not (
                    self.ALLOW_FINGER_CONTACTS
                    and all("finger" in n for n in robot_names)
                )
            ):
                self.events.fail(
                    "forbidden_arm_object_contact", self.time, invalid=True
                )
            if robot_names and any(n in ("table", "floor") for n in other_names):
                self.events.fail("forbidden_collision", self.time, invalid=True)
            fixture_link_names = {
                self.contact_labels.get(link, link.entity.name.removeprefix("scene-0_"))
                for f in self.fixtures.values()
                for link in f.raw.links
            }
            if (
                robot_names
                and any(n in fixture_link_names for n in other_names)
                and not (
                    all("finger" in n for n in robot_names)
                    and all(n in self.ALLOWED_FINGER_FIXTURES for n in other_names)
                )
            ):
                self.events.fail(
                    "forbidden_arm_fixture_contact", self.time, invalid=True
                )
            if any(n in tool_names for n in names):
                outside = [
                    n for n in names if n not in tool_names and n not in robot_names
                ]
                if any(
                    n not in self.objects and n not in self.ALLOWED_TOOL_FIXTURES
                    for n in outside
                ):
                    self.events.fail(
                        "forbidden_tool_fixture_contact", self.time, invalid=True
                    )
            if "tool" in names and "table" in names:
                self.events.fail("tool_table_collision", self.time, invalid=True)
            if penetration < -0.004:
                self.events.fail("excessive_penetration", self.time, invalid=True)
        self.previous_contacts = set(self.contacts)

    def evaluate(self):
        accepted = (
            self.events.physical_success
            and self.events.valid
            and self.events.failure_reason is None
        )
        return {
            "success": torch.tensor([accepted]),
            "physical_success": torch.tensor([self.events.physical_success]),
            "valid": torch.tensor([self.events.valid]),
            "fail": torch.tensor([self.events.failure_reason is not None]),
            "simulation_time": self.time,
            "failure_reason": self.events.failure_reason or "",
            "event_count": len(self.events.history),
            "phase": self.phase,
            "phase_name": self.phase_name,
            "arm_roles": self.arm_role_labels,
        }

    def _get_obs_extra(self, info):
        values = {
            "time": torch.tensor([[self.time]], dtype=torch.float32),
            "tool_pose": torch.tensor(
                np.r_[self.tool_pose.p, self.tool_pose.q][None], dtype=torch.float32
            ),
        }
        for name, obj in self.objects.items():
            rb = body(obj)
            values[name] = torch.tensor(
                np.r_[
                    rb.entity_pose.p,
                    rb.entity_pose.q,
                    rb.linear_velocity,
                    rb.angular_velocity,
                ][None],
                dtype=torch.float32,
            )
        for uid, arm in self.arms.items():
            values[uid + "_tool_pose"] = torch.tensor(
                np.r_[arm.tool_pose.p, arm.tool_pose.q][None], dtype=torch.float32
            )
        values["phase"] = torch.tensor([[self.phase]], dtype=torch.int32)
        for name, fixture in self.fixtures.items():
            values[name + "_state"] = torch.tensor(
                [[fixture.q, fixture.v]], dtype=torch.float32
            )
        values["progress"] = torch.tensor(
            [
                [
                    len(self.events.history),
                    float(self.events.physical_success),
                    float(self.events.valid),
                ]
            ]
        )
        # Only goals announced at reset, not future RNG draws or hidden release
        # decisions. All free-object launch states are already in state_dict.
        for key in ("target", "goal", "zone", "waypoints", "order", "window_start"):
            if key in self.events.flags:
                values["goal_" + key] = torch.as_tensor(
                    np.asarray(self.events.flags[key]), dtype=torch.float32
                ).reshape(1, -1)
        return values

    def snapshot(self):
        """Full state plus actions needed to reconstruct opaque solver caches."""
        return {
            "action_history": deepcopy(self.action_history),
            "physics": deepcopy(super().get_state_dict()),
            "events": deepcopy(asdict(self.events)),
            "controller": self.servo.state(),
            "arm_controllers": {
                uid: arm.servo.state() for uid, arm in self.arms.items()
            },
            "arm_telemetry": {
                uid: deepcopy(arm.telemetry) for uid, arm in self.arms.items()
            },
            "time": self.time,
            "elapsed_steps": self._elapsed_steps.clone(),
            "rng": deepcopy(self.rng.bit_generator.state),
            "seed": self.seed_value,
            "previous_positions": deepcopy(self.previous_positions),
            "previous_local": deepcopy(self.previous_local),
            "previous_contacts": deepcopy(self.previous_contacts),
            "contacts": deepcopy(self.contacts),
            "fixture_states": {n: f.state() for n, f in self.fixtures.items()},
            "initial_tool_position": self.initial_tool_position.copy(),
            "telemetry": deepcopy(self.telemetry),
            "contact_records": deepcopy(self.contact_records),
        }

    def restore(self, state):
        def equal(a, b):
            if isinstance(a, dict):
                return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
            return np.array_equal(np.asarray(a), np.asarray(b))

        # Exact checkpoints rebuild the unexported contact caches by advancing
        # physical actions from a cold seeded reset. No recorded pose playback.
        # This costs O(elapsed episode steps), and is outside controller stepping.
        # Legacy snapshots remain readable; only new snapshots carry a prefix.
        if "action_history" in state and (
            self.time != state["time"]
            or self.seed_value != state["seed"]
            or not equal(super().get_state_dict(), state["physics"])
        ):
            history = deepcopy(state["action_history"])
            self.reset(seed=state["seed"])
            for action in history:
                self.step(action if isinstance(action, dict) else np.asarray(action))
        self.action_history = deepcopy(state.get("action_history", []))
        # Reapplying identical transforms needlessly rebuilds PhysX contact
        # pairs. Preserve the exact fresh-reset scene when loading its state.
        current = super().get_state_dict()

        if not equal(current, state["physics"]):
            super().set_state_dict(state["physics"])
        self.events = EventLedger(**deepcopy(state["events"]))
        self.servo.restore(state["controller"])
        for uid, controller in state.get("arm_controllers", {}).items():
            self.arms[uid].servo.restore(controller)
        for uid, telemetry in state.get("arm_telemetry", {}).items():
            self.arms[uid].telemetry = deepcopy(telemetry)
        self.time, self.seed_value = state["time"], state["seed"]
        self._elapsed_steps = state["elapsed_steps"].clone()
        self.rng.bit_generator.state = deepcopy(state["rng"])
        self.previous_positions = deepcopy(state["previous_positions"])
        self.previous_local = deepcopy(state["previous_local"])
        self.previous_contacts = deepcopy(state["previous_contacts"])
        self.contacts = deepcopy(state["contacts"])
        self.initial_tool_position = state["initial_tool_position"].copy()
        self.telemetry = deepcopy(state["telemetry"])
        self.primary.telemetry = self.telemetry
        self.contact_records = deepcopy(state["contact_records"])
        for n, s in state["fixture_states"].items():
            self.fixtures[n].restore(s)

    def target_action(
        self, xyz, quaternion=(1, 0, 0, 0), aperture=0.08, initial=None, arm="panda-0"
    ):
        arm = self.arms[arm]
        pose = sapien.Pose(xyz, quaternion)
        tcp = (
            pose * arm.mount_pose.inv()
            if arm.tool is not None
            else sapien.Pose(xyz, quaternion)
        )
        q = arm.ik.solve(tcp, initial=initial)
        return np.r_[q[:7], aperture]

    def parked_action(self):
        actions = {uid: arm.parked_action() for uid, arm in self.arms.items()}
        return actions if len(actions) > 1 else actions["panda-0"]

    def telemetry_arrays(self):
        if len(self.arms) == 1:
            return self.telemetry.arrays()
        return {
            uid + "/" + key: value
            for uid, arm in self.arms.items()
            for key, value in arm.telemetry.arrays().items()
        }

    def telemetry_summary(self):
        if len(self.arms) == 1:
            return self.telemetry.summary()
        return {uid: arm.telemetry.summary() for uid, arm in self.arms.items()}

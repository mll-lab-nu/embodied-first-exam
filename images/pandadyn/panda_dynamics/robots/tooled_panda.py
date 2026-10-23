"""Native Panda URDF with a procedural fixed tool link appended at load time.

All stock links, masses, inertias and the standard hand are preserved. Tool
mass/inertia are integrated into the articulation, inverse dynamics and effort
budget. UID remains panda; no payload is ever made part of this articulation.
"""

from copy import deepcopy
import sapien
from mani_skill.agents.robots.panda.panda import Panda
from mani_skill.utils import sapien_utils
from panda_dynamics.props.primitives import tool_shapes


class TooledPanda(Panda):
    def __init__(self, *args, tool_spec=None, **kwargs):
        self.tool_spec = tool_spec
        super().__init__(*args, **kwargs)

    def _load_articulation(self, initial_pose=None):
        loader = self.scene.create_urdf_loader()
        loader.name = (
            "panda" if self._agent_idx is None else f"panda-agent-{self._agent_idx}"
        )
        loader.fix_root_link = True
        config = deepcopy(self.urdf_config)
        config["_materials"]["gripper"].update(
            static_friction=1.2, dynamic_friction=1.0
        )
        for finger in ("panda_leftfinger", "panda_rightfinger"):
            config["link"][finger].update(patch_radius=0.003, min_patch_radius=0.001)
        cfg = sapien_utils.parse_urdf_config(config)
        sapien_utils.apply_urdf_config(loader, cfg)
        builder = loader.parse(self.urdf_path)["articulation_builders"][0]
        builder.initial_pose = initial_pose
        if self.tool_spec:
            spec = self.tool_spec
            parent = next(
                b for b in builder.link_builders if b.name == "panda_hand_tcp"
            )
            link = builder.create_link_builder(parent)
            link.set_name("tool")
            link.set_joint_name("declared_tool_adapter_fixed_joint")
            link.set_joint_properties("fixed", [], spec["mount"], sapien.Pose())
            mount = spec["mount"].p
            vertical = mount[2] if abs(mount[0]) + abs(mount[1]) < 1e-8 else 0.0
            tool_shapes(
                link,
                spec["kind"],
                spec["half"],
                spec["mu"],
                spec["restitution"],
                side_mount=spec["side_mount"],
                height=spec.get("height"),
                vertical_mount=vertical,
                mount=mount,
            )
        self.robot = builder.build()
        self.robot_link_names = [l.name for l in self.robot.get_links()]
        if self.tool_spec:
            link = self.robot.links_map["tool"]._objs[0]
            scale = self.tool_spec["mass"] / link.mass
            link.inertia = link.inertia * scale
            link.mass = self.tool_spec["mass"]
            # The declared rigid adapter mates with the Hand housing. Exclude
            # only this fixed assembly pair, keeping fingers/object/fixture
            # collisions enabled. Preserve every existing SRDF mask bit.
            hand = self.robot.links_map["panda_hand"]._objs[0]
            for rb in (hand, link):
                for shape in rb.collision_shapes:
                    groups = list(shape.get_collision_groups())
                    groups[2] |= 1 << (28 + int(self._agent_idx or 0))
                    shape.set_collision_groups(groups)

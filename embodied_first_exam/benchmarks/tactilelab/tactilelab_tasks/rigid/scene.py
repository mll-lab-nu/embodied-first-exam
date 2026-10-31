"""Scene construction for the rigid assembly tasks.

Builds an :class:`tactilelab_tasks.backends.isaaclab_scene.IsaacLabScene` from the
``scene`` block of a task ``cfg.yaml``. The object USDs of the assembly, mechanical and
insertion sets are plain meshes with a collider and (sometimes) a mass, but no rigid
body API, so :class:`RigidTaskScene` applies the rigid-body / mass / physics
material schemas itself after spawning instead of relying on the spawner.

Object entry keys (``scene.objects[]``)::

    name: square_table_leg            # unique object name
    usd: objects/.../Object.usd       # relative to the assets directory (see assets/resolve.py)
    pos: [x, y, z]                    # env frame, metres
    ori_deg: [rx, ry, rz]             # extrinsic XYZ degrees
    scale: [1, 1, 1]
    static: false                     # true = kinematic (never moves)
    mass: 0.0231                      # kg (dynamic objects)
    friction: 0.15                    # static = dynamic friction of the bound material
    restitution: 0.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..assets.resolve import resolve_asset
from ..backends.isaaclab_scene import IsaacLabScene, ObjectCfg, SceneCfg
from ..backends.robot import RobotCfg
from ..core.types import PARKED_LEFT_ARM, TABLE_TOP_Z

__all__ = ["RigidObjectSpec", "RigidTaskScene", "build_scene_cfg", "object_spec", "object_specs"]


class RigidObjectSpec(ObjectCfg):
    """``ObjectCfg`` plus the material parameters the base spawner does not apply to USD files."""

    def __init__(
        self,
        name: str,
        usd_path: str,
        pos,
        ori_deg=(0.0, 0.0, 0.0),
        scale=(1.0, 1.0, 1.0),
        static: bool = False,
        mass: Optional[float] = None,
        friction: Optional[float] = None,
        restitution: float = 0.0,
    ):
        super().__init__(
            name=name,
            usd_path=usd_path,
            pos=tuple(pos),
            ori_deg=tuple(ori_deg),
            scale=tuple(scale),
            mass=mass,
            kinematic=bool(static),
            friction=friction,
        )
        self.restitution = float(restitution)
        self.static = bool(static)


def object_spec(o: Dict[str, Any]) -> ObjectCfg:
    """One ``scene.objects`` entry: a USD object (``usd``) or a procedural box (``shape: cuboid`` with ``dims``)."""
    name = str(o["name"])
    pos = tuple(float(v) for v in o.get("pos", (0.0, 0.0, TABLE_TOP_Z)))
    ori = tuple(float(v) for v in o.get("ori_deg", (0.0, 0.0, 0.0)))
    if o.get("shape") == "cuboid":
        kw: Dict[str, Any] = dict(
            name=name,
            shape="cuboid",
            dims=tuple(float(v) for v in o["dims"]),
            pos=pos,
            ori_deg=ori,
            kinematic=bool(o.get("static", False)),
        )
        for key in ("mass", "friction"):
            if o.get(key) is not None:
                kw[key] = float(o[key])
        if o.get("color") is not None:
            kw["color"] = tuple(float(v) for v in o["color"])
        return ObjectCfg(**kw)
    return RigidObjectSpec(
        name=name,
        usd_path=resolve_asset(str(o["usd"])),
        pos=pos,
        ori_deg=ori,
        scale=tuple(float(v) for v in o.get("scale", (1.0, 1.0, 1.0))),
        static=bool(o.get("static", False)),
        mass=None if o.get("mass") is None else float(o["mass"]),
        friction=None if o.get("friction") is None else float(o["friction"]),
        restitution=float(o.get("restitution", 0.0)),
    )


def object_specs(scene_cfg: Dict[str, Any]) -> List[ObjectCfg]:
    """Parse ``scene.objects`` into specs (asset paths resolved)."""
    return [object_spec(o) for o in scene_cfg.get("objects", [])]


def build_scene_cfg(cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0") -> SceneCfg:
    """``SceneCfg`` for a task configuration (robot gel material, parked arm, objects)."""
    scene = cfg.get("scene", {})
    gel = scene.get("gel", {})
    robot_cfg = scene.get("robot", {})
    robot = RobotCfg(
        gel_stiffness=float(gel.get("stiffness", 650.0)),
        gel_damping=float(gel.get("damping", 0.5)),
        gel_friction=float(gel.get("friction", 1.5)),
        close_magnitude=float(robot_cfg.get("close_magnitude", 0.038)),
        right_arm_q0=tuple(float(v) for v in robot_cfg.get("right_arm_q0", (0.0,) * 6)),
        left_arm_q0=tuple(float(v) for v in robot_cfg.get("left_arm_q0", PARKED_LEFT_ARM)),
    )
    return SceneCfg(robot=robot, objects=object_specs(scene), cameras=cameras, device=device)


class RigidTaskScene(IsaacLabScene):
    """Isaac Lab scene whose USD objects get rigid-body, mass and material schemas applied."""

    def _spawn_object(self, o: ObjectCfg):
        if o.usd_path is None or o.shape == "cuboid":
            return super()._spawn_object(o)
        import isaaclab.sim as sim_utils
        from isaaclab.assets import RigidObject, RigidObjectCfg
        from isaaclab.sim import schemas

        from ..core import math as m

        prim_path = f"/World/Objects/{o.name}"
        spawn = sim_utils.UsdFileCfg(usd_path=o.usd_path, scale=tuple(o.scale))
        q = m.quat_from_euler_xyz_deg(o.ori_deg)
        cfg = RigidObjectCfg(
            prim_path=prim_path,
            spawn=spawn,
            init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(o.pos), rot=tuple(float(x) for x in q)),
        )
        obj = RigidObject(cfg)  # spawns the prim; the physics view is created at sim.reset()
        rigid = sim_utils.RigidBodyPropertiesCfg(
            kinematic_enabled=bool(o.kinematic), disable_gravity=False, max_depenetration_velocity=5.0
        )
        schemas.define_rigid_body_properties(prim_path, rigid)
        if o.mass is not None and not o.kinematic:
            schemas.define_mass_properties(prim_path, sim_utils.MassPropertiesCfg(mass=float(o.mass)))
        if o.friction is not None:
            restitution = float(getattr(o, "restitution", 0.0))
            mat = sim_utils.RigidBodyMaterialCfg(
                static_friction=float(o.friction), dynamic_friction=float(o.friction), restitution=restitution
            )
            mat_path = f"{prim_path}/physicsMaterial"
            mat.func(mat_path, mat)
            self._bind_material_to_colliders(prim_path, mat_path)
        return obj

    @staticmethod
    def _bind_material_to_colliders(prim_path: str, mat_path: str) -> int:
        """Bind a material to every collider under ``prim_path`` (stronger than the baked bindings)."""
        import isaaclab.sim as sim_utils
        from isaaclab.sim.utils.stage import get_current_stage
        from pxr import Usd, UsdPhysics

        stage = get_current_stage()
        root = stage.GetPrimAtPath(prim_path)
        n = 0
        for prim in Usd.PrimRange(root):
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                sim_utils.bind_physics_material(
                    str(prim.GetPath()), mat_path, stage=stage, stronger_than_descendants=True
                )
                n += 1
        return n

    # ------------------------------------------------------------------ helpers for tasks
    def rigid_body_prim_path(self, name: str) -> str:
        """Path of the prim carrying the rigid body API of object ``name`` (its link frame)."""
        from isaaclab.sim.utils.stage import get_current_stage
        from pxr import Usd, UsdPhysics

        stage = get_current_stage()
        root = stage.GetPrimAtPath(f"/World/Objects/{name}")
        for prim in Usd.PrimRange(root):
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                return str(prim.GetPath())
        return str(root.GetPath())

    def object_mass(self, name: str) -> float:
        obj = self.objects[name]
        try:
            return float(obj.data.default_mass[0].sum().item())
        except Exception:
            return float("nan")

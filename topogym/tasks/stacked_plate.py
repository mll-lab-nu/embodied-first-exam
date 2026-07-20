from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import (
    StandardTabletopSceneBuilder,
    materials,
    TabletopBaseScene,
    tabletop_frames_from_config,
)
from topogym.world.rope import write_obj


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _wrap_angle(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    return float((float(angle) + np.pi) % (2.0 * np.pi) - np.pi)


# ---------------------------------------------------------------------------
# Sector (pac-man) disk visual mesh
# ---------------------------------------------------------------------------

def sector_disk_mesh(
    radius: float,
    thickness: float,
    sector_deg: float,
    segments: int = 48,
) -> tuple[np.ndarray, np.ndarray]:
    """A full disk with a ``sector_deg`` wedge removed (visual-only pac-man).

    Local frame: circular face in the XY plane, thickness along Z (centered at 0).
    The removed wedge is centered at local angle 0 (+X); the kept arc spans
    ``360 - sector_deg``. Faces are 0-indexed triangles for ``rope.write_obj``.
    """
    radius = float(radius)
    half_t = 0.5 * float(thickness)
    gap = np.deg2rad(float(sector_deg))
    start = 0.5 * gap
    end = 2.0 * np.pi - 0.5 * gap
    n = max(3, int(segments))
    angles = np.linspace(start, end, n)

    verts: list[list[float]] = [[0.0, 0.0, half_t], [0.0, 0.0, -half_t]]
    center_front, center_back = 0, 1
    arc_front: list[int] = []
    arc_back: list[int] = []
    for a in angles:
        x = radius * float(np.cos(a))
        y = radius * float(np.sin(a))
        arc_front.append(len(verts))
        verts.append([x, y, half_t])
        arc_back.append(len(verts))
        verts.append([x, y, -half_t])

    faces: list[list[int]] = []
    for i in range(n - 1):
        f0, f1 = arc_front[i], arc_front[i + 1]
        b0, b1 = arc_back[i], arc_back[i + 1]
        faces.append([center_front, f0, f1])       # front fan
        faces.append([center_back, b1, b0])        # back fan
        faces.append([f0, b0, b1])                 # rim
        faces.append([f0, b1, f1])
    # two flat wedge cut faces (from center out along each kept-arc endpoint)
    faces.append([center_front, center_back, arc_back[0]])
    faces.append([center_front, arc_back[0], arc_front[0]])
    faces.append([center_front, arc_front[-1], arc_back[-1]])
    faces.append([center_front, arc_back[-1], center_back])
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


# ---------------------------------------------------------------------------
# Disk URDF: full-cylinder collision + sector visual mesh, revolute about Y.
# ---------------------------------------------------------------------------

def _write_disk_urdf(
    path: Path,
    *,
    radius: float,
    thickness: float,
    color: list[float],
    sector_obj_path: str,
    joint_name: str,
    mass: float,
    joint_damping: float,
    joint_friction: float,
    collision_radius_scale: float,
) -> None:
    radius = float(radius)
    thickness = float(thickness)
    mass = float(mass)
    if mass <= 0.0:
        raise ValueError("Stacked Plate mechanism mass must be positive.")
    if not 0.1 <= float(collision_radius_scale) <= 1.0:
        raise ValueError("mechanism.collision_radius_scale must be in [0.1, 1.0].")
    coll_r = radius * float(collision_radius_scale)
    # Stand the coin up on the horizontal Y rod: a URDF cylinder/mesh sits along
    # local Z by default; rpy=(pi/2,0,0) rotates its axis onto Y so the circular
    # face lies in the XZ plane. The joint then spins the disk about that same Y.
    axis_rpy = f"{0.5 * np.pi:.9f} 0 0"
    # Solid-cylinder inertia with symmetry axis along Y (Iyy) after the rpy.
    i_sym = 0.5 * mass * radius * radius
    i_trans = mass * (3.0 * radius * radius + thickness * thickness) / 12.0
    rgba = f"{float(color[0]):.6f} {float(color[1]):.6f} {float(color[2]):.6f} 1"
    xml = f"""<?xml version="1.0"?>
<robot name="stacked_disk">
  <link name="disk_base"/>
  <link name="rotating_disk">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="{mass:.9f}"/>
      <inertia ixx="{i_trans:.9f}" ixy="0" ixz="0"
               iyy="{i_sym:.9f}" iyz="0" izz="{i_trans:.9f}"/>
    </inertial>
    <collision>
      <origin xyz="0 0 0" rpy="{axis_rpy}"/>
      <geometry>
        <cylinder radius="{coll_r:.9f}" length="{thickness:.9f}"/>
      </geometry>
    </collision>
    <visual>
      <origin xyz="0 0 0" rpy="{axis_rpy}"/>
      <geometry>
        <mesh filename="{sector_obj_path}" scale="1 1 1"/>
      </geometry>
      <material name="disk_color">
        <color rgba="{rgba}"/>
      </material>
    </visual>
  </link>
  <joint name="{joint_name}" type="continuous">
    <parent link="disk_base"/>
    <child link="rotating_disk"/>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <dynamics damping="{float(joint_damping):.9f}" friction="{float(joint_friction):.9f}"/>
  </joint>
</robot>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

@dataclass
class StackedPlateLayout:
    """Geometry + sector-alignment logic for the redesigned stacked-plate task."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(f"Stacked Plate position must have shape (3,), got {result}.")
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(f"Unsupported coordinate_frame={self.coordinate_frame!r}.")
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(f"Unsupported coordinate_frame={self.coordinate_frame!r}.")

    # -- disks --
    def disk_names(self) -> list[str]:
        return [str(name) for name in self.cfg.disks.keys()]

    def disk(self, name: str):
        return self.cfg.disks[str(name)]

    def disk_center(self, name: str) -> np.ndarray:
        return self.position_to_world(self.disk(name).center)

    def disk_radius(self, name: str) -> float:
        return float(self.disk(name).radius)

    def disk_thickness(self, name: str) -> float:
        return float(self.disk(name).thickness)

    def disk_initial_angle(self, name: str) -> float:
        return float(np.deg2rad(float(getattr(self.disk(name), "init_angle_deg", 0.0))))

    # kept for downstream/sync code that reads an initial "yaw" per articulated disk
    def plate_names(self) -> list[str]:
        return self.disk_names()

    def plate_initial_yaw(self, name: str) -> float:
        return self.disk_initial_angle(name)

    # -- sector --
    def sector_deg(self) -> float:
        return float(getattr(self.cfg.sector, "sector_deg", 70.0))

    def sector_world_angle(self, name: str, disk_angle: float) -> float:
        # All disks share the same sector-local offset (same mesh), so the sector's
        # world angle equals the joint angle up to a common constant -> use directly.
        return _wrap_angle(float(disk_angle))

    def sector_angles(self, disk_angles: dict[str, float]) -> dict[str, float]:
        return {name: self.sector_world_angle(name, angle) for name, angle in disk_angles.items()}

    def alignment_spread(self, disk_angles: dict[str, float]) -> float:
        names = self.disk_names()
        if len(names) < 2:
            return 0.0
        ref = float(disk_angles[names[0]])
        deltas = [_wrap_angle(float(disk_angles[name]) - ref) for name in names]
        return float(max(deltas) - min(deltas))

    def alignment_tolerance(self) -> float:
        return float(np.deg2rad(float(getattr(self.cfg.success, "alignment_tolerance_deg", 10.0))))

    def sectors_aligned(self, disk_angles: dict[str, float]) -> bool:
        return self.alignment_spread(disk_angles) <= self.alignment_tolerance()

    def target_angle(self) -> float:
        return float(np.deg2rad(float(getattr(self.cfg.oracle, "target_angle_deg", 90.0))))

    # -- grasp geometry (edge grab: rim point pinched, then rolled downward) --
    def grasp_azimuth(self) -> float:
        """Rim azimuth (from top, +Z toward +X) where the pinch starts."""
        physical = getattr(self.cfg, "physical", None)
        return float(np.deg2rad(float(getattr(physical, "grasp_rim_angle_deg", 0.0))))

    def roll_sign(self) -> int:
        """Which way the pinched rim point rolls; +1/-1, or 0 for shortest path."""
        physical = getattr(self.cfg, "physical", None)
        return int(getattr(physical, "roll_sign", 0))

    def grasp_radius_scale(self) -> float:
        """Fraction of the disk radius at which the pads pinch (1.0 = the rim edge)."""
        physical = getattr(self.cfg, "physical", None)
        return float(getattr(physical, "grasp_radius_scale", 1.0))

    def rim_top_world(self, name: str) -> np.ndarray:
        center = self.disk_center(name)
        radius = self.disk_radius(name)
        return np.array([center[0], center[1], center[2] + radius], dtype=float)


# ---------------------------------------------------------------------------
# State / evaluator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StackedPlatePuzzleState:
    disk_angles: dict[str, float]
    sector_angles: dict[str, float]
    alignment_spread: float
    alignment_tolerance: float

    @property
    def is_terminal(self) -> bool:
        return self.alignment_spread <= self.alignment_tolerance

    def to_info(self) -> dict[str, Any]:
        return {
            "disk_angles": {k: float(v) for k, v in self.disk_angles.items()},
            "sector_angles_deg": {k: float(np.rad2deg(v)) for k, v in self.sector_angles.items()},
            "alignment_spread_deg": float(np.rad2deg(self.alignment_spread)),
            "alignment_tolerance_deg": float(np.rad2deg(self.alignment_tolerance)),
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class StackedPlatePuzzleEvaluator:
    """Success = all disks' missing sectors rotated into angular alignment."""

    def classify(self, plate_scene: "StackedPlateScene") -> StackedPlatePuzzleState:
        sync_stacked_plate_physics(plate_scene)
        layout = plate_scene.layout
        angles = dict(plate_scene.plate_yaws)
        return StackedPlatePuzzleState(
            disk_angles=angles,
            sector_angles=layout.sector_angles(angles),
            alignment_spread=layout.alignment_spread(angles),
            alignment_tolerance=layout.alignment_tolerance(),
        )

    def is_success(self, plate_scene: "StackedPlateScene") -> bool:
        return self.classify(plate_scene).is_terminal


# ---------------------------------------------------------------------------
# Scene + sync
# ---------------------------------------------------------------------------

@dataclass
class StackedPlateScene:
    scene: Any
    manifest: EntityManifest
    layout: StackedPlateLayout
    plate_yaws: dict[str, float]
    cameras: dict = field(default_factory=dict)
    articulated_plate_entities: dict[str, Any] = field(default_factory=dict)
    plate_joint_names: dict[str, str] = field(default_factory=dict)
    plate_joint_dofs: dict[str, int] = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None


def sync_stacked_plate_physics(plate_scene: StackedPlateScene) -> None:
    for name, entity in plate_scene.articulated_plate_entities.items():
        dof = plate_scene.plate_joint_dofs.get(name)
        if dof is None:
            continue
        value = entity.get_dofs_position(dofs_idx_local=[dof])
        plate_scene.plate_yaws[name] = float(_as_numpy(value).reshape(-1)[0])


def apply_stacked_plate_visuals(plate_scene: StackedPlateScene) -> None:
    # The sector visual is embedded in each disk's URDF link, so it rotates with
    # the joint automatically; only refresh the tracked joint angles here.
    sync_stacked_plate_physics(plate_scene)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class StackedPlateSceneBuilder:
    """Build the redesigned stacked-plate scene: vertical disks on a Y rod."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = StackedPlateLayout(task_cfg, task_origin=frames.task_origin)

    def build(self, *, show_viewer: bool = False) -> StackedPlateScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        self._add_workspace(scene, manifest)
        self._add_rod(scene, manifest)
        self._add_support(scene, manifest)
        self._add_end_caps(scene, manifest)
        disk_entities, disk_joint_names = self._add_disks(scene, manifest)

        tabletop_builder.finalize(tabletop)
        disk_joint_dofs: dict[str, int] = {}
        for name, entity in disk_entities.items():
            joint = entity.get_joint(name=disk_joint_names[name])
            dof = int(np.asarray(joint.dofs_idx_local).reshape(-1)[0])
            disk_joint_dofs[name] = dof
            entity.set_dofs_position(
                [self.layout.disk_initial_angle(name)],
                dofs_idx_local=[dof],
                zero_velocity=True,
            )
        plate_scene = StackedPlateScene(
            scene=scene,
            manifest=manifest,
            layout=self.layout,
            plate_yaws={name: self.layout.disk_initial_angle(name) for name in self.layout.disk_names()},
            cameras=tabletop.cameras,
            articulated_plate_entities=disk_entities,
            plate_joint_names=disk_joint_names,
            plate_joint_dofs=disk_joint_dofs,
            tabletop=tabletop,
        )
        apply_stacked_plate_visuals(plate_scene)
        return plate_scene

    def _add_workspace(self, scene, manifest: EntityManifest) -> None:
        if not box_entity_enabled(self.task_cfg.workspace):
            return
        manifest.add(
            self.task_cfg.workspace.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(self.task_cfg.workspace.pos)),
                    size=tuple(self.task_cfg.workspace.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.workspace.color),
                name=self.task_cfg.workspace.name,
            ),
        )

    def _rod_center(self) -> np.ndarray:
        return self.layout.position_to_world(self.task_cfg.rod.center)

    def _add_rod(self, scene, manifest: EntityManifest) -> None:
        rod = getattr(self.task_cfg, "rod", None)
        if rod is None or not bool(getattr(rod, "enabled", True)):
            return
        center = self._rod_center()
        manifest.add(
            "plate_rod",
            scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(center),
                    radius=float(rod.radius),
                    height=float(rod.length),
                    euler=(90.0, 0.0, 0.0),  # default-Z cylinder axis -> world Y
                    fixed=True,
                    collision=bool(getattr(rod, "collision", True)),
                ),
                surface=materials.plastic("fixture", rod.color),
                name="plate_rod",
            ),
        )

    def _add_support(self, scene, manifest: EntityManifest) -> None:
        support = getattr(self.task_cfg, "support", None)
        if support is None or not bool(getattr(support, "enabled", False)):
            return
        center = self._rod_center()
        half = 0.5 * float(self.task_cfg.rod.length) - float(getattr(support, "end_margin", 0.02))
        bottom = self.layout.world_z(0.0)
        top = float(center[2])
        height = max(0.001, top - bottom)
        for sign, tag in ((-1.0, "l"), (1.0, "r")):
            pos = np.array([center[0], center[1] + sign * half, bottom + 0.5 * height], dtype=float)
            manifest.add(
                f"plate_support_{tag}",
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(pos),
                        radius=float(getattr(support, "radius", 0.014)),
                        height=float(height),
                        fixed=True,
                        collision=bool(getattr(support, "collision", True)),
                    ),
                    surface=materials.plastic("fixture", support.color),
                    name=f"plate_support_{tag}",
                ),
            )

    def _add_end_caps(self, scene, manifest: EntityManifest) -> None:
        vd = getattr(self.task_cfg, "visual_details", None)
        if vd is None or not bool(getattr(vd, "enabled", False)):
            return
        cap = getattr(vd, "end_cap", None)
        if cap is None or not bool(getattr(cap, "enabled", False)):
            return
        center = self._rod_center()
        half = 0.5 * float(self.task_cfg.rod.length)
        for sign, tag in ((-1.0, "l"), (1.0, "r")):
            pos = np.array([center[0], center[1] + sign * half, center[2]], dtype=float)
            manifest.add(
                f"rod_cap_{tag}",
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(pos),
                        radius=float(getattr(cap, "radius", 0.016)),
                        height=float(getattr(cap, "length", 0.006)),
                        euler=(90.0, 0.0, 0.0),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("fixture", cap.color),
                    name=f"rod_cap_{tag}",
                ),
            )

    def _add_disks(self, scene, manifest: EntityManifest) -> tuple[dict[str, Any], dict[str, str]]:
        asset_root = Path(__file__).resolve().parents[2] / "runs" / "generated_meshes" / "stacked_plate"
        asset_root.mkdir(parents=True, exist_ok=True)
        mech = getattr(self.task_cfg, "mechanism", None)
        joint_base = str(getattr(mech, "joint_name", "disk_joint")) if mech is not None else "disk_joint"
        mass = float(getattr(mech, "mass", 0.30)) if mech is not None else 0.30
        joint_damping = float(getattr(mech, "joint_damping", 0.06)) if mech is not None else 0.06
        joint_friction = float(getattr(mech, "joint_friction", 0.03)) if mech is not None else 0.03
        collision_radius_scale = float(getattr(mech, "collision_radius_scale", 0.98)) if mech is not None else 0.98
        armature = float(getattr(mech, "joint_armature", 0.01)) if mech is not None else 0.01
        contact_friction = float(getattr(mech, "contact_friction", 1.5)) if mech is not None else 1.5
        sector_deg = self.layout.sector_deg()
        segments = int(getattr(self.task_cfg.sector, "arc_segments", 48))

        entities: dict[str, Any] = {}
        joint_names: dict[str, str] = {}
        for name in self.layout.disk_names():
            radius = self.layout.disk_radius(name)
            thickness = self.layout.disk_thickness(name)
            color = [float(v) for v in _list(self.layout.disk(name).color)]
            verts, faces = sector_disk_mesh(radius, thickness, sector_deg, segments)
            obj_path = asset_root / f"{name}_sector.obj"
            write_obj(obj_path, verts, faces)
            urdf_path = asset_root / f"{name}_disk.urdf"
            joint_name = f"{joint_base}_{name}"
            _write_disk_urdf(
                urdf_path,
                radius=radius,
                thickness=thickness,
                color=color,
                sector_obj_path=str(obj_path.resolve()).replace("\\", "/"),
                joint_name=joint_name,
                mass=mass,
                joint_damping=joint_damping,
                joint_friction=joint_friction,
                collision_radius_scale=collision_radius_scale,
            )
            entity = scene.add_entity(
                gs.morphs.URDF(
                    file=str(urdf_path),
                    pos=tuple(self.layout.disk_center(name)),
                    fixed=True,
                    convexify=False,
                    recompute_inertia=False,
                    prioritize_urdf_material=True,
                    default_armature=armature,
                ),
                material=gs.materials.Rigid(friction=contact_friction),
                name=f"disk_{name}",
            )
            manifest.add(f"disk_{name}", entity)
            entities[name] = entity
            joint_names[name] = joint_name
        return entities, joint_names

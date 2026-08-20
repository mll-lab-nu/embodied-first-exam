"""Cloth Fold (docx 1.1 「对折／折角」): a square sheet, folded corner to corner.

The scene is a flat cloth on the standard tabletop and nothing else. All of the
task's difficulty is in the cloth: one gripper picks a corner up, carries it half
a turn about the diagonal, and puts it down on the opposite corner. Where the
crease lands is decided by the grasp point and the arc together, which is what
docx 1.1 says the task is testing -- it cannot be read off a local observation.

**The fold is corner-to-corner, not edge-to-edge**, and that is a physical
finding rather than a preference. docx 1.1's title covers both ("对折／折角"),
but only the corner fold works with a single grasp point. Folding a square about
a diagonal moves a triangle whose other two vertices already lie ON the fold
line: the flap hinges like a door whose hinge ends are pinned, and only the
grasped vertex travels. Folding about a centre line instead moves a rectangle
whose far 240 mm edge is unconstrained apart from an 18 mm patch at its middle,
so its two far corners stay on the table and get dragged into a heap. Measured
2026-08-20: the edge fold left the sheet 163 mm wide where 120 mm was asked for,
20 mm tall where two layers are 6 mm, and read no better than deliberately
shoving the cloth around. See `configs/task_configs/cloth_fold_*.yaml`.

Judging lives in `topogym/verification/cloth_fold_verifier.py`; the arc the hand
follows lives in `topogym/planning/cloth_fold_planner.py`. This file only says
what the scene contains and where its landmarks are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np

from topogym.core import EntityManifest
from topogym.supervision.pbd_probe import probe_particles
from topogym.world import StandardTabletopSceneBuilder, materials, textures
from topogym.world.rope import TabletopParticleFriction


def cloth_sheet_mesh(size, center, z: float, cols: int, rows: int, path: Path):
    """A flat rectangular triangle grid with texture coordinates, written as OBJ.

    This is only the CONTROL mesh: Genesis remeshes it isotropically to
    ``PBDOptions.particle_size``, so the simulated particle count is larger. The
    33x33 / 0.004 combination the config ships is the only one measured to keep
    vertex order through that remesh, and vertex order is what makes every
    material-tracking judge possible -- see the config's note before changing it.

    The ``vt`` lines matter as much as the geometry: Genesis' rasterizer keeps a
    surface's diffuse colour and TEXTURE and discards everything else (roughness,
    metallic, normal maps are raytracer-only, and the raytracer needs an
    extension this install does not have). A texture is therefore the only way to
    give the cloth any surface detail at all -- and a texture with no UVs to map
    onto does nothing. The sheet shipped without them until 2026-08-21, which is
    part of why it reads as a slab of modelling clay.

    UVs span [0, 1] exactly once over the sheet rather than tiling. Tiling would
    need the sampler to wrap, which is renderer behaviour this code cannot check;
    one full-coverage image has no such dependency, at the cost of regenerating
    the image when the sheet's size changes.
    """

    xs = np.linspace(-0.5 * float(size[0]), 0.5 * float(size[0]), int(cols))
    ys = np.linspace(-0.5 * float(size[1]), 0.5 * float(size[1]), int(rows))
    vertices = np.array(
        [[float(center[0]) + x, float(center[1]) + y, float(z)] for y in ys for x in xs],
        dtype=float,
    )
    # One UV per vertex, in the same order, so the two indices coincide in the
    # face lines below.
    uvs = np.array(
        [
            [col / max(1, int(cols) - 1), row / max(1, int(rows) - 1)]
            for row in range(int(rows))
            for col in range(int(cols))
        ],
        dtype=float,
    )
    faces = []
    for row in range(int(rows) - 1):
        for col in range(int(cols) - 1):
            lower_left = row * int(cols) + col
            lower_right = lower_left + 1
            upper_left = (row + 1) * int(cols) + col
            upper_right = upper_left + 1
            faces.append([lower_left, lower_right, upper_right])
            faces.append([lower_left, upper_right, upper_left])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        for uv in uvs:
            handle.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")
        for face in faces:
            handle.write(
                "f "
                + " ".join(f"{index + 1}/{index + 1}" for index in face)
                + "\n"
            )
    return vertices, np.asarray(faces, dtype=int)


@dataclass
class ClothFoldLayout:
    """Where the sheet is and where the fold's landmarks are, in world metres."""

    task_cfg: Any
    origin: np.ndarray

    def coordinate_frame(self) -> str:
        return str(self.task_cfg.coordinate_frame)

    def position_to_world(self, position) -> np.ndarray:
        return np.asarray(self.origin, dtype=float) + np.asarray(position, dtype=float)

    def world_z(self, z: float) -> float:
        return float(self.origin[2]) + float(z)

    @property
    def table_z(self) -> float:
        return float(self.origin[2])

    def cloth_size(self) -> np.ndarray:
        return np.asarray(list(self.task_cfg.cloth.size), dtype=float)

    def cloth_centre(self) -> np.ndarray:
        """World (x, y) of the sheet's middle. The fold line passes through it."""

        return np.asarray(self.origin, dtype=float)[:2] + np.asarray(
            list(self.task_cfg.cloth.center), dtype=float
        )

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    def _grasp_offset(self) -> np.ndarray:
        """Offset from the sheet's middle to the grasp point, in the plane.

        ``inset`` pulls the point in from the edge so the whole attachment disc
        lands on material. Centred exactly on a corner, half the disc hangs off
        the cloth and catches fewer particles on one side, which tilts the patch
        as soon as it is lifted.
        """

        half = 0.5 * self.cloth_size()
        inset = float(self.task_cfg.grasp.inset)
        mode = str(self.task_cfg.grasp.at)
        if mode == "corner":
            return np.array([half[0] - inset, half[1] - inset])
        if mode == "edge_mid":
            return np.array([half[0] - inset, 0.0])
        raise ValueError(
            f"task.grasp.at must be 'corner' or 'edge_mid', got {mode!r}."
        )

    def grasp_point(self) -> np.ndarray:
        """World point on the sheet the gripper attaches to."""

        centre = self.cloth_centre()
        return np.array([*(centre + self._grasp_offset()), self.rest_z()])

    def fold_target(self) -> np.ndarray:
        """Where the grasped point has to end up: its mirror across the line."""

        centre = self.cloth_centre()
        return np.array([*(centre - self._grasp_offset()), self.rest_z()])

    def fold_point(self) -> np.ndarray:
        """A point ON the fold line. The sheet's middle, by construction."""

        return self.cloth_centre()

    def fold_normal(self) -> np.ndarray:
        """Unit in-plane normal of the fold line, pointing at the half that lifts."""

        offset = self._grasp_offset()
        return offset / max(float(np.linalg.norm(offset)), 1e-12)

    def material_distance(self) -> float:
        """Cloth between the fold line and the grasp point, measured flat."""

        return float(np.linalg.norm(self._grasp_offset()))

    def fold_radius(self) -> float:
        """Radius of the arc the hand follows.

        The grasped point can only travel on a circle centred on the fold line --
        it is joined to that line by a fixed length of material. Reach further and
        the hand is stretching the cloth; cut inside and the sheet sags onto the
        table and gets towed sideways. `fold_slack` is the couple of percent kept
        back from the taut value.
        """

        return self.material_distance() * float(self.task_cfg.physical.fold_slack)

    def fold_steps(self) -> int:
        """Steps for the half turn, from the calibrated hand SPEED.

        A fixed step count would become a different speed the moment the arc
        changes length, and speed is the calibrated quantity: 3.6 mm a step, from
        the 120/180/240 sweep. Deriving it keeps the same speed across grasp
        positions and cloth sizes.
        """

        arc = float(np.pi * self.fold_radius())
        return max(4, int(round(arc / float(self.task_cfg.physical.fold_step_m))))

    def summary(self) -> str:
        grasp, target = self.grasp_point(), self.fold_target()
        return (
            f"grasp_at={str(self.task_cfg.grasp.at)} "
            f"grasp=({grasp[0]:+.3f},{grasp[1]:+.3f}) "
            f"target=({target[0]:+.3f},{target[1]:+.3f}) "
            f"fold_line=({self.fold_point()[0]:+.3f},{self.fold_point()[1]:+.3f}) "
            f"normal=({self.fold_normal()[0]:+.3f},{self.fold_normal()[1]:+.3f}) "
            f"material_mm={self.material_distance() * 1e3:.1f} "
            f"radius_mm={self.fold_radius() * 1e3:.1f} "
            f"arc_mm={np.pi * self.fold_radius() * 1e3:.0f} "
            f"steps={self.fold_steps()} "
            f"step_mm={np.pi * self.fold_radius() / self.fold_steps() * 1e3:.2f}"
        )


@dataclass
class ClothFoldScene:
    scene: Any
    manifest: EntityManifest
    cameras: dict[str, Any]
    frames: Any
    layout: ClothFoldLayout
    cloth: Any
    control_vertices: np.ndarray
    table_friction: Any = None
    #: The settled flat sheet, which every judge measures against. Filled in by
    #: `settle_cloth` -- it cannot be read at build time, because the sheet
    #: spawns a particle-radius above the table and has to land first.
    rest_nodes: np.ndarray | None = field(default=None)


def cloth_particles(cloth_scene: ClothFoldScene) -> np.ndarray:
    """Current ``(P, 3)`` particle positions of the sheet."""

    return probe_particles(cloth_scene.cloth)


def settle_cloth(cloth_scene: ClothFoldScene, steps: int) -> np.ndarray:
    """Let the sheet land, then record it as the rest state every judge uses.

    Without this the first samples of anything are the sheet still falling, and
    the fold's analytic targets would be built from a mid-air layout.
    """

    for _ in range(max(0, int(steps))):
        cloth_scene.scene.step()
    cloth_scene.rest_nodes = cloth_particles(cloth_scene)
    return cloth_scene.rest_nodes


def remesh_report(control: np.ndarray, simulated: np.ndarray) -> str:
    """Did Genesis' remesh keep vertex order? Everything else depends on it.

    Order survives when the simulated set is a clean subdivision of the control
    mesh, and then control vertex *i* is still simulated particle *i*. When it
    does not, the fold line's material, layer membership and the per-particle
    targets are all unavailable -- so this is printed on every build, not only
    when something looks wrong.
    """

    control = np.asarray(control, dtype=float)
    simulated = np.asarray(simulated, dtype=float)
    shared = min(len(control), len(simulated))
    offset = (
        float(np.abs(control[:shared] - simulated[:shared]).max()) if shared else float("nan")
    )
    preserved = shared == len(control) and offset < 1e-6
    return (
        f"order_preserved={'yes' if preserved else 'NO'} "
        f"control={len(control)} simulated={len(simulated)} "
        f"max_offset_mm={offset * 1e3:.3f}"
    )


class ClothFoldSceneBuilder:
    """Standard tabletop, one PBD cloth sheet, optional landmark markers."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg

    def build(
        self,
        *,
        show_viewer: bool = False,
        include_robot: bool = True,
        markers: bool = False,
    ) -> ClothFoldScene:
        cloth_cfg = self.task_cfg.cloth
        builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            # The cloth's collision thickness and the layer judges' resolution
            # are the same number, so it is a scene option rather than a material
            # one and has to reach gs.Scene before anything is added.
            pbd_options=gs.options.PBDOptions(
                particle_size=float(cloth_cfg.particle_size)
            ),
        )
        tabletop = builder.create(show_viewer=show_viewer, include_robot=include_robot)
        scene = tabletop.scene
        layout = ClothFoldLayout(
            self.task_cfg, np.asarray(tabletop.frames.task_origin, dtype=float)
        )

        path = Path(str(cloth_cfg.mesh.output_dir)) / "cloth_fold_sheet.obj"
        vertices, _faces = cloth_sheet_mesh(
            list(cloth_cfg.size),
            layout.cloth_centre(),
            layout.rest_z(),
            int(cloth_cfg.mesh.cols),
            int(cloth_cfg.mesh.rows),
            path,
        )
        cloth = scene.add_entity(
            gs.morphs.Mesh(
                file=str(path),
                pos=(0.0, 0.0, 0.0),
                scale=1.0,
                decimate=False,
                convexify=False,
                fixed=False,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.PBD.Cloth(
                rho=float(cloth_cfg.rho),
                # Cloth-against-cloth, which is what the two layers rest on each
                # other with. The table is a separate matter entirely -- see
                # `TabletopParticleFriction` below.
                static_friction=float(cloth_cfg.static_friction),
                kinetic_friction=float(cloth_cfg.kinetic_friction),
                stretch_compliance=float(cloth_cfg.stretch_compliance),
                bending_compliance=float(cloth_cfg.bending_compliance),
                stretch_relaxation=float(cloth_cfg.stretch_relaxation),
                bending_relaxation=float(cloth_cfg.bending_relaxation),
                air_resistance=float(cloth_cfg.air_resistance),
            ),
            surface=self._cloth_surface(cloth_cfg),
            name=str(cloth_cfg.name),
        )
        tabletop.manifest.add(str(cloth_cfg.name), cloth)
        if markers:
            self._add_landmarks(scene, tabletop.manifest, layout)
        builder.finalize(tabletop)

        cloth_scene = ClothFoldScene(
            scene=scene,
            manifest=tabletop.manifest,
            cameras=tabletop.cameras,
            frames=tabletop.frames,
            layout=layout,
            cloth=cloth,
            control_vertices=vertices,
            table_friction=self._install_table_friction(scene, cloth, layout),
        )
        print(
            f"cloth_fold scene particles={len(cloth_particles(cloth_scene))} "
            f"{remesh_report(vertices, cloth_particles(cloth_scene))} "
            f"{layout.summary()}",
            flush=True,
        )
        return cloth_scene

    def _cloth_surface(self, cloth_cfg):
        """The sheet's surface, with a woven diffuse image when one is asked for.

        A diffuse texture is the ONLY way to give this cloth surface detail: the
        rasterizer builds its visual from `surface.get_rgba()` and drops
        roughness, metallic, normal and emissive, and the raytracer that would
        honour them needs a LuisaRender build this install does not have. Without
        it the sheet is one flat colour with a lighting gradient across it, which
        is most of why it read as modelling clay.
        """

        texture_cfg = getattr(cloth_cfg, "texture", None)
        image = None
        if texture_cfg is not None and bool(texture_cfg.enabled):
            image = textures.fabric_weave(
                color=list(cloth_cfg.color),
                size_m=list(cloth_cfg.size),
                thread_pitch_m=float(texture_cfg.thread_pitch),
                pixels_per_thread=int(texture_cfg.pixels_per_thread),
                thread_shading=float(texture_cfg.thread_shading),
                weft_tint=float(texture_cfg.weft_tint),
                fibre_noise=float(texture_cfg.fibre_noise),
                cloud_noise=float(texture_cfg.cloud_noise),
                seed=int(texture_cfg.seed),
            )
        surface = materials.plastic(
            "deformable", list(cloth_cfg.color), vis_mode="visual", texture=image
        )
        if image is not None:
            # Says `FLAT(...)` if the texture is set somewhere the renderer does
            # not read, which otherwise looks exactly like not setting one.
            print(
                "cloth_fold texture "
                f"{materials.texture_reaches_renderer(surface)} "
                f"thread_pitch_mm={float(texture_cfg.thread_pitch) * 1e3:.1f}",
                flush=True,
            )
        return surface

    def _install_table_friction(self, scene, cloth, layout: ClothFoldLayout):
        """Sustained cloth-against-table friction, which Genesis does not provide.

        Its deformable-against-rigid friction scales with the normal velocity and
        only acts while a particle is driving INTO the surface, so a sheet already
        lying on the table gets essentially none however high the table's
        `coup_friction` is set. Without this the whole sheet is towed across the
        table during a fold -- measured, and it is why `world/rope.py` grew a
        Coulomb model of its own. That model changes velocities only: moving
        positions instead gets rebuilt by PBD into enormous velocities, which is
        how the ropes used to be flung out of the scene.
        """

        friction_cfg = getattr(self.task_cfg.cloth, "tabletop_friction", None)
        if friction_cfg is None or not bool(friction_cfg.enabled):
            return None
        return TabletopParticleFriction(
            scene,
            [cloth],
            surface_z=layout.table_z,
            contact_band=float(friction_cfg.contact_band),
            static_mu=float(friction_cfg.static_mu),
            kinetic_mu=float(friction_cfg.kinetic_mu),
            dt=float(self.env_cfg.sim.dt),
            gravity=abs(float(self.env_cfg.sim.gravity[2])),
            max_load_factor=float(friction_cfg.max_load_factor),
        ).install()

    def _add_landmarks(self, scene, manifest: EntityManifest, layout: ClothFoldLayout) -> None:
        """Collision-free markers for the grasp point, the target and the crease.

        For looking at the scene, not for the episode: `collision=False` keeps
        them out of the physics entirely, so a run with them is the same run.
        """

        lift = 0.010
        grasp, target = layout.grasp_point(), layout.fold_target()
        for name, point, color in (
            ("marker_grasp", grasp, (0.10, 0.75, 0.25)),
            ("marker_fold_target", target, (0.95, 0.55, 0.10)),
        ):
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=(float(point[0]), float(point[1]), float(point[2]) + lift),
                        radius=0.008,
                        height=0.020,
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("deformable", list(color)),
                    name=name,
                ),
            )
        # The crease: a bar through the sheet's middle, along the fold line.
        normal = layout.fold_normal()
        centre = layout.fold_point()
        manifest.add(
            "marker_fold_line",
            scene.add_entity(
                gs.morphs.Box(
                    pos=(float(centre[0]), float(centre[1]), layout.rest_z() + lift),
                    size=(0.004, float(np.linalg.norm(layout.cloth_size())), 0.004),
                    # The bar runs ALONG the line, so it is the normal's direction
                    # turned a quarter turn.
                    euler=(0.0, 0.0, float(np.degrees(np.arctan2(normal[1], normal[0])))),
                    fixed=True,
                    collision=False,
                ),
                surface=materials.plastic("deformable", [0.20, 0.45, 0.95]),
                name="marker_fold_line",
            ),
        )

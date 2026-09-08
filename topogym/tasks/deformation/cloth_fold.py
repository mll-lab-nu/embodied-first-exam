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

**Variation (2026-09-06; axis swapped 2026-09-07).** Which corner is taken
(`grasp.corner`, four names from the arm's point of view), how far along the
diagonal it is carried (`goal.fold_fraction`) -- both told only by
`goal.instruction`, because the sheet is plain and square -- where the sheet
lies (`center_y` drawn, `center_x` derived so the far corner stays inside the
arm's reach disc) and how taut the arc is (`fold_slack`) are drawn per seed by
the task yaml's ``variation:`` block. The feasibility rows and the derivation live in
`_cloth_fold_geometry.py` (numpy only) so the offline gate and the corner
harness can run them without Genesis.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np

from topogym.core import EntityManifest
from topogym.supervision.pbd_probe import probe_particles
from topogym.world import StandardTabletopSceneBuilder, materials, textures
from topogym.world.rope import TabletopParticleFriction

from ._cloth_fold_geometry import (
    CORNER_WORDS,
    EXTENT_WORDS,
    center_x_from_frac,
    cloth_fold_checks,
    corner_name,
    corner_signs,
    fold_fraction,
    grasp_offset,
    mesh_diagonal,
)


def cloth_sheet_mesh(
    size, center, z: float, cols: int, rows: int, path: Path, *, diagonal: str = "up"
):
    """A flat rectangular triangle grid with texture coordinates, written as OBJ.

    ``diagonal`` says which way each quad is split: ``"up"`` (lower-left to
    upper-right, the layout the task was calibrated on) or ``"down"``. It is
    chosen per fold so the crease crosses the diagonal edges -- see
    `_cloth_fold_geometry.mesh_diagonal` for the measurement behind that. Only
    a uniform diagonal keeps Genesis' remesh a clean subdivision (alternating
    them per quad came back as 4604 particles, order lost).

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
    if diagonal not in ("up", "down"):
        raise ValueError(f"diagonal must be 'up' or 'down', got {diagonal!r}.")
    faces = []
    for row in range(int(rows) - 1):
        for col in range(int(cols) - 1):
            lower_left = row * int(cols) + col
            lower_right = lower_left + 1
            upper_left = (row + 1) * int(cols) + col
            upper_right = upper_left + 1
            if diagonal == "up":
                faces.append([lower_left, lower_right, upper_right])
                faces.append([lower_left, upper_right, upper_left])
            else:
                faces.append([lower_left, lower_right, upper_left])
                faces.append([lower_right, upper_right, upper_left])
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
    #: World position of the task frame's origin. Zero when the layout is built
    #: from the task config alone (offline gate, corner harness): every
    #: feasibility row is task-frame arithmetic and never needs it.
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))

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

        return np.asarray(self.origin, dtype=float)[:2] + np.array(
            [float(self.task_cfg.cloth.center_x), float(self.task_cfg.cloth.center_y)],
            dtype=float,
        )

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    @property
    def corner(self) -> str:
        """Which corner is taken: `grasp.corner`, one of the four names."""

        return corner_name(self.task_cfg)

    def corner_signs(self) -> tuple[int, int]:
        """``(sx, sy)``: which way the grasped corner lies from the sheet's middle."""

        return corner_signs(self.task_cfg)

    def _grasp_offset(self) -> np.ndarray:
        """Offset from the sheet's middle to the grasp point, in the plane.

        Decided by `grasp.corner` alone (the sign pair); the point is the tip
        itself. Everything else -- the fold line's normal, the put-down point,
        the arc's radius, the wrist yaw -- is read off this one vector and
        `goal.fold_fraction`, so a different corner changes nothing else in the
        layout.
        """

        return grasp_offset(self.task_cfg)

    def with_corner(self, name: str) -> "ClothFoldLayout":
        """The same layout with a different corner taken.

        For the `fixed_corner` control motion, which plans as if the
        instruction always named the baseline corner while the judge scores
        the corner the instruction actually named.
        """

        view = copy.deepcopy(self.task_cfg)
        view.grasp.corner = str(name)
        return ClothFoldLayout(view, np.asarray(self.origin, dtype=float))

    def with_fold_fraction(self, value: float) -> "ClothFoldLayout":
        """The same layout folded a different distance along the diagonal.

        For the `fixed_fold` control motion, which plans as if the instruction
        always said corner-to-corner while the judge scores the fold the
        instruction actually asked for.
        """

        view = copy.deepcopy(self.task_cfg)
        view.goal.fold_fraction = float(value)
        return ClothFoldLayout(view, np.asarray(self.origin, dtype=float))

    def mesh_diagonal(self) -> str:
        """Which way the control mesh's diagonals run for this corner (see geometry)."""

        return mesh_diagonal(self.task_cfg)

    def fold_fraction(self) -> float:
        """How far along the diagonal the corner is carried; 1.0 is corner to corner."""

        return fold_fraction(self.task_cfg)

    def instruction(self) -> str:
        """`goal.instruction` with the corner's name and the fold's extent filled in."""

        return str(self.task_cfg.goal.instruction).format(
            corner=CORNER_WORDS[self.corner], extent=EXTENT_WORDS[self.fold_fraction()]
        )

    def grasp_point(self) -> np.ndarray:
        """World point on the sheet the gripper attaches to."""

        centre = self.cloth_centre()
        return np.array([*(centre + self._grasp_offset()), self.rest_z()])

    def fold_target(self) -> np.ndarray:
        """Where the grasped point has to end up: its mirror across the fold line.

        Mirroring across a line offset by ``d`` towards the grasped corner puts
        it at ``centre + (1 - 2f) * offset``: the opposite corner at f = 1, the
        sheet's middle at f = 0.5.
        """

        centre = self.cloth_centre()
        travel = (1.0 - 2.0 * self.fold_fraction()) * self._grasp_offset()
        return np.array([*(centre + travel), self.rest_z()])

    def fold_point(self) -> np.ndarray:
        """A point ON the fold line: the middle, pushed out towards the grasped corner.

        At `goal.fold_fraction` 1.0 this is the middle itself and the line is
        the other diagonal -- the layout every reading was calibrated on. Below
        that the line slides towards the grasped corner by
        ``material x (1 - fraction)``, so less of the sheet moves.
        """

        offset = self._grasp_offset()
        shift = float(np.linalg.norm(offset)) * (1.0 - self.fold_fraction())
        return self.cloth_centre() + shift * self.fold_normal()

    def fold_normal(self) -> np.ndarray:
        """Unit in-plane normal of the fold line, pointing at the half that lifts."""

        offset = self._grasp_offset()
        return offset / max(float(np.linalg.norm(offset)), 1e-12)

    def material_distance(self) -> float:
        """Cloth between the fold line and the grasp point, measured flat.

        Shrinks with `goal.fold_fraction`, and the arc radius and the step
        count follow it: 16.97 / 12.73 / 8.49 cm of material at 1.0 / 0.75 /
        0.5, and 145 / 109 / 73 steps at the calibrated 3.6 mm a step.
        """

        return float(np.linalg.norm(self._grasp_offset())) * self.fold_fraction()

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

    def grasp_yaw(self) -> float | None:
        """Which way the gripper should face, radians about world Z; None = arm's own.

        `grasp.finger_axis: across` (the default) points the tool along the fold
        normal, i.e. the direction the held corner travels; `arm_default`
        returns None and leaves the arm's orientation alone -- the fallback
        when the wrist cannot hold the commanded angle (the four corners ask
        for +-45 and +-135 degrees, and cloth_unroll measured a 180-degree
        yaw reversal as 34-43 degrees of wrist tilt).

        Along the fold normal, for two reasons that agree:

        - it is how a hand pinches a corner -- fingers across the corner,
          perpendicular to the pull, not at some unrelated angle to it;
        - it is much easier on the wrist. Holding the arm's default orientation
          instead means the tool's yaw stays fixed in the WORLD while the arm
          swings through 180 degrees around a diagonal, which drives the last
          joint through a large range for no reason. Genesis' `continuous_ik`
          runs one seeded solve and returns whatever it reached without saying it
          fell short, so an unreachable orientation shows up not as an error but
          as an arm quietly in the wrong pose -- measured 2026-08-20 as a hand
          42 mm off its command with the gripper rolled flat onto the sheet.
        """

        mode = str(self.task_cfg.grasp.finger_axis)
        if mode == "arm_default":
            return None
        if mode != "across":
            raise ValueError(
                f"grasp.finger_axis must be 'across' or 'arm_default', got {mode!r}."
            )
        normal = self.fold_normal()
        return float(np.arctan2(normal[1], normal[0]))

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres; task frame.
        """

        return cloth_fold_checks(self.task_cfg)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"cloth_fold layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )

    def summary(self) -> str:
        grasp, target = self.grasp_point(), self.fold_target()
        yaw = self.grasp_yaw()
        return (
            f"grasp_at={str(self.task_cfg.grasp.at)} corner={self.corner} "
            f"fold_fraction={self.fold_fraction():.2f} "
            f"grasp=({grasp[0]:+.3f},{grasp[1]:+.3f}) "
            f"target=({target[0]:+.3f},{target[1]:+.3f}) "
            f"fold_line=({self.fold_point()[0]:+.3f},{self.fold_point()[1]:+.3f}) "
            f"normal=({self.fold_normal()[0]:+.3f},{self.fold_normal()[1]:+.3f}) "
            f"material_mm={self.material_distance() * 1e3:.1f} "
            f"radius_mm={self.fold_radius() * 1e3:.1f} "
            f"arc_mm={np.pi * self.fold_radius() * 1e3:.0f} "
            f"steps={self.fold_steps()} "
            f"grasp_yaw_deg={'arm_default' if yaw is None else f'{np.degrees(yaw):+.1f}'} "
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
        # Before anything is added: a layout that fails a feasibility row is a
        # config error, not a run to spend a scene build on.
        _assert_literal_copies(self.task_cfg)
        layout.validate()

        path = Path(str(cloth_cfg.mesh.output_dir)) / f"cloth_fold_sheet_{layout.mesh_diagonal()}.obj"
        vertices, _faces = cloth_sheet_mesh(
            list(cloth_cfg.size),
            layout.cloth_centre(),
            layout.rest_z(),
            int(cloth_cfg.mesh.cols),
            int(cloth_cfg.mesh.rows),
            path,
            diagonal=layout.mesh_diagonal(),
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
            f"mesh_diagonal={layout.mesh_diagonal()} "
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
                pattern=str(texture_cfg.pattern),
                accent_color=list(texture_cfg.accent_color),
                stripe_pitch_m=float(texture_cfg.stripe_pitch),
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


def _assert_literal_copies(task_cfg) -> None:
    """The yaml's literal copy of the workspace box must still match `common`.

    `checks()` reads `workspace.x / y / z`, and the variation harness loads the
    task yaml alone, where `${common...}` cannot resolve -- so the task yaml
    carries literals, and the one place with both in hand asserts they agree.
    """

    root = task_cfg._get_root() if hasattr(task_cfg, "_get_root") else None
    common = getattr(root, "common", None) if root is not None else None
    if common is None:
        return
    ws = common.manipulation_space.workspace
    for axis in ("x", "y", "z"):
        want = [float(v) for v in ws[axis]]
        got = [float(v) for v in task_cfg.workspace[axis]]
        if want != got:
            raise ValueError(
                f"cloth_fold: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
            )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``: the sheet's
    x position from its unit fraction, in the window the drawn corner,
    `center_y` and `goal.fold_fraction` leave under the reach disc. A
    ``ValueError`` (empty window) rejects the draw.
    """

    task_cfg.cloth.center_x = center_x_from_frac(task_cfg, float(task_cfg.cloth.center_x_frac))


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    ClothFoldLayout(task_cfg).validate()

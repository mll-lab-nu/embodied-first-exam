"""Cloth Unroll (docx 1.3「展开自身卷曲的布带」): a roll on a bar, pulled flat.

The scene is a washroom paper dispenser: two posts carrying a horizontal bar,
with a cloth band wound twice around the bar, hanging off it and lying on the
table. The gripper takes the flat end and drags it along the table; the roll pays
out material and the band ends up flat, one layer, at its full length.

**Why a dispenser and not docx 1.3's loose roll.** docx has the roll lying on the
table, held by nothing, unrolling as it is pulled. Two measurements say that will
not work here:

- The roll is the heaviest part of the band and touches the table along a line,
  so pulling the free end is at least as likely to tow the whole thing as to
  unroll it. In `cloth_unpleat` the anchor was a long flat run BEYOND the
  feature; a roll at the end of the band has nothing beyond it. The bar replaces
  a friction anchor with a rigid one.
- Nothing holds the roll's shape. Genesis 1.2.1 ignores `bending_compliance`
  entirely -- measured 2026-08-23 across seven orders of magnitude with no change
  in any reading -- so this cloth has no crease stiffness at all, and
  `cloth_unpleat`'s authored pleat lay down inside 25 steps. The bar supports the
  innermost turn, which is the part a free roll has nothing to stand on.

It also settles a material conflict. `cloth_unpleat` raised cloth-against-cloth
friction to 0.4 to stop its three layers coming apart; unrolling needs those
layers to slide over each other, which is the opposite. With the bar there is no
conflict: low friction lets the outer wrap peel off the one beneath it, high
friction turns the whole roll about the bar, and either pays material out.

**The gripper pulls in a straight line and never rotates.** Orbiting the roll
would force the wrist to follow through two full turns, which no arm's last joint
can do in one grasp. Pulling straight puts all of the rotation in the roll, so
the held end keeps its orientation for free -- which is what "the gripper's pose
relative to the cloth stays fixed" actually asks for. The travel fits in one
reach, so as shipped that is one continuous stroke; the multi-stroke machinery
below is kept for a larger `turns`, which is the only thing that puts the travel
past what the arm can reach.

Judging lives in `topogym/verification/cloth_unroll_verifier.py`; the strokes live
in `topogym/planning/cloth_unroll_planner.py`; the roll's control mesh comes from
`cloth_profile_mesh.spiral_profile`. This file only says what the scene contains
and where its landmarks are.
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

from .cloth_fold import remesh_report
from .cloth_profile_mesh import (
    edge_report,
    resample_polyline,
    spiral_landmarks,
    spiral_profile,
    sweep_profile_mesh,
    texture_size_m,
)


@dataclass
class ClothUnrollLayout:
    """Where the dispenser is and where the band's landmarks are, in world metres."""

    task_cfg: Any
    origin: np.ndarray
    _profile: np.ndarray | None = field(default=None, init=False, repr=False)
    #: The free end as measured after settling, and again after every stroke.
    _grasp: np.ndarray | None = field(default=None, init=False, repr=False)

    def coordinate_frame(self) -> str:
        return str(self.task_cfg.coordinate_frame)

    @property
    def material_axis(self) -> int:
        """World axis the band pays out along: 0 for x, 1 for y.

        The bar runs along the OTHER horizontal axis, so this also fixes the
        dispenser's orientation. y as shipped, which puts the bar along x and the
        band paying out toward the arm -- the same axis `cloth_unpleat` pulls
        along, and the one its reach was measured on.
        """

        axis = str(self.task_cfg.cloth.material_axis).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        return 0 if axis == "x" else 1

    @property
    def bar_axis(self) -> int:
        """The horizontal axis the bar runs along, which the band's width follows."""

        return 1 - self.material_axis

    @property
    def table_z(self) -> float:
        return float(self.origin[2])

    def world_z(self, z: float) -> float:
        return float(self.origin[2]) + float(z)

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    def bar_centre(self) -> np.ndarray:
        """World (x, y) of the bar's axis. Every profile offset is from here."""

        return np.asarray(self.origin, dtype=float)[:2] + np.asarray(
            list(self.task_cfg.cloth.center), dtype=float
        )

    def bar_height(self) -> float:
        return self.world_z(float(self.task_cfg.dispenser.bar_height))

    def _plan_point(self, material: float, height: float) -> np.ndarray:
        """A world point from a (material-offset, height) pair on the band's axes."""

        centre = self.bar_centre()
        point = np.zeros(3, dtype=float)
        point[self.material_axis] = centre[self.material_axis] + float(material)
        point[self.bar_axis] = centre[self.bar_axis]
        point[2] = self.world_z(height)
        return point

    def profile(self) -> np.ndarray:
        if self._profile is None:
            cloth = self.task_cfg.cloth
            dispenser = self.task_cfg.dispenser
            self._profile = spiral_profile(
                material_length=float(cloth.material_length),
                bar_radius=float(dispenser.bar_radius),
                clearance=float(cloth.roll.clearance),
                pitch=float(cloth.roll.pitch),
                turns=float(cloth.roll.turns),
                bar_height=float(dispenser.bar_height),
                rest_z=float(cloth.z),
                spacing=float(cloth.mesh.spacing),
            )
        return self._profile

    def landmarks(self) -> dict:
        return spiral_landmarks(
            self.profile(),
            bar_height=float(self.task_cfg.dispenser.bar_height),
            rest_z=float(self.task_cfg.cloth.z),
        )

    def material_length(self) -> float:
        return float(self.task_cfg.cloth.material_length)

    def rolled_length(self) -> float:
        """Material wound on the bar. The pull has to pay out exactly this."""

        return float(self.landmarks()["rolled"])

    # ------------------------------------------------------------------ grasp

    def design_grasp_point(self) -> np.ndarray:
        """Where the mesh puts the band's free end, inset for the disc."""

        marks = self.landmarks()
        end = marks["free_end_s"] - float(self.task_cfg.grasp.edge_inset)
        return self._plan_point(end, float(self.task_cfg.cloth.z))

    def grasp_point(self) -> np.ndarray:
        """The free end: observed once settled, design before."""

        return self._grasp if self._grasp is not None else self.design_grasp_point()

    def observe(self, nodes) -> np.ndarray:
        """Find the band's current free end and use it until the next call.

        Called before EVERY stroke, not just the first. The end moves the length
        of each pull, so a stroke planned from the previous stroke's grasp point
        reaches into cloth that has already gone past -- and reaching for a
        position the cloth has left is how `cloth_unpleat`'s first run failed.

        Taken as the material furthest along the pay-out axis, on the band's
        centre line, then pulled back in by `edge_inset`. Restricted to material
        lying on the table so the roll itself can never be mistaken for the end.
        """

        nodes = np.asarray(nodes, dtype=float)
        centre = self.bar_centre()
        material, across = self.material_axis, self.bar_axis
        band = float(self.task_cfg.grasp.attach_radius)
        flat = self.rest_z() + 2.0 * float(self.task_cfg.cloth.particle_size)
        near = np.flatnonzero(
            (np.abs(nodes[:, across] - centre[across]) <= band) & (nodes[:, 2] <= flat)
        )
        if near.size == 0:
            raise ValueError(
                f"no material lying on the table within {band:.3f} m of the band's "
                f"centre line at {centre[across]:+.4f}; nothing to grasp."
            )
        end = float(nodes[near, material].max())
        point = self._plan_point(0.0, float(self.task_cfg.cloth.z))
        point[material] = end - float(self.task_cfg.grasp.edge_inset)
        # Height of the material AT the grasp, not the highest particle anywhere
        # on the centre line. Those differ, and the second one is useless: the
        # `flat` filter above is an upper bound, so its max is that bound
        # whenever ANY particle in the strip is near it. Measured 2026-08-24:
        # the grasp came back at 0.9295 against a ceiling of 0.9296 while the
        # band rested at 0.9216 -- 7.9 mm high, nearly the whole
        # `touch_clearance`. `attach_radius` covered for it, but the pads were
        # descending to the wrong place.
        at = near[
            np.abs(nodes[near, material] - point[material])
            <= float(self.task_cfg.grasp.attach_radius)
        ]
        point[2] = float(nodes[at, 2].max()) if at.size else self.rest_z()
        self._grasp = point
        return self._grasp

    # ------------------------------------------------------------------ pull

    def pull_direction(self) -> np.ndarray:
        """Unit vector the hand pulls along: away from the bar, in plane."""

        direction = np.zeros(3, dtype=float)
        direction[self.material_axis] = 1.0
        return direction

    def pull_total(self) -> float:
        """Total travel: how far the free end must move to lay the band flat.

        Not a tuned number -- it comes off the profile (`flat_travel`), and
        `pull_scale` is the only slack, for whatever the bar's friction keeps.

        It is NOT the material wound on the bar, which is what this returned until
        2026-08-24. Pulling `rolled` empties the roll and still leaves the drape
        -- the material hanging between the bar and the table -- unlaid, so it
        drops onto the band that has already been paid out. Measured: the roll
        emptied (`on_bar=0`) and the band still finished at 215 mm of its 260 mm
        with 114 doubled cells.
        """

        return float(self.landmarks()["flat_travel"]) * float(
            self.task_cfg.physical.pull_scale
        )

    def final_grasp_position(self) -> float:
        """Where the hand finishes, along the pay-out axis.

        Worth having as its own reading because of what it does NOT depend on.
        Substituting the definitions leaves

            centre + inner_s + material_length - edge_inset

        so the roll's radius, pitch and turn count cancel completely: winding
        tighter or adding a turn changes where the pull STARTS, never where it
        ends. Only the dispenser's position, the material's length and the grasp
        inset move it, which is the whole list of levers when the finish is out of
        the arm's reach.
        """

        return float(self.final_grasp_point()[self.material_axis])

    def stroke_count(self) -> int:
        """How many grasps the travel is split into.

        `stroke_m` is a CEILING on one stroke, not its length, and the shipped
        config sets it ABOVE the total so there is exactly one continuous stroke.

        Splitting is not a reach device and it is worth saying so, because that is
        what it was mistaken for until 2026-08-24: the hand ends up at the start
        plus the TOTAL however the travel is cut, so cutting it buys nothing in
        reach and costs a release-retreat-reapproach-regrasp cycle per cut. What
        splitting is for is a single stroke's tracking residual, and the machinery
        earns its place when a larger `turns` pushes the travel past what the arm
        can reach at all.

        When it does split, it splits EVENLY rather than taking full-length
        strokes and a short remainder -- a remainder left for last lands exactly
        where the arm is weakest.
        """

        return max(1, int(np.ceil(self.pull_total() / float(self.task_cfg.physical.stroke_m))))

    def stroke_distance(self) -> float:
        """How far one grasp pulls: the total, divided evenly."""

        return self.pull_total() / self.stroke_count()

    def final_grasp_point(self) -> np.ndarray:
        """Where the hand ends up after the last stroke.

        Exposed so the offline check can assert it against the arm's measured
        envelope rather than trusting the arithmetic in a comment.
        """

        return self.grasp_point() + self.pull_direction() * self.pull_total()

    def stroke_steps(self) -> int:
        """Steps for one stroke, from the calibrated hand SPEED, as in 1.2."""

        return max(
            4,
            int(round(self.stroke_distance() / float(self.task_cfg.physical.pull_step_m))),
        )

    def grasp_yaw(self) -> float | None:
        """Which way the wrist faces, or None to leave the arm's own orientation.

        Same knob and the same reason as `cloth_unpleat`: which setting the arm
        can hold out at the end of a pull is a measured question, and holding an
        orientation it cannot quite reach costs position silently.
        """

        mode = str(self.task_cfg.grasp.finger_axis)
        if mode == "arm_default":
            return None
        direction = self.pull_direction()
        yaw = float(np.arctan2(direction[1], direction[0]))
        if mode == "across":
            return yaw
        if mode == "along":
            return yaw + 0.5 * float(np.pi)
        raise ValueError(
            f"grasp.finger_axis must be 'across', 'along' or 'arm_default', "
            f"got {mode!r}."
        )

    def summary(self) -> str:
        marks = self.landmarks()
        grasp = self.grasp_point()
        return (
            f"axis={'xy'[self.material_axis]} "
            f"bar=({self.bar_centre()[0]:+.3f},{self.bar_centre()[1]:+.3f},"
            f"{self.bar_height():.3f}) "
            f"grasp=({grasp[0]:+.3f},{grasp[1]:+.3f},{grasp[2]:+.3f}) "
            f"material_mm={marks['material_length'] * 1e3:.0f} "
            f"rolled_mm={marks['rolled'] * 1e3:.1f} "
            f"roll_dia_mm={2 * marks['roll_radius'] * 1e3:.1f} "
            f"flat_run_mm={marks['flat_run'] * 1e3:.1f} "
            f"plan_span_mm={marks['plan_span'] * 1e3:.1f} "
            f"stored_mm={marks['stored'] * 1e3:.1f} "
            f"strokes={self.stroke_count()}x{self.stroke_distance() * 1e3:.0f}mm "
            f"steps_per_stroke={self.stroke_steps()}"
        )


@dataclass
class ClothUnrollScene:
    scene: Any
    manifest: EntityManifest
    cameras: dict[str, Any]
    frames: Any
    layout: ClothUnrollLayout
    cloth: Any
    control_vertices: np.ndarray
    grid: tuple[int, int]
    table_friction: Any = None
    rest_nodes: np.ndarray | None = field(default=None)


def band_particles(band: ClothUnrollScene) -> np.ndarray:
    """Current ``(P, 3)`` particle positions of the band."""

    return probe_particles(band.cloth)


def settle_band(band: ClothUnrollScene, steps: int) -> np.ndarray:
    """Let the band settle onto the bar and the table, then record the rest state.

    Load-bearing here for the same reason as in `cloth_unpleat`: the roll is
    authored into the mesh rather than wound by anything, so whether it stays on
    the bar at all is decided during this settle. `tests/roll_settle_spike.py`
    asks that question on its own, before any arm exists.
    """

    for _ in range(max(0, int(steps))):
        band.scene.step()
    band.rest_nodes = band_particles(band)
    return band.rest_nodes


class ClothUnrollSceneBuilder:
    """Standard tabletop, a two-post dispenser, one PBD cloth band wound on it."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg

    def build(
        self, *, show_viewer: bool = False, include_robot: bool = True
    ) -> ClothUnrollScene:
        cloth_cfg = self.task_cfg.cloth
        builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            pbd_options=gs.options.PBDOptions(
                particle_size=float(cloth_cfg.particle_size)
            ),
        )
        tabletop = builder.create(show_viewer=show_viewer, include_robot=include_robot)
        scene = tabletop.scene
        layout = ClothUnrollLayout(
            self.task_cfg, np.asarray(tabletop.frames.task_origin, dtype=float)
        )

        self._add_dispenser(scene, tabletop.manifest, layout)

        spacing = float(cloth_cfg.mesh.spacing)
        samples = resample_polyline(layout.profile(), spacing)
        path = Path(str(cloth_cfg.mesh.output_dir)) / "cloth_unroll_band.obj"
        vertices, _faces, cols, rows = sweep_profile_mesh(
            samples,
            width=float(cloth_cfg.width),
            spacing=spacing,
            centre=layout.bar_centre(),
            table_z=layout.table_z,
            path=path,
            material_axis=layout.material_axis,
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
        builder.finalize(tabletop)

        band = ClothUnrollScene(
            scene=scene,
            manifest=tabletop.manifest,
            cameras=tabletop.cameras,
            frames=tabletop.frames,
            layout=layout,
            cloth=cloth,
            control_vertices=vertices,
            grid=(cols, rows),
            table_friction=self._install_table_friction(scene, cloth, layout),
        )
        print(
            f"cloth_unroll scene particles={len(band_particles(band))} "
            f"{remesh_report(vertices, band_particles(band))} "
            f"{edge_report(vertices, cols, rows)} "
            f"{layout.summary()}",
            flush=True,
        )
        return band

    def _add_dispenser(self, scene, manifest: EntityManifest, layout) -> None:
        """Two posts and the bar between them, all fixed.

        The bar is the task's anchor: it is what makes the pull unroll the band
        instead of towing it, and what holds the innermost turn up. The posts do
        one job beyond holding the bar -- they stop the roll sliding off along the
        bar's axis, which a band with a free inner end can otherwise do.

        Plain cylinders rather than the flared `routing_post_mesh`: that shape
        exists because a post meeting the table at a right angle ejected rope
        being dragged against it, and nothing here is dragged along the posts.
        """

        cfg = self.task_cfg.dispenser
        centre = layout.bar_centre()
        across, along = layout.bar_axis, layout.material_axis
        half = 0.5 * float(cfg.span)

        for side in (-1.0, 1.0):
            pos = np.zeros(3, dtype=float)
            pos[across] = centre[across] + side * half
            pos[along] = centre[along]
            pos[2] = layout.table_z + 0.5 * float(cfg.post_height)
            post = scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(float(v) for v in pos),
                    radius=float(cfg.post_radius),
                    height=float(cfg.post_height),
                    fixed=True,
                    collision=True,
                ),
                surface=materials.plastic("fixture", list(cfg.color), vis_mode="visual"),
                name=f"{cfg.name}_post_{'lo' if side < 0 else 'hi'}",
            )
            manifest.add(f"{cfg.name}_post_{'lo' if side < 0 else 'hi'}", post)

        # `gs.morphs.Cylinder` stands on z; the bar has to lie along the posts'
        # axis, so it is rolled a quarter turn about whichever axis leaves it
        # pointing that way -- `(90,0,0)` sends the axis to world y and
        # `(0,90,0)` to world x. Same construction as `stacked_plate.py:389`.
        euler = (0.0, 90.0, 0.0) if across == 0 else (90.0, 0.0, 0.0)
        bar_pos = np.zeros(3, dtype=float)
        bar_pos[across] = centre[across]
        bar_pos[along] = centre[along]
        bar_pos[2] = layout.bar_height()
        bar = scene.add_entity(
            gs.morphs.Cylinder(
                pos=tuple(float(v) for v in bar_pos),
                radius=float(cfg.bar_radius),
                height=float(cfg.span),
                euler=euler,
                fixed=True,
                collision=True,
            ),
            surface=materials.plastic("fixture", list(cfg.bar_color), vis_mode="visual"),
            name=f"{cfg.name}_bar",
        )
        manifest.add(f"{cfg.name}_bar", bar)

    def _cloth_surface(self, cloth_cfg):
        """The band's surface, with a woven diffuse image when one is asked for.

        Same reasoning as `cloth_fold` and `cloth_unpleat`: the rasterizer keeps a
        surface's diffuse colour and texture and drops everything else. ``size_m``
        comes from `texture_size_m` so the stripes stay across the material and
        the roll's turns read as separate layers on camera.
        """

        texture_cfg = getattr(cloth_cfg, "texture", None)
        image = None
        if texture_cfg is not None and bool(texture_cfg.enabled):
            image = textures.fabric_weave(
                color=list(cloth_cfg.color),
                size_m=texture_size_m(
                    float(cloth_cfg.material_length), float(cloth_cfg.width)
                ),
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
            print(
                "cloth_unroll texture "
                f"{materials.texture_reaches_renderer(surface)} "
                f"thread_pitch_mm={float(texture_cfg.thread_pitch) * 1e3:.1f}",
                flush=True,
            )
        return surface

    def _install_table_friction(self, scene, cloth, layout: ClothUnrollLayout):
        """Cloth against the table: friction, and here also the normal constraint.

        The tangential half matters less than in `cloth_unpleat` -- the bar is
        the anchor, not the table -- but the paid-out band still has to stay
        where it is put rather than sliding back.

        There is no normal half. The band DOES sink into the table -- Genesis'
        PBD contact is not a barrier -- and the one thing this module could do
        about it was measured on 2026-08-24 to leave the penetration unchanged
        while making the band billow. See `TabletopParticleFriction`'s docstring.

        Two other routes were ruled out the same day. Raising the PBD solver's
        `lower_bound` to the table would not clamp a sinking particle, it would
        PARK it at the domain corner (100, 100, 100) and drag its triangles
        across the scene -- see `supervision/pbd_probe.py`. And a rigid riser
        that lifts the cloth clear of the visible table hides the dip rather
        than fixing it, at the cost of a floating band.
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

"""Cloth Unpleat (docx 1.2「展开单个褶皱」): a band with one standing pleat, spread flat.

The scene is a cloth band on the standard tabletop and nothing else. Its middle
carries an unpressed knife pleat -- the band doubles back and up to a crest, then
comes back down and continues -- so a strip of it stacks three layers deep while
the rest lies flat. The gripper pinches the crest and takes the stored material
back out.

**Where the crest can go is decided by the material, not chosen.** The crest is
joined to the lower crease by a fixed length of cloth, so it travels on a circle
about that crease -- the same constraint `cloth_fold` derives its arc from, and
for the same reason. docx 1.2 describes the motion as 「一次水平拖拽」; that is
the intent, and the circle is what the intent works out to once the crest starts
30 mm above the table. A straight line between the crest's start and its flat
target cuts 34 mm inside that circle, which leaves the cloth slack and shoves it
rather than unfolding it.

Three things the task then reads, all from docx 1.2: the height comes down to one
cloth thickness, the covered area goes back to a single layer, and the spread
length comes back to the material's full length. The last two are what separate
unfolding from the shortcut docx names -- pressing the pleat flat also passes the
height test.

Judging lives in `topogym/verification/cloth_unpleat_verifier.py`; the arc lives
in `topogym/planning/cloth_unpleat_planner.py`; the pleat's control mesh lives in
`cloth_profile_mesh.py`. This file only says what the scene contains and where
its landmarks are.
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
    pleat_landmarks,
    pleat_profile,
    resample_polyline,
    sweep_profile_mesh,
)


@dataclass
class ClothUnpleatLayout:
    """Where the band is and where the pleat's landmarks are, in world metres."""

    task_cfg: Any
    origin: np.ndarray
    #: The profile's corners, cached because every landmark is read off them.
    _corners: np.ndarray | None = field(default=None, init=False, repr=False)
    #: The crest as measured after settling. See `observe`.
    _crest: np.ndarray | None = field(default=None, init=False, repr=False)

    def coordinate_frame(self) -> str:
        return str(self.task_cfg.coordinate_frame)

    @property
    def table_z(self) -> float:
        return float(self.origin[2])

    def world_z(self, z: float) -> float:
        return float(self.origin[2]) + float(z)

    def band_centre(self) -> np.ndarray:
        """World (x, y) of the band's plan-view middle."""

        return np.asarray(self.origin, dtype=float)[:2] + np.asarray(
            list(self.task_cfg.cloth.center), dtype=float
        )

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    def corners(self) -> np.ndarray:
        if self._corners is None:
            cloth = self.task_cfg.cloth
            self._corners = pleat_profile(
                material_length=float(cloth.material_length),
                pleat_width=float(cloth.pleat.width),
                crest_height=float(cloth.pleat.crest_height),
                rest_z=float(cloth.z),
            )
        return self._corners

    def landmarks(self) -> dict:
        return pleat_landmarks(self.corners())

    def material_length(self) -> float:
        return float(self.task_cfg.cloth.material_length)

    def design_crest_point(self) -> np.ndarray:
        """Where the mesh was authored to put the crest. Nominal, not observed."""

        marks = self.landmarks()
        centre = self.band_centre()
        return np.array(
            [centre[0] + marks["crest_x"], centre[1], self.world_z(marks["crest_z"])]
        )

    def crest_point(self) -> np.ndarray:
        """World point on the pleat's top edge the gripper attaches to.

        The observed crest once `observe` has been called, the design crest
        before that. **The difference is not a rounding error.** The pleat is
        authored into the mesh and then let go, so it sags before anything
        touches it -- measured 2026-08-22, by more than the 12 mm attachment
        window, which is how this method came to exist. Reaching for the design
        position after a settle is reaching into empty air.
        """

        return self._crest if self._crest is not None else self.design_crest_point()

    def observe(self, nodes) -> np.ndarray:
        """Find the settled crest in ``nodes`` and use it from here on.

        The highest particle near the design crest, on the band's centre line.
        Searched within the pleat's own plan width, because a crest that has
        moved further than that is not a crest any more -- and the caller is
        expected to check `crest_kept` rather than trust whatever this returns.

        The returned point keeps the band's centre line for y, so the gripper
        still sits mid-width rather than wherever the tallest particle happens to
        be across the weave.
        """

        nodes = np.asarray(nodes, dtype=float)
        design = self.design_crest_point()
        window = float(self.task_cfg.cloth.pleat.width)
        band = float(self.task_cfg.grasp.attach_radius)
        near = np.flatnonzero(
            (np.abs(nodes[:, 0] - design[0]) <= window)
            & (np.abs(nodes[:, 1] - design[1]) <= band)
        )
        if near.size == 0:
            raise ValueError(
                f"no material within {window:.3f} m of the design crest at "
                f"({design[0]:+.4f},{design[1]:+.4f}); the band is not where the "
                f"layout says it is."
            )
        top = near[int(np.argmax(nodes[near, 2]))]
        self._crest = np.array([nodes[top, 0], design[1], nodes[top, 2]])
        return self._crest

    def crest_height(self) -> float:
        """Current crest height above the band's rest plane."""

        return float(self.crest_point()[2] - self.rest_z())

    def crest_kept(self) -> float:
        """Observed crest height over the authored one. 1.0 means it did not sag.

        The number the caller gates on: an episode that starts from a collapsed
        pleat is not a hard episode, it is a different task.
        """

        design = float(self.design_crest_point()[2] - self.rest_z())
        return self.crest_height() / max(design, 1e-9)

    def crease_point(self) -> np.ndarray:
        """World point the crest pivots about: where the band doubles back.

        Treated as fixed the way `cloth_fold` treats its fold line -- the flat run
        leading up to it is held down by table friction. How well that holds is a
        measured question, and `band_shift` in the judge is the reading for it.
        """

        marks = self.landmarks()
        centre = self.band_centre()
        return np.array([centre[0] + marks["crease_x"], centre[1], self.rest_z()])

    def arm_length(self) -> float:
        """Cloth between the crease and the crest, measured along the material."""

        return float(self.landmarks()["arm_length"])

    def arc_radius(self) -> float:
        """Radius the hand follows. Slightly inside taut, as in `cloth_fold`."""

        return self.arm_length() * float(self.task_cfg.physical.arc_slack)

    def start_angle(self) -> float:
        """Where the crest starts, radians from +x about the crease.

        Taken from the crest's actual position rather than from the profile, so a
        crest that sagged during the settle is swept from where it IS. The two
        agree exactly before `observe` is called.
        """

        crest, crease = self.crest_point(), self.crease_point()
        return float(np.arctan2(crest[2] - crease[2], crest[0] - crease[0]))

    def start_radius(self) -> float:
        """How far the crest currently is from the crease, straight-line.

        Less than `arc_radius` whenever the pleat has sagged: the arm is still the
        same length of cloth, it has just stopped being straight. Driving the taut
        radius from step one would yank that slack out in a single step, so the
        planner opens the radius out over the sweep instead.
        """

        crest, crease = self.crest_point(), self.crease_point()
        return float(np.hypot(crest[0] - crease[0], crest[2] - crease[2]))

    def arc_length(self) -> float:
        """Path length of the sweep, using the mean radius it is driven at."""

        return float(
            0.5 * (self.start_radius() + self.arc_radius()) * abs(self.start_angle())
        )

    def drag_steps(self) -> int:
        """Steps for the sweep, from the calibrated hand SPEED.

        A fixed step count would become a different speed the moment the pleat
        changes size, and the speed is the calibrated quantity (`cloth_fold`'s
        120/180/240 sweep, 3.6 mm a step).
        """

        return max(
            4, int(round(self.arc_length() / float(self.task_cfg.physical.drag_step_m)))
        )

    def grasp_yaw(self) -> float:
        """Fingers across the crest, i.e. facing the direction the crest travels.

        The crest opens toward +x, so this is 0 -- written as arithmetic rather
        than as a constant so a mirrored layout stays correct.
        """

        return 0.0 if self.start_angle() > 0.0 else float(np.pi)

    def summary(self) -> str:
        marks = self.landmarks()
        crest, crease = self.crest_point(), self.crease_point()
        return (
            f"crest=({crest[0]:+.3f},{crest[1]:+.3f},{crest[2]:+.3f}) "
            f"crest_kept={self.crest_kept():.3f} "
            f"start_radius_mm={self.start_radius() * 1e3:.1f} "
            f"crease=({crease[0]:+.3f},{crease[1]:+.3f}) "
            f"material_mm={marks['material_length'] * 1e3:.0f} "
            f"plan_span_mm={marks['plan_span'] * 1e3:.1f} "
            f"stored_mm={marks['stored'] * 1e3:.1f} "
            f"spread_ratio_now={marks['plan_span'] / marks['material_length']:.3f} "
            f"radius_mm={self.arc_radius() * 1e3:.1f} "
            f"start_deg={np.degrees(self.start_angle()):.1f} "
            f"arc_mm={self.arc_length() * 1e3:.1f} "
            f"steps={self.drag_steps()} "
            f"step_mm={self.arc_length() / self.drag_steps() * 1e3:.2f}"
        )


@dataclass
class ClothUnpleatScene:
    scene: Any
    manifest: EntityManifest
    cameras: dict[str, Any]
    frames: Any
    layout: ClothUnpleatLayout
    cloth: Any
    control_vertices: np.ndarray
    #: Control-grid shape, for the neighbour arithmetic the stretch report needs.
    grid: tuple[int, int]
    table_friction: Any = None
    #: The settled band, which every judge measures against. Filled in by
    #: `settle_band` -- it cannot be read at build time, because the band spawns
    #: a particle radius above the table and the pleat has to relax first.
    rest_nodes: np.ndarray | None = field(default=None)


def band_particles(band: ClothUnpleatScene) -> np.ndarray:
    """Current ``(P, 3)`` particle positions of the band."""

    return probe_particles(band.cloth)


def settle_band(band: ClothUnpleatScene, steps: int) -> np.ndarray:
    """Let the band land and the pleat relax, then record it as the rest state.

    More load-bearing here than in `cloth_fold`: the pleat is BUILT rather than
    made by folding, so whether it stands at all is a question the settle answers.
    A pleat that flattens itself, or springs open, invalidates the whole task
    before any arm moves -- which is why `tests/pleat_settle_spike.py` exists and
    runs first.
    """

    for _ in range(max(0, int(steps))):
        band.scene.step()
    band.rest_nodes = band_particles(band)
    return band.rest_nodes


class ClothUnpleatSceneBuilder:
    """Standard tabletop, one pleated PBD cloth band."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg

    def build(
        self, *, show_viewer: bool = False, include_robot: bool = True
    ) -> ClothUnpleatScene:
        cloth_cfg = self.task_cfg.cloth
        builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            # The band's collision thickness and the layer judge's resolution are
            # the same number, so it has to reach gs.Scene before anything is
            # added.
            pbd_options=gs.options.PBDOptions(
                particle_size=float(cloth_cfg.particle_size)
            ),
        )
        tabletop = builder.create(show_viewer=show_viewer, include_robot=include_robot)
        scene = tabletop.scene
        layout = ClothUnpleatLayout(
            self.task_cfg, np.asarray(tabletop.frames.task_origin, dtype=float)
        )

        spacing = float(cloth_cfg.mesh.spacing)
        samples = resample_polyline(layout.corners(), spacing)
        path = Path(str(cloth_cfg.mesh.output_dir)) / "cloth_unpleat_band.obj"
        vertices, _faces, cols, rows = sweep_profile_mesh(
            samples,
            width=float(cloth_cfg.width),
            spacing=spacing,
            centre=layout.band_centre(),
            table_z=layout.table_z,
            path=path,
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
                # Cloth-against-cloth, which is what the pleat's three layers rest
                # on each other with. The table is a separate matter -- see
                # `_install_table_friction`.
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

        band = ClothUnpleatScene(
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
            f"cloth_unpleat scene particles={len(band_particles(band))} "
            f"{remesh_report(vertices, band_particles(band))} "
            f"{edge_report(vertices, cols, rows)} "
            f"{layout.summary()}",
            flush=True,
        )
        return band

    def _cloth_surface(self, cloth_cfg):
        """The band's surface, with a woven diffuse image when one is asked for.

        Same reasoning as `cloth_fold`: the rasterizer keeps a surface's diffuse
        colour and texture and drops everything else, and the raytracer that
        would honour the rest needs a LuisaRender build this install does not
        have. ``size_m`` is passed width-first so the texture's stripe pitch is
        measured along the MATERIAL, which is the axis the mesh puts on v.
        """

        texture_cfg = getattr(cloth_cfg, "texture", None)
        image = None
        if texture_cfg is not None and bool(texture_cfg.enabled):
            image = textures.fabric_weave(
                color=list(cloth_cfg.color),
                size_m=[float(cloth_cfg.width), float(cloth_cfg.material_length)],
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
                "cloth_unpleat texture "
                f"{materials.texture_reaches_renderer(surface)} "
                f"thread_pitch_mm={float(texture_cfg.thread_pitch) * 1e3:.1f}",
                flush=True,
            )
        return surface

    def _install_table_friction(self, scene, cloth, layout: ClothUnpleatLayout):
        """Sustained cloth-against-table friction, which Genesis does not provide.

        Load-bearing for this task in particular: the whole motion runs along the
        table, and without friction pulling the crest tows the entire band. A
        towed band and an unfolded one read the same on spread length, so the
        friction is what makes that judge mean anything.
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

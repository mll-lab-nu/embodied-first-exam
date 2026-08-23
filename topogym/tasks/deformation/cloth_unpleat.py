"""Cloth Unpleat (docx 1.2「展开单个褶皱」): a band with one standing pleat, spread flat.

The scene is a cloth band on the standard tabletop and nothing else. Its middle
carries an unpressed knife pleat -- the band doubles back and up to a crest, then
comes back down and continues -- so a strip of it stacks three layers deep while
the rest lies flat. The gripper pinches the crest and takes the stored material
back out.

**The gripper pulls the band's free END sideways, not the pleat itself.** The
tension runs down the flat tail into the fold, and table friction on the far half
is what holds the anchor while the fold feeds its material out. docx 1.2 has the
gripper pinch the crest; this task does not, because the pleat lies flat here (no
material parameter in Genesis 1.2.1 makes cloth hold a crease -- see the config)
and there is no standing edge to pinch.

The distance is arithmetic, not a tuned number: if the far half stays put, the end
travels exactly the difference between the band's material length and its plan
span, and that difference IS the pleat.

**This makes "the whole band slid" the task's primary failure**, where pinching
the crest had the lower crease as a pivot. `band_shift` is the reading that
separates a band that was unfolded from one that was towed, and it is why the
judge records it alongside the two gates.

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
    texture_size_m,
)


@dataclass
class ClothUnpleatLayout:
    """Where the band is and where the pleat's landmarks are, in world metres."""

    task_cfg: Any
    origin: np.ndarray
    #: The profile's corners, cached because every landmark is read off them.
    _corners: np.ndarray | None = field(default=None, init=False, repr=False)
    #: The grasp point as measured after settling. See `observe`.
    _grasp: np.ndarray | None = field(default=None, init=False, repr=False)

    def coordinate_frame(self) -> str:
        return str(self.task_cfg.coordinate_frame)

    @property
    def material_axis(self) -> int:
        """World axis the band's length runs along: 0 for x, 1 for y.

        The band runs along y as shipped. Reason: `front` looks down the world x
        axis, so a crease running along x is seen END ON, and a fold seen end on
        shows its cross-section -- the crest's height and the three layers under
        it are directly readable. With the band along x the same camera faces the
        flat side of the pleat and its depth has to be inferred from shading.

        The cloth is rotated, not the texture: the stripes are bound to the
        material by the mesh's UVs, so they turn with the band and keep the same
        relationship to the crease.
        """

        axis = str(self.task_cfg.cloth.material_axis).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        return 0 if axis == "x" else 1

    @property
    def sweep_axis(self) -> int:
        """The horizontal axis the band's WIDTH runs along."""

        return 1 - self.material_axis

    def _plan_point(self, material: float, height: float) -> np.ndarray:
        """A world point from a (material, height) pair on the band's own axes."""

        centre = self.band_centre()
        point = np.zeros(3, dtype=float)
        point[self.material_axis] = centre[self.material_axis] + float(material)
        point[self.sweep_axis] = centre[self.sweep_axis]
        point[2] = self.world_z(height)
        return point

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

    def design_grasp_point(self) -> np.ndarray:
        """Where the mesh puts the gripper's target: the band's free end.

        **The gripper pulls the END, not the pleat.** The pull is transmitted
        through the flat tail into the fold, and the far half of the band is held
        down by table friction while the fold feeds material out -- which makes
        "the whole band slid instead" the task's primary failure, and
        `band_shift` the reading that catches it.

        The tail end rather than the lead-in end: the pleat opens by the tail
        moving AWAY from the crease, and the lead-in run is longer (99 mm against
        75 mm) and carries the pleat's three layers on top of it, so it is the
        end with more friction holding it down. Pulling the other one would drag
        the anchor.

        Inset from the very edge by `grasp.edge_inset` so the whole attachment
        disc lands on cloth; centred on the band's width so the pull has no
        moment about the band's own axis.
        """

        marks = self.landmarks()
        end = 0.5 * marks["plan_span"] - float(self.task_cfg.grasp.edge_inset)
        return self._plan_point(end, float(self.task_cfg.cloth.z))

    def grasp_point(self) -> np.ndarray:
        """The end the gripper attaches to: observed once settled, design before."""

        return self._grasp if self._grasp is not None else self.design_grasp_point()

    def observe(self, nodes) -> np.ndarray:
        """Find the band's actual free end in ``nodes`` and use it from here on.

        The band does not move during the settle once the bending constraint is
        off (measured 2026-08-23: plan span stationary from step 25), so this
        normally agrees with the design point. It is measured anyway because
        agreeing is a fact to check, not one to assume -- and because reaching for
        a design position that the cloth has left is how the first version of this
        demo failed.

        Taken as the extreme material along the band's axis, then pulled back in
        by `edge_inset`, on the width's centre line.
        """

        nodes = np.asarray(nodes, dtype=float)
        design = self.design_grasp_point()
        material, sweep = self.material_axis, self.sweep_axis
        band = float(self.task_cfg.grasp.attach_radius)
        near = np.flatnonzero(np.abs(nodes[:, sweep] - design[sweep]) <= band)
        if near.size == 0:
            raise ValueError(
                f"no material within {band:.3f} m of the band's centre line at "
                f"{design[sweep]:+.4f}; the band is not where the layout says."
            )
        edge = float(nodes[near, material].max())
        point = design.copy()
        point[material] = edge - float(self.task_cfg.grasp.edge_inset)
        point[2] = float(nodes[near, 2].max())
        self._grasp = point
        return self._grasp

    def pull_direction(self) -> np.ndarray:
        """Unit vector the hand pulls along: outward from the pleat, in plane."""

        direction = np.zeros(3, dtype=float)
        direction[self.material_axis] = 1.0
        return direction

    def pull_distance(self) -> float:
        """How far the end has to travel: exactly the material the pleat stores.

        Not a tuned number. If the far half stays put, the end moves by the
        difference between the band's material length and its plan span, and that
        difference IS the pleat. `pull_scale` is the only slack, for the fact that
        friction lets the anchor creep a little.
        """

        return float(self.landmarks()["stored"]) * float(
            self.task_cfg.physical.pull_scale
        )

    def pull_steps(self) -> int:
        """Steps for the pull, from a commanded SPEED rather than a step count.

        A fixed count would become a different speed the moment the pleat changes
        size. The speed itself is no longer inherited from `cloth_fold`'s 3.6 mm a
        step: that value was set by a tradeoff against the cloth creeping across
        the table while the hand worked, and with `bending_relaxation` at zero the
        band does not creep at all (measured 2026-08-23, plan span flat over 200
        steps). Slower is now free, and a slower pull is both gentler on the
        contact and legible in a video.
        """

        return max(
            4, int(round(self.pull_distance() / float(self.task_cfg.physical.pull_step_m)))
        )

    def attach_z_band(self) -> float | None:
        """Height window for the attachment, or None for a planar disc.

        ``None`` here, and that is a consequence of pulling the END rather than
        the crest: the end is a single layer lying on the table, so there is no
        layer under it to grab by mistake. The window existed to keep the hand off
        the flat run passing beneath the crest, and there is no crest in the grasp
        any more.
        """

        value = self.task_cfg.grasp.attach_z_band
        return None if value is None else float(value)

    def grasp_yaw(self) -> float | None:
        """Which way the wrist faces, radians about world Z, or None to leave it.

        A knob rather than a derivation, because which setting the ARM can
        actually hold is a measured question here. `cloth_fold` faces the tool
        along the direction of travel for two reasons that agreed there -- it is
        how a hand pinches, and it keeps the last joint out of a large swing --
        but this task pulls at table height where the arm has much less room, and
        2026-08-23 a pull commanded 64 mm delivered 33 mm while holding the
        commanded orientation to 0.8 degrees. Holding an orientation the arm can
        barely reach and paying for it in position is exactly what `continuous_ik`
        does silently, so the setting has to be testable without editing code.

        ``across``      tool faces along the pull. Fingers lie across the band,
                        which is how a hand takes a hem.
        ``along``       turned a quarter turn from that.
        ``arm_default`` leaves the arm's own orientation alone -- the cheapest
                        pose for the wrist, and the one to fall back to if the
                        other two cannot be held.
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
        target = grasp + self.pull_direction() * self.pull_distance()
        return (
            f"axis={'xy'[self.material_axis]} "
            f"grasp=({grasp[0]:+.3f},{grasp[1]:+.3f},{grasp[2]:+.3f}) "
            f"target=({target[0]:+.3f},{target[1]:+.3f}) "
            f"material_mm={marks['material_length'] * 1e3:.0f} "
            f"plan_span_mm={marks['plan_span'] * 1e3:.1f} "
            f"stored_mm={marks['stored'] * 1e3:.1f} "
            f"spread_ratio_now={marks['plan_span'] / marks['material_length']:.3f} "
            f"pull_mm={self.pull_distance() * 1e3:.1f} "
            f"steps={self.pull_steps()} "
            f"step_mm={self.pull_distance() / self.pull_steps() * 1e3:.2f}"
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
        have. ``size_m`` comes from `texture_size_m` rather than being written out
        here, because its order has to match the mesh's UV layout exactly -- see
        that function.
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

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

Variation (2026-09-05): the task yaml's ``variation:`` block draws the pleat's
width (three tiers) and crest height, the band's across-axis position, the pull
scale, which end of the axis the free end lies at (`cloth.pull_side`, the mirror
layout), and two unit fractions that `derive_task_cfg` maps onto the windows the
drawn pleat leaves for `grasp.edge_inset` (the attachment disc must clear the
three-layer strip) and for the band's along-axis position (the pull's end point
must stay inside the arm's reach disc and the workspace box). The feasibility
rows live in `_cloth_unpleat_geometry.py` (numpy only, so the offline gate reads
the same rows without Genesis).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import genesis as gs
import numpy as np

from topogym.core import EntityManifest
from topogym.supervision.pbd_probe import probe_particles
from topogym.world import StandardTabletopSceneBuilder, materials, textures
from topogym.world.rope import TabletopParticleFriction

from ._cloth_unpleat_geometry import (
    across_leaf,
    along_leaf,
    band_length,
    band_profile,
    band_sign,
    center_across_from_frac,
    center_along_from_frac,
    cloth_unpleat_checks,
    edge_inset_from_frac,
    gap_from_frac,
    grasp_point_task,
    lead_from_frac,
    pleat_count,
    pleat_layout,
    pleat_marks,
    pull_direction as pull_direction_task,
    pull_distance_max,
    pulls,
    second_crest_from_frac,
    second_width_from_frac,
    tail_from_frac,
)
from ._cloth_cross_geometry import cross_dimensions, fold_flat_nodes
from .cloth_fold import remesh_report
from .cloth_profile_mesh import (
    edge_report,
    resample_polyline,
    sweep_profile_mesh,
    texture_size_m,
)


@dataclass
class ClothUnpleatLayout:
    """Where the band is and where the pleat's landmarks are, in world metres."""

    task_cfg: Any
    #: World position of the task frame's origin. Zero when the layout is built
    #: from the task config alone (offline gate, corner harness): every
    #: feasibility row is task-frame arithmetic and never needs it.
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    #: The profile's corners, cached because every landmark is read off them.
    _corners: np.ndarray | None = field(default=None, init=False, repr=False)
    #: The grasp point as measured after settling. See `observe`.
    #: Observed grasp per pull index, filled in by `observe`.
    _grasp: dict = field(default_factory=dict, init=False, repr=False)

    continuous_grasp = True
    is_cross = False

    def pull_axis(self, index=0):
        return self.material_axis

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

    @property
    def band_sign(self) -> float:
        """+1 for the band as built, -1 with the whole band mirrored on its axis.

        `cloth.band_flip: -1` reflects profile AND placement together, so the end
        that was the tail lies at the negative end of the material axis and every
        pull runs the other way. It is layout variety, not a task axis -- the
        2026-09-08 review took "which end to pull" out of the task -- and the two
        signs read identically on every feasibility row.
        """

        return band_sign(self.task_cfg)

    @property
    def pull_count(self) -> int:
        """How many separate grasp-and-drag actions this layout takes: 1 or 2."""

        return len(pulls(self.task_cfg))

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

        cloth = self.task_cfg.cloth
        return np.asarray(self.origin, dtype=float)[:2] + np.array(
            [float(cloth.center_x), float(cloth.center_y)], dtype=float
        )

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    def corners(self) -> np.ndarray:
        """The band's profile: every crease square to the band.

        The mirror layout reflects the material coordinate. Material ORDER is
        kept (index 0 is still the lead-in end), so the mesh's column order and
        every reading that walks it are unchanged.
        """

        if self._corners is None:
            corners = band_profile(self.task_cfg)
            corners[:, 0] *= self.band_sign
            self._corners = corners
        return self._corners


    def landmarks(self) -> dict:
        """Per-pleat and whole-band lengths, read off the unmirrored profile."""

        return pleat_marks(self.task_cfg)

    def material_length(self) -> float:
        """The band's material length -- COMPUTED from the runs and the pleats.

        Not read off the leaf. The leaf exists because the judge divides by it,
        and `validate` asserts the two agree; deriving it here is what makes the
        band's size follow the pleats instead of the other way round.
        """

        return band_length(self.task_cfg)

    def pull_end_sign(self, index: int = 0) -> float:
        """Which end of the material axis pull ``index`` takes, in world terms."""

        return self.band_sign * float(pulls(self.task_cfg)[int(index)]["end"])

    def design_grasp_point(self, index: int = 0) -> np.ndarray:
        """Where the mesh puts pull ``index``'s target: one bare band END.

        **The gripper pulls the END, not the pleat.** The pull is transmitted
        through the flat run into the fold, and the rest of the band is held down
        by table friction while the fold feeds material out -- which makes "the
        whole band slid instead" the task's primary failure, and `band_shift` the
        reading that catches it.

        With ONE pleat the tail end rather than the lead-in end: the pleat opens
        by the tail moving away from the crease, and the lead-in run is longer and
        carries the pleat's three layers on top of it, so it is the end with more
        friction holding it down. Pulling the other one drags the anchor
        (measured 2026-09-05).

        With TWO pleats both ends are taken, one pull each, and neither is the
        "wrong" one: whichever end is moving, the anchor is the whole of the rest
        of the band including the other pleat's stack. The tail goes first,
        because at that point the anchor still carries both stacks.

        Inset from the very edge by `grasp.edge_inset` so the whole attachment
        disc lands on cloth; centred on the band's width so the pull has no
        moment about the band's own axis.
        """

        xy = grasp_point_task(self.task_cfg, int(index))
        point = np.zeros(3, dtype=float)
        point[:2] = np.asarray(self.origin, dtype=float)[:2] + xy
        point[2] = self.rest_z()
        return point

    def grasp_point(self, index: int = 0) -> np.ndarray:
        """The end pull ``index`` attaches to: observed once settled, design before."""

        found = self._grasp.get(int(index))
        return found if found is not None else self.design_grasp_point(index)

    def observe(self, nodes, index: int = 0) -> np.ndarray:
        """Find the band's actual free end in ``nodes`` and use it from here on.

        The band does not move during the settle once the bending constraint is
        off (measured 2026-08-23: plan span stationary from step 25), so this
        normally agrees with the design point. It is measured anyway because
        agreeing is a fact to check, not one to assume -- and because reaching for
        a design position that the cloth has left is how the first version of this
        demo failed.

        Taken as the extreme material along the band's axis on this pull's end
        (`pull_end_sign`), then pulled back in by `edge_inset`, on the width's
        centre line. Re-measured before EVERY pull: with two pleats the first
        pull moves the band, so the second one's end is not where it spawned.
        """

        nodes = np.asarray(nodes, dtype=float)
        index = int(index)
        design = self.design_grasp_point(index)
        material = self.pull_axis(index)
        sweep = 1 - material
        band = float(self.task_cfg.grasp.attach_radius)
        near = np.flatnonzero(np.abs(nodes[:, sweep] - design[sweep]) <= band)
        if near.size == 0:
            raise ValueError(
                f"no material within {band:.3f} m of the band's centre line at "
                f"{design[sweep]:+.4f}; the band is not where the layout says."
            )
        sign = self.pull_end_sign(index)
        along = nodes[near, material]
        edge = float(along.max() if sign > 0 else along.min())
        point = design.copy()
        point[material] = edge - sign * float(self.task_cfg.grasp.edge_inset)
        # Height of the material AT the grasp, not the highest particle anywhere
        # on the centre line. The strip `near` runs the whole band, so its max
        # z is the settled pleat's top (table + 9.5 mm measured 2026-08-23),
        # while the end lies one layer thick at table + 2 mm; the pads were
        # being sent 7.5 mm high, most of `touch_clearance`. Same defect
        # `cloth_unroll.observe` fixed 2026-08-24.
        at = near[np.abs(along - point[material]) <= band]
        point[2] = float(nodes[at, 2].max()) if at.size else self.rest_z()
        self._grasp[index] = point
        return point

    def pull_direction(self, index: int = 0) -> np.ndarray:
        """Unit vector pull ``index`` runs along: the band's own axis, in plane."""

        direction = np.zeros(3, dtype=float)
        direction[:2] = pull_direction_task(self.task_cfg, int(index))
        return direction

    def pull_distance(self, index: int = 0) -> float:
        """How far this end has to travel: the material ITS pleat stores.

        Not a tuned number. If the rest of the band stays put, the end moves by
        the difference the fold takes out of the plan span, and that difference IS
        the pleat. With two pleats each pull answers for its own one, which is why
        neither pull needs a longer stroke than a single-pleat layout does.
        `pull_scale` is the only slack, for the fact that friction lets the anchor
        creep a little.
        """

        return float(pulls(self.task_cfg)[int(index)]["stored"]) * float(
            self.task_cfg.physical.pull_scale
        )

    def pull_steps(self, index: int = 0) -> int:
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
            4,
            int(round(self.pull_distance(index) / float(self.task_cfg.physical.pull_step_m))),
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

    def grasp_yaw(self, index: int = 0) -> float | None:
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
        direction = self.pull_direction(index)
        yaw = float(np.arctan2(direction[1], direction[0]))
        if mode == "across":
            return yaw
        if mode == "along":
            return yaw + 0.5 * float(np.pi)
        raise ValueError(
            f"grasp.finger_axis must be 'across', 'along' or 'arm_default', "
            f"got {mode!r}."
        )

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres; task frame.
        """

        return cloth_unpleat_checks(self.task_cfg)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        # The leaf is what the judge divides by; the runs and the pleats are what
        # the mesh is built from. A hand-edited fixed layout can put the two out
        # of step, and the symptom would be a recovered fraction that is quietly
        # wrong rather than a build that fails.
        leaf = float(self.task_cfg.cloth.material_length)
        computed = band_length(self.task_cfg)
        if abs(leaf - computed) > 1e-6:
            raise ValueError(
                f"cloth_unpleat: cloth.material_length is {leaf:.6f} but the flat "
                f"runs and pleats add up to {computed:.6f}; the judge divides by "
                f"the leaf, so they have to agree."
            )
        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"cloth_unpleat layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )

    def summary(self) -> str:
        marks = self.landmarks()
        pulls_txt = " ".join(
            (
                f"pull{index}=({self.grasp_point(index)[0]:+.3f},"
                f"{self.grasp_point(index)[1]:+.3f})"
                f"->({(self.grasp_point(index) + self.pull_direction(index) * self.pull_distance(index))[0]:+.3f},"
                f"{(self.grasp_point(index) + self.pull_direction(index) * self.pull_distance(index))[1]:+.3f})"
                f"/{self.pull_distance(index) * 1e3:.1f}mm"
            )
            for index in range(self.pull_count)
        )
        sizes = ",".join(
            f"{p['width'] * 1e3:.0f}x{p['height'] * 1e3:.0f}" for p in marks["pleats"]
        )
        return (
            f"axis={'xy'[self.material_axis]} flip={self.band_sign:+.0f} "
            f"layout={pleat_layout(self.task_cfg)} pleats={marks['count']}({sizes}) {pulls_txt} "
            f"material_mm={marks['material_length'] * 1e3:.1f} "
            f"plan_span_mm={marks['plan_span'] * 1e3:.1f} "
            f"runs_mm={','.join(f'{r * 1e3:.1f}' for r in marks['runs'])} "
            f"stored_mm={marks['stored'] * 1e3:.1f} "
            f"spread_ratio_now={marks['plan_span'] / marks['material_length']:.3f} "
            f"steps={','.join(str(self.pull_steps(i)) for i in range(self.pull_count))}"
        )


class ClothCrossLayout(ClothUnpleatLayout):
    """A true orthogonal stack with material-edge or material-corner grasps."""

    is_cross = True
    material_nodes = None

    @property
    def continuous_grasp(self):
        return str(self.task_cfg.cloth.cross.get("grasp", "edges")) == "corner"

    @property
    def pull_count(self):
        return 2

    def pull_axis(self, index=0):
        return self.sweep_axis if index == 0 else self.material_axis

    def pull_end_sign(self, index=0):
        return float(self.task_cfg.cloth.cross.flip) if index == 0 else self.band_sign

    def pull_direction(self, index=0):
        direction = np.zeros(3)
        direction[self.pull_axis(index)] = self.pull_end_sign(index)
        return direction

    def material_length(self):
        return cross_dimensions(self.task_cfg)[0][0]

    def corners(self):
        # The solver MUST build rest lengths on this flat mesh. The authored
        # fold is applied to actual remeshed particles only after scene.build.
        return np.array([[-self.material_length() / 2, float(self.task_cfg.cloth.z)],
                         [self.material_length() / 2, float(self.task_cfg.cloth.z)]])

    def landmarks(self):
        dims = cross_dimensions(self.task_cfg)
        pleats = []
        for key, (length, span) in zip(("first", "second"), dims):
            fold = self.task_cfg.cloth.cross[key]
            pleats.append(dict(width=float(fold.depth), height=4 * float(fold.radius),
                               stored=length - span))
        return dict(count=2, pleats=pleats, material_length=dims[0][0],
                    plan_span=dims[0][1], stored=dims[0][0] - dims[0][1],
                    width=dims[1][0], width_span=dims[1][1], runs=[])

    def pull_distance(self, index=0):
        length, span = cross_dimensions(self.task_cfg)[1 - index]
        return (length - span) * float(self.task_cfg.physical.pull_scale)

    def design_grasp_point(self, index=0):
        point = np.r_[self.band_centre(), self.rest_z()]
        dims = cross_dimensions(self.task_cfg)
        axis = self.pull_axis(index)
        if self.continuous_grasp:
            for i in range(2):
                point[self.pull_axis(i)] += self.pull_end_sign(i) * (dims[1-i][1] / 2 - float(self.task_cfg.grasp.edge_inset))
            return point
        point[axis] += self.pull_end_sign(index) * (dims[1 - index][1] / 2 - float(self.task_cfg.grasp.edge_inset))
        if index == 0:
            # Bare lead panel of the first fold, clear of its multilayer strip.
            first = self.task_cfg.cloth.cross.first
            strip_low = float(first.lead - first.depth - first.radius) - dims[0][1] / 2
            offset = min(0.0, strip_low - float(self.task_cfg.grasp.attach_radius)
                         - 2 * float(self.task_cfg.cloth.particle_size))
            point[self.material_axis] += self.band_sign * offset
        else:
            # The across end has already moved. Use the middle of the restored
            # footprint for the next grasp, not the old folded centre line.
            point[self.sweep_axis] += self.pull_end_sign(0) * (dims[1][0] - dims[1][1]) / 2
        return point

    def observe(self, nodes, index=0):
        if not self.continuous_grasp:
            return super().observe(nodes, index)
        return self.observe_corner(nodes, (1, 1), index=index)

    def observe_corner(self, nodes, ends, *, index=0):
        if self.material_nodes is None:
            raise ValueError("corner grasp requires the remeshed material reference")
        reference = self.material_nodes
        xy = self.band_centre().copy()
        dims = cross_dimensions(self.task_cfg)
        for i in range(2):
            xy[self.pull_axis(i)] += ends[i] * self.pull_end_sign(i) * (dims[1-i][0] / 2 - float(self.task_cfg.grasp.edge_inset))
        ids = np.linalg.norm(reference[:, :2] - xy, axis=1) < 2 * float(self.task_cfg.cloth.particle_size)
        if not ids.any():
            raise ValueError("no particles at cross free material corner")
        point = np.median(np.asarray(nodes)[ids], axis=0)
        self._grasp[int(index)] = point
        return point

    def checks(self):
        """Five rows; the arithmetic is in `_cloth_cross_geometry.cross_checks`.

        It lives there, on the plain config, for the same reason the band's
        seven rows live in `_cloth_unpleat_geometry`: the offline gate and the
        corner harness have to read them without importing Genesis.
        """

        from ._cloth_cross_geometry import cross_checks

        return cross_checks(self.task_cfg)

    def validate(self):
        from ._cloth_cross_geometry import rounded_pleat
        if str(self.task_cfg.cloth.cross.get("grasp", "edges")) not in ("edges", "corner"):
            raise ValueError("cross grasp must be edges or corner")
        if str(self.task_cfg.cloth.cross.get("corner_path", "sequential")) not in ("sequential", "diagonal"):
            raise ValueError("cross corner path must be sequential or diagonal")
        lift = float(self.task_cfg.cloth.cross.get("pull_lift", 0.0))
        if not 0 <= lift <= float(self.task_cfg.physical.approach_z):
            raise ValueError("cross peel height must lie below the approach height")
        if float(self.task_cfg.cloth.cross.flip) not in (-1, 1) or float(self.task_cfg.cloth.band_flip) not in (-1, 1):
            raise ValueError("cross material-axis flips must be +1 or -1")
        for key, (length, _) in zip(("first", "second"), cross_dimensions(self.task_cfg)):
            rounded_pleat(np.array([0.0, length]), self.task_cfg.cloth.cross[key])
        for leaf, (length, _) in zip(("material_length", "width"), cross_dimensions(self.task_cfg)):
            if abs(float(self.task_cfg.cloth[leaf]) - length) > 1e-6:
                raise ValueError(f"cross cloth.{leaf} must equal material arclength {length}")
        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(f"cross {name}: {measured:.4f} < {limit:.4f}")

    def summary(self):
        return (f"layout=cross fold_order={'xy'[self.material_axis]} then {'xy'[self.sweep_axis]} "
                f"unfold_order={'xy'[self.sweep_axis]} then {'xy'[self.material_axis]} "
                f"dimensions={cross_dimensions(self.task_cfg)} rest_metric=flat_sheet")


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
    material_nodes: np.ndarray | None = None


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
                particle_size=float(cloth_cfg.particle_size),
                max_stretch_solver_iterations=(int(cloth_cfg.cross.get("stretch_iterations", 4))
                                               if str(cloth_cfg.pleat.layout) == "cross" else 4),
            ),
        )
        tabletop = builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            # The arm is outside the soft-body coupler, as it is in every rope
            # task (`ring_transfer.py:215`, `closed_band_spike.py:318`). All
            # manipulation here goes through the kinematic bind, so finger
            # contact carries no signal -- and with the coupler on it carried
            # the OPPOSITE of signal: the pads pressed cloth through the table
            # and the bind froze it there.
            #
            # PBD's stable standoff is 5-9 mm (measured 2026-08-25) while a real
            # pinch on a 2 mm sheet needs the pads at the surface, so no clearance
            # exists that is both penetration-free and reachable on hardware.
            # Leaving the coupler on forces that choice; taking the arm out of it
            # removes the choice.
            #
            # The cost is that nothing stops the arm passing THROUGH the cloth:
            # trajectory correctness is now the script's job, not the solver's.
            robot_material=gs.materials.Rigid(needs_coup=False),
        )
        scene = tabletop.scene
        layout = layout_for(
            self.task_cfg, np.asarray(tabletop.frames.task_origin, dtype=float)
        )
        _assert_literal_copies(self.task_cfg)
        layout.validate()

        spacing = float(cloth_cfg.mesh.spacing)
        samples = resample_polyline(layout.corners(), spacing)
        # Genesis loads the exported file below; simultaneous builders must
        # never overwrite it with another episode's geometry in that interval.
        mesh_root = Path(str(cloth_cfg.mesh.output_dir))
        mesh_root.mkdir(parents=True, exist_ok=True)
        path = Path(mkdtemp(prefix="unpleat_", dir=mesh_root)) / "cloth_unpleat_band.obj"
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

        if isinstance(layout, ClothCrossLayout):
            flat = probe_particles(cloth)
            folded = fold_flat_nodes(flat, self.task_cfg, layout.origin)
            layout.material_nodes = flat
            cloth.set_particles_pos(folded)
            cloth.set_particles_vel(0.0)
            print("cloth_unpleat cross_initialized rest_metric=flat_sheet "
                  "fold_order=first_then_second", flush=True)

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
            material_nodes=flat if isinstance(layout, ClothCrossLayout) else None,
        )
        print(
            f"cloth_unpleat scene particles={len(band_particles(band))} "
            f"{remesh_report(vertices, flat if isinstance(layout, ClothCrossLayout) else band_particles(band))} "
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


def _assert_literal_copies(task_cfg) -> None:
    """The yaml's literal copy of the workspace box must still match `common`.

    `checks()` reads `workspace.x / y`, and the variation harness loads the task
    yaml alone, where `${common...}` cannot resolve -- so the task yaml carries
    literals, and the one place with both in hand asserts they agree.
    """

    root = task_cfg._get_root() if hasattr(task_cfg, "_get_root") else None
    common = getattr(root, "common", None) if root is not None else None
    if common is None:
        return
    ws = common.manipulation_space.workspace
    for axis in ("x", "y"):
        want = [float(v) for v in ws[axis]]
        got = [float(v) for v in task_cfg.workspace[axis]]
        if want != got:
            raise ValueError(
                f"cloth_unpleat: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
            )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. **Order is
    the dependency order**, and every step is a window rather than a redraw, so
    the envelope does not lean on rejection:

    1. the second pleat's own size -- independent, but its windows live in the
       yaml rather than the variation block;
    2. the band's ACROSS position, because how far out the band may sit depends
       on how much material the pleats hold: a band that gives it all back is
       longer, and the reach disc's chord shrinks as the band moves out;
    3. the run between the two pleats, then the two end runs, out of the
       band-length budget. **The band's material length falls out of those** and
       is written back, because the judge divides by it;
    4. the grasp inset, whose window is what the tail leaves;
    5. the band's ALONG position, whose window needs every pull's end point.

    A ``ValueError`` (empty window) rejects the draw.
    """

    cloth = task_cfg.cloth
    if str(cloth.pleat.layout) == "cross":
        from ._cloth_cross_geometry import derive_cross_cfg
        derive_cross_cfg(task_cfg)
        return
    if pleat_count(task_cfg) > 1:
        cloth.pleat.b.width = second_width_from_frac(task_cfg, float(cloth.pleat.b.width_frac))
        cloth.pleat.b.crest_height = second_crest_from_frac(task_cfg, float(cloth.pleat.b.crest_frac))
    across = across_leaf(task_cfg)
    cloth[across] = center_across_from_frac(task_cfg, float(cloth[f"{across}_frac"]))

    if pleat_count(task_cfg) > 1:
        cloth.pleat.gap = gap_from_frac(task_cfg, float(cloth.pleat.gap_frac))
    cloth.lead = lead_from_frac(task_cfg, float(cloth.lead_frac))
    cloth.tail = tail_from_frac(task_cfg, float(cloth.tail_frac))
    cloth.material_length = band_length(task_cfg)

    task_cfg.grasp.edge_inset = edge_inset_from_frac(task_cfg, float(task_cfg.grasp.edge_inset_frac))
    along = along_leaf(task_cfg)
    cloth[along] = center_along_from_frac(task_cfg, float(cloth[f"{along}_frac"]))


def layout_for(task_cfg, *args):
    """The Layout this task config's `cloth.pleat.layout` asks for, built.

    ``single`` and ``parallel`` are the same pleated band and share
    `ClothUnpleatLayout`; ``cross`` is a square sheet folded once each way and
    has its own. One place makes the choice, so the builder, the randomizer's
    validate hook and the corner harness cannot disagree about it. ``args`` is
    the task frame's world origin when the caller has one (the builder does; the
    offline gate and the corner harness do not, and every feasibility row is
    task-frame arithmetic anyway).
    """

    cls = ClothCrossLayout if str(task_cfg.cloth.pleat.layout) == "cross" else ClothUnpleatLayout
    return cls(task_cfg, *args)


def apply_layout_solver(cfg) -> bool:
    """Switch the solver to the drawn layout's preset. Call before building.

    Takes the WHOLE config (``cfg.env`` and ``cfg.task``), because half of the
    preset is the substep count, which lives under ``env``. A no-op for the
    band layouts, which keep the 4 mm / 4 substep baseline every threshold in
    `success:` was calibrated at.

    The cross needs 1 mm particles and 16 substeps or its nine-layer crossing
    comes apart during the settle, before the arm has moved -- measured, see the
    table under `cloth.cross.solver` in the task yaml. Which layout a seed draws
    is only known after `randomize_task_cfg`, and the sweep script cannot know
    it at all, so the switch has to happen here rather than in a config override.

    Idempotent. Returns True when it changed anything, so the caller can say so
    in the log.
    """

    if str(cfg.task.cloth.pleat.layout) != "cross":
        return False
    from ._cloth_cross_geometry import CROSS_PRESET_ID, apply_cross_solver

    apply_cross_solver(cfg.task)
    cfg.env.sim.substeps = int(cfg.task.cloth.cross.solver.substeps)
    cfg.env.preset.id = CROSS_PRESET_ID
    return True


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    layout_for(task_cfg).validate()

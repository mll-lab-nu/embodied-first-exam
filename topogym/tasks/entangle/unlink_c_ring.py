"""Unlink C Ring (docx 3.4): pull an open C-ring off a closed ring it is threaded on.

Scene: a post stands on the table and carries a closed rigid ring lying FLAT across
its top, bolted to the rim right above the post. A C-shaped open ring hangs on the
opposite rim, one ring diameter away, in a vertical plane, opening pointed sideways.

**The opening is the whole task.** The closed ring's body has to leave through it, and
`tests/check_c_ring_clearance.py` measures that every other way out is a rigid-body
dead end -- pulling, sliding along the bar, and lifting and carrying it aside all jam
by more than a millimetre. Turning the opening onto the bar and then leaving through
it works either way up, so there are two gateways; both are the task, and what the
anti-shortcut rules out is not turning at all. That gate runs without a solver and is
the reason the geometry in the config looks over-specified: five inequalities have to
hold at once, and the opening has only 2 mm of slack per side.

**Why the closed ring lies flat.** It sits on top of the post and the C hangs on the
opposite rim, one ring diameter away, so nothing the arm has to reach is underneath
anything. The layout it replaced stood the ring on edge at the end of a horizontal
cantilever; that arm ran directly over the grasp point, and the offline gate did not
catch it because the gate measures the C RING's envelope, not the hand's.

A flat ring also puts the extraction's rotation axis horizontal and pointing at the
robot. A gripper that comes in face-on to the C therefore rolls it about its own tool
axis -- one wrist joint -- rather than tipping the whole hand over.

**Both rings are chains of cylinders**, not meshes: `gs.morphs.Mesh(convexify=True)`
would fill a ring's hole in. `tasks/_fixtures.py` `add_rigid_assembly` welds a chain
into one body with one pose, which is what the moving C has to be. The chain geometry
and every derived length live in `./_c_ring_geometry.py`, which is Genesis-free so the
offline gate can import it on a machine with no solver.

STAGING (intentional, not an oversight): the scene, `verification/unlink_c_ring_verifier.py`,
`primitives/gateway_extract.py` and `demos/entangle/unlink_c_ring_physical_extract_demo.py`
are all in place, but there is no `generation/unlink_c_ring_generator.py` and so no
executable contrast PAIR -- `run.oracle_mode=no_align` is a contrast action, not a
contrast dataset. Per `docs/develop/framework/task_taxonomy_zh.md` Section 4.0 this
task therefore does NOT yet qualify for benchmark artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks.entangle import _c_ring_geometry as ring_geometry
from topogym.tasks._fixtures import HingeShape, add_rigid_assembly
from topogym.tasks._visuals import add_industrial_pedestal, box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir

STAND_PARTS = ("stand_post",)


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _euler_deg(direction) -> tuple[float, float, float]:
    """Genesis primitive ``euler`` that points a cylinder's axis along ``direction``.

    Genesis takes extrinsic x-y-z in degrees, which is the same composition URDF's
    ``rpy`` uses, so the one conversion in `_c_ring_geometry` serves both.
    """

    return tuple(float(np.rad2deg(v)) for v in ring_geometry.direction_to_rpy(direction))


@dataclass(frozen=True)
class UnlinkCRingLayout:
    """Stand, closed ring, and C ring geometry for Unlink C Ring."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        pos = np.asarray(_list(position), dtype=float)
        if pos.shape != (3,):
            raise ValueError(f"Position must have shape (3,), got {pos}.")
        if self.coordinate_frame == "world":
            return pos
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        raise ValueError(
            f"Unsupported UnlinkCRing coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        raise ValueError(
            f"Unsupported UnlinkCRing coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    # ----- derived geometry -------------------------------------------------

    def geometry(self) -> ring_geometry.SceneGeometry:
        """The one derivation of every length, shared with the offline gate.

        Rebuilt on each call rather than cached: the layout is frozen so config
        cannot change under it, and the build path asks for this a handful of times.
        """

        return ring_geometry.scene_geometry(OmegaConf.to_container(self.cfg, resolve=True))

    def validate(self) -> None:
        """Raise if any inequality the scene rests on is violated.

        The same rows `tests/check_c_ring_clearance.py` prints. Checking again at
        build time is what makes a config override safe: a scene that would spawn
        the C inside the arm, or the ring inside the robot's home pose, stops here
        rather than as a solver NaN several hundred steps later.
        """

        broken = [
            f"{name} is {value * 1000:+.2f} mm, needs more than {limit * 1000:+.2f} mm"
            for name, value, limit, ok in self.geometry().checks()
            if not ok
        ]
        if broken:
            raise ValueError(
                "Unlink C Ring layout is not physically consistent: " + "; ".join(broken)
            )

    def urdf_dir(self):
        return resolve_mesh_dir(
            str(getattr(self.cfg, "urdf_output_dir", ".cache/topogym/urdf/unlink_c_ring"))
        )


@dataclass
class UnlinkCRingScene:
    scene: Any
    manifest: EntityManifest
    layout: UnlinkCRingLayout
    geometry: ring_geometry.SceneGeometry
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def c_ring_entity(self):
        return self.manifest.get("c_ring")

    def c_ring_link_idx(self) -> int:
        """Global index of the C's only link -- where an external push has to land.

        `_c_ring_travel_probe` pushes the body itself rather than writing its pose,
        and `apply_links_external_force` addresses links, not entities.
        """

        return int(self.c_ring_entity().base_link.idx)

    def fixed_ring_entity(self):
        return self.manifest.get("fixed_ring")


class UnlinkCRingSceneBuilder:
    """Build the common table plus the stand, the closed ring, and the C ring."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> UnlinkCRingScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = UnlinkCRingLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        layout.validate()
        geometry = layout.geometry()

        self._add_stand(scene, manifest, layout, geometry)
        self._add_fixed_ring(scene, manifest, layout, geometry)
        self._add_c_ring(scene, manifest, layout, geometry)
        self._add_visual_details(scene, manifest, layout, geometry)

        tabletop_builder.finalize(tabletop)
        return UnlinkCRingScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            geometry=geometry,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    # ------------------------------------------------------------------ stand

    def _add_stand(self, scene, manifest, layout, geometry) -> None:
        """The post: one plain fixed cylinder, no URDF needed.

        There is no arm. An earlier layout carried the closed ring on a horizontal
        cantilever, and the arm ended up directly over the grasp point -- the
        clearance gate had cleared the C RING against it and the HAND was what
        collided. A ring lying flat on top of the post needs no arm at all.
        """

        stand = self.task_cfg.stand
        color = _list(stand.color)
        starts, ends, radii = geometry.stand_axes
        for name, start, end, radius in zip(STAND_PARTS, starts, ends, radii):
            axis = end - start
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(layout.position_to_world(0.5 * (start + end))),
                        euler=_euler_deg(axis),
                        radius=float(radius),
                        height=float(np.linalg.norm(axis)),
                        fixed=True,
                    ),
                    surface=materials.plastic("fixture", color),
                    name=name,
                ),
            )

    # ------------------------------------------------------------------ rings

    def _shapes(self, spec, frame, tab, color) -> list[HingeShape]:
        return [
            HingeShape(
                kind="cylinder",
                size=(segment.radius, segment.length),
                origin=segment.origin,
                rpy=segment.rpy,
                color=color,
            )
            for segment in ring_geometry.segment_specs(spec, frame, tab)
        ]

    def _add_fixed_ring(self, scene, manifest, layout, geometry) -> None:
        """The closed ring, pinned in space at the arm's end."""

        cfg = self.task_cfg.fixed_ring
        color = _list(cfg.color)
        add_rigid_assembly(
            scene,
            manifest,
            name="fixed_ring",
            urdf_path=layout.urdf_dir() / "fixed_ring.urdf",
            world_pos=layout.position_to_world(geometry.fixed_frame.center),
            shapes=self._shapes(geometry.fixed, geometry.fixed_frame, None, color),
            mass=float(cfg.mass),
            color=color,
            fixed=True,
        )

    def _add_c_ring(self, scene, manifest, layout, geometry) -> None:
        """The C, spawned a couple of millimetres above where it will hang.

        Resting on the bar is a zero-clearance pose by construction -- the hole's rim
        touches the bar -- and the chord approximation makes it very slightly
        negative. Spawning there is an initial interpenetration; spawning above it
        and letting the body fall is not, and the drop is short enough to settle in
        the same breath as the rest of the scene.
        """

        cfg = self.task_cfg.c_ring
        color = _list(cfg.color)
        add_rigid_assembly(
            scene,
            manifest,
            name="c_ring",
            urdf_path=layout.urdf_dir() / "c_ring.urdf",
            world_pos=layout.position_to_world(geometry.c_spawn_frame.center),
            shapes=self._shapes(
                geometry.c_ring, geometry.c_spawn_frame, geometry.tab, color
            ),
            mass=float(cfg.mass),
            color=color,
            fixed=False,
        )

    # -------------------------------------------------------- visual dressing

    def _add_visual_details(self, scene, manifest, layout, geometry) -> None:
        """Collision-free dressing for the post's base, independently switchable.

        Only the stand is dressed. The C moves, and a decorative part on a moving
        body would have to be synced every step or ride inside its collision link --
        neither is worth a cosmetic gain here (same call as `bar_through_hole`).
        """

        details = getattr(self.task_cfg, "visual_details", None)
        pedestal = getattr(details, "pedestal", None) if details is not None else None
        if pedestal is None or not box_entity_enabled(pedestal):
            return
        starts, _, radii = geometry.stand_axes
        post_base, post_radius = starts[0], float(radii[0])
        top_z = float(geometry.stand_axes[1][0][2])
        add_industrial_pedestal(
            scene,
            manifest,
            prefix="stand_post",
            spec=pedestal,
            center_x=float(post_base[0]),
            center_y=float(post_base[1]),
            top_z=top_z,
            block_size=(2.0 * post_radius, 2.0 * post_radius, top_z),
            to_world=layout.position_to_world,
        )

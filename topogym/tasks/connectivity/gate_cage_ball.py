"""Gate Cage Ball (docx 4.1): drop a gate into a chute and trap the rolling ball.

Scene: a straight walled channel lying along y, a ball that rolls into it from a
feed ramp outside, and a gate plate the robot slides down a pair of guide posts to
close the only opening. The robot never touches the ball -- the state change is on
the BALL's free space, not on any body the gripper holds.

**The two ends are deliberately different, and the task does not exist without
that.** Close both and the ball could never leave, so the gate changes no
topological state; open both and the ball rolls straight through and there is no
"inside". One closed end (a wall with a return ramp that sends the ball back under
gravity) plus one open end (the doorway, which the gate seals) is what turns "the
ball can leave" into "the ball cannot leave". It also makes inside and outside
readable from the geometry itself rather than from a label: the judge floods the
free space from the ball and asks whether it reaches the arena boundary, and the
doorway is the only route there.

The ball starts OUTSIDE, on the feed ramp, at rest -- gravity gives it its entry
speed, so no velocity is written at runtime. Starting outside is what makes "too
early" a real failure: seal the doorway before the ball is in and the ball is
locked out. Starting it inside would make "insert immediately" a winning script.

The ball is driven, not dropped: `_ball_drive.BallShuttle` holds its speed along
the lane and reverses it when something blocks the way. That is why there are no
ramps here. `tests/ball_roll_spike.py` measured rigid-vs-rigid restitution at
-0.001, so a ball has no way of its own to turn around -- gravity ramps were the
first answer and cost a slope shallow enough to be at the mercy of solver
stiction. Driving it instead makes every timing figure exact arithmetic and
reduces the whole family of tuning to one number, the speed.

The drive never overrules collision: only the along-lane velocity is written, so
a closed gate stops the ball and the shuttle reverses off it. That is what makes
success visible without reading a number -- a caged ball keeps shuttling inside
the box, an escaped one runs off the end of the rail.

Everything here is generated from config numbers -- opening width, channel length,
ramp rise and gate travel are difficulty and randomization knobs, so none of them
may be frozen into a mesh. Collision geometry is convex primitives; the industrial
scene carries no decoration at all -- see `_add_visual_details` for why both
attempts at it were withdrawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class GateCageBallLayout:
    """Channel, ramps, gate and ball geometry for Gate Cage Ball."""

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
            f"Unsupported GateCageBall coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        return float(self.task_origin[2]) + float(z)

    # ----- channel ----------------------------------------------------------

    @property
    def center_x(self) -> float:
        return float(self.cfg.channel.center_x)

    @property
    def inner_width(self) -> float:
        return float(self.cfg.channel.inner_width)

    @property
    def floor_top_z(self) -> float:
        return float(self.cfg.channel.floor_top_z)

    @property
    def door_y(self) -> float:
        """The plane the gate seals. Everything at larger y is 'inside'."""

        return float(self.cfg.channel.door_y)

    @property
    def flat_end_y(self) -> float:
        return float(self.cfg.channel.flat_end_y)

    def wall_inner_x(self) -> tuple[float, float]:
        half = 0.5 * self.inner_width
        return self.center_x - half, self.center_x + half

    def slot_y_extent(self) -> tuple[float, float]:
        """Outer faces of the near and far guide posts.

        The slot's four posts occupy this whole strip of y, so the side walls
        begin where it ends and the feed rails stop where it starts. Tiling them
        edge to edge rather than letting them overlap is the same rule
        `bar_through_hole._add_panel` follows: volumetric overlap renders as
        clipping, and there is no reason to accept it when the parts abut anyway.
        """

        slot = self.cfg.gate_slot
        reach = 0.5 * float(slot.guide_gap) + float(slot.post_thickness)
        return self.door_y - reach, self.door_y + reach

    # ----- ball -------------------------------------------------------------

    @property
    def ball_radius(self) -> float:
        return float(self.cfg.ball.radius)

    @property
    def entry_start_y(self) -> float:
        return float(self.cfg.channel.entry_start_y)

    @property
    def ball_speed(self) -> float:
        return float(self.cfg.ball.speed)

    def ball_release_center(self) -> np.ndarray:
        """Where the ball starts: on the flat, OUTSIDE the doorway.

        Outside is load-bearing. It is what makes sealing too early a failure
        rather than a free win; a ball starting inside would make "insert
        immediately" a winning script.
        """

        return self.position_to_world(
            (
                self.center_x,
                float(self.cfg.ball.release_y),
                self.floor_top_z + self.ball_radius,
            )
        )

    def turn_y(self) -> float:
        """Where the ball's centre reverses at the closed end."""

        return self.flat_end_y - self.ball_radius

    def predicted_window(self, *, dt: float = 0.01) -> float:
        """Seconds the ball spends inside, from crossing the doorway and back.

        Exact, not integrated: the drive holds the speed, so the round trip is a
        distance over a speed. The gate has to be committed and seated inside
        this, which is what `run.safety_margin` is checked against.
        """

        del dt  # the answer is continuous
        speed = self.ball_speed
        if speed <= 0.0:
            return 0.0
        return float(2.0 * (self.turn_y() - self.door_y) / speed)

    def entry_delay(self) -> float:
        """Seconds from the episode's start until the ball first crosses the doorway."""

        speed = self.ball_speed
        if speed <= 0.0:
            return float("inf")
        return float((self.door_y - float(self.cfg.ball.release_y)) / speed)

    def lane_bounds(self) -> tuple[float, float]:
        """Where the drive applies. Past these the ball is off the rail and free."""

        return self.entry_start_y - 2.0 * self.ball_radius, self.flat_end_y

    # ----- gate -------------------------------------------------------------

    def gate_seated_center(self) -> np.ndarray:
        """Gate centre when it is fully down in the slot."""

        gate = self.cfg.gate
        mid_z = 0.5 * (float(gate.seated_bottom_z) + float(gate.seated_top_z))
        return self.position_to_world((self.center_x, self.door_y, mid_z))

    def gate_parked_center(self) -> np.ndarray:
        rack = self.cfg.gate_rack
        gate = self.cfg.gate
        base_top = float(rack.base_size[2])
        height = float(gate.seated_top_z) - float(gate.seated_bottom_z)
        return self.position_to_world(
            (float(rack.center_x), float(rack.center_y), base_top + 0.5 * height)
        )

@dataclass
class GateCageBallScene:
    scene: Any
    manifest: EntityManifest
    layout: GateCageBallLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def ball_entity(self):
        return self.manifest.get("ball")

    def gate_entity(self):
        return self.manifest.get("gate")


class GateCageBallSceneBuilder:
    """Build the common table plus the chute, ramps, gate slot, gate and ball."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> GateCageBallScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = GateCageBallLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        self._add_channel(scene, manifest, layout)
        self._add_far_wall(scene, manifest, layout)
        self._add_gate_slot(scene, manifest, layout)
        self._add_gate_rack(scene, manifest, layout)
        self._add_gate(scene, manifest, layout)
        self._add_ball(scene, manifest, layout)
        self._add_visual_details(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        return GateCageBallScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    def _box(self, scene, manifest, name, center, size, color, *, role="fixture", euler=None):
        kwargs = {"pos": tuple(center), "size": tuple(float(v) for v in size), "fixed": True}
        if euler is not None:
            kwargs["euler"] = tuple(float(v) for v in euler)
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(**kwargs),
                surface=materials.plastic(role, _list(color)),
                name=name,
            ),
        )

    # ---------------------------------------------------------------- channel

    def _add_channel(self, scene, manifest, layout) -> None:
        """The floor slab and the side walls, in two segments per side.

        The walls run parallel to the ball's motion and are never struck head-on;
        the drive keeps the ball on the lane axis and only the far wall stops it.

        Two segments because the guide posts stand in the strip between them: the
        entry segment ends at the slot's near face and the box segment starts at
        its far face, so post and wall abut rather than sharing a volume. The floor
        runs the whole length underneath both, at inner width only -- at full outer
        width it would share a volume with the walls and the posts, all of which
        stand on the table.
        """

        channel = self.task_cfg.channel
        if not box_entity_enabled(channel):
            return
        color = _list(channel.color)
        floor_top = layout.floor_top_z
        thickness = float(channel.floor_thickness)
        wall_t = float(channel.wall_thickness)
        box_top = floor_top + float(channel.wall_height)
        # The entry run only has to keep the ball straight; the box has to keep it
        # in. Making the outside walls lower separates the two visually and keeps
        # them out of the front and wrist camera's line on the slot.
        entry_top = floor_top + float(
            getattr(channel, "entry_wall_height", channel.wall_height)
        )
        slot_near, slot_far = layout.slot_y_extent()
        y0, y1 = layout.entry_start_y, layout.flat_end_y

        self._box(
            scene,
            manifest,
            "channel_floor",
            layout.position_to_world(
                (layout.center_x, 0.5 * (y0 + y1), floor_top - 0.5 * thickness)
            ),
            (layout.inner_width, y1 - y0, thickness),
            _list(channel.floor_color),
            role="board",
        )

        inner_lo, inner_hi = layout.wall_inner_x()
        segments = (
            ("entry", y0, slot_near, entry_top),
            ("box", slot_far, y1, box_top),
        )
        for sign, side, inner in ((-1.0, "l", inner_lo), (1.0, "r", inner_hi)):
            for seg, seg_y0, seg_y1, seg_top in segments:
                self._box(
                    scene,
                    manifest,
                    f"channel_wall_{seg}_{side}",
                    layout.position_to_world(
                        (inner + sign * 0.5 * wall_t, 0.5 * (seg_y0 + seg_y1), 0.5 * seg_top)
                    ),
                    (wall_t, seg_y1 - seg_y0, seg_top),
                    color,
                )

    def _add_far_wall(self, scene, manifest, layout) -> None:
        """The closed end. A plain wall now: the drive reverses the ball, so this
        only has to stop it, and stopping is exactly what a zero-restitution
        contact does. The ramp that used to live here existed solely to turn the
        ball around under gravity.
        """

        wall = self.task_cfg.far_wall
        wall_t = float(wall.thickness)
        self._box(
            scene,
            manifest,
            "far_wall",
            layout.position_to_world(
                (layout.center_x, layout.flat_end_y + 0.5 * wall_t, 0.5 * float(wall.height))
            ),
            (
                layout.inner_width + 2.0 * float(self.task_cfg.channel.wall_thickness),
                wall_t,
                float(wall.height),
            ),
            _list(self.task_cfg.channel.color),
        )

    # -------------------------------------------------------------- gate slot

    def _guide_post_stations(self, layout) -> tuple[tuple[str, float, float], ...]:
        """(tag, x, y) for the four posts that box in the gate's descent."""

        slot = self.task_cfg.gate_slot
        half_gap = 0.5 * float(slot.guide_gap)
        half_post = 0.5 * float(slot.post_thickness)
        inner_lo, inner_hi = layout.wall_inner_x()
        # Straddling the channel's inner face puts each post over the side wall's
        # footprint, so the pair reads as a continuation of the wall rather than as
        # two rods standing in front of it.
        x_lo = inner_lo - 0.5 * float(slot.post_width)
        x_hi = inner_hi + 0.5 * float(slot.post_width)
        stations = []
        for x_tag, x in (("l", x_lo), ("r", x_hi)):
            for y_tag, y in (
                ("n", layout.door_y - half_gap - half_post),
                ("f", layout.door_y + half_gap + half_post),
            ):
                stations.append((f"{x_tag}{y_tag}", x, y))
        return tuple(stations)

    def _add_gate_slot(self, scene, manifest, layout) -> None:
        """Four straight posts: two columns, each a pair boxing the plate in y.

        No lead-in funnel at the top. What captures the plate is its own width --
        it is wider than the gap between the two columns, so both ends drop into a
        slot at once and the pair holds it from both sides. A funnel would be a
        second, redundant way to find the same alignment.

        The cost is that the slot clearance is now the whole insertion budget:
        3 mm per side, against a measured IK tracking error of 7.5 mm on the
        comparable move in bar_through_hole. That is survivable only by aiming the
        PLATE from its measured pose rather than the hand from a precomputed one,
        the same correction that task needed. `guide_gap` is the knob if it turns
        out to be too tight in the scene.
        """

        slot = self.task_cfg.gate_slot
        color = _list(slot.color)
        height = float(slot.post_height)
        for tag, x, y in self._guide_post_stations(layout):
            self._box(
                scene,
                manifest,
                f"gate_post_{tag}",
                layout.position_to_world((x, y, 0.5 * height)),
                (float(slot.post_width), float(slot.post_thickness), height),
                color,
            )

    def _add_gate_rack(self, scene, manifest, layout) -> None:
        """Where the gate stands before the episode.

        The smallest thing that holds a plate upright: a thin base and two low
        jaws in the same grey as everything else. It is not a pedestal -- nothing
        is being raised, the gate simply has to start somewhere the gripper can
        take it from without first re-orienting it (which would put an object
        rotation in the episode that no arm motion explains).
        """

        rack = self.task_cfg.gate_rack
        base = np.asarray(_list(rack.base_size), dtype=float)
        self._box(
            scene,
            manifest,
            "gate_rack_base",
            layout.position_to_world(
                (float(rack.center_x), float(rack.center_y), 0.5 * float(base[2]))
            ),
            base,
            _list(rack.color),
        )
        slot = self.task_cfg.gate_slot
        half_gap = 0.5 * float(slot.guide_gap)
        half_post = 0.5 * float(slot.post_thickness)
        height = float(base[2]) + float(getattr(rack, "jaw_height", 0.022))
        for tag, sign in (("n", -1.0), ("f", 1.0)):
            self._box(
                scene,
                manifest,
                f"gate_rack_jaw_{tag}",
                layout.position_to_world(
                    (
                        float(rack.center_x),
                        float(rack.center_y) + sign * (half_gap + half_post),
                        0.5 * height,
                    )
                ),
                (float(base[0]), float(slot.post_thickness), height),
                _list(rack.color),
            )

    # -------------------------------------------------------------- gate/ball

    def _add_gate(self, scene, manifest, layout) -> None:
        """The plate: ONE body, spawned parked in the rack.

        It carried a separate handle block until it was checked: two free rigid
        bodies with nothing joining them do not make a handled plate, they make a
        block resting on a plate, and the first lift would leave one of them
        behind. Genesis has no compound primitive and the convex hull of a T is a
        wedge, so a real handle would have to be a welded second entity -- more
        machinery than the grasp needs. The plate is 12 mm across the axis the
        fingers close on, which is a perfectly ordinary pinch, and the 1.1 kg is
        carried by the same assisted attachment bar_through_hole uses.
        """

        gate = self.task_cfg.gate
        height = float(gate.seated_top_z) - float(gate.seated_bottom_z)
        manifest.add(
            "gate",
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(layout.gate_parked_center()),
                    size=(float(gate.width), float(gate.thickness), height),
                    fixed=False,
                ),
                material=gs.materials.Rigid(
                    rho=float(getattr(gate, "rho", 7800.0)),
                    friction=float(getattr(gate, "friction", 0.8)),
                ),
                surface=materials.plastic("object", _list(gate.color)),
                name="gate",
            ),
        )

    def _add_ball(self, scene, manifest, layout) -> None:
        """The ball, at rest on the feed ramp OUTSIDE the arena.

        Outside is load-bearing: it is what makes sealing too early a failure
        rather than a free win. Its entry speed comes from the ramp height, so
        nothing has to write a velocity at run time -- the release point is the
        randomization axis and gravity does the rest.
        """

        ball = self.task_cfg.ball
        manifest.add(
            "ball",
            scene.add_entity(
                gs.morphs.Sphere(
                    pos=tuple(layout.ball_release_center()),
                    radius=float(ball.radius),
                    fixed=False,
                ),
                material=gs.materials.Rigid(
                    rho=float(ball.rho), friction=float(ball.friction)
                ),
                surface=materials.plastic("object", _list(ball.color)),
                name="ball",
            ),
        )

    # -------------------------------------------------------- visual dressing

    def _add_visual_details(self, scene, manifest, layout) -> None:
        """Nothing is drawn here, and that is the finding rather than an omission.

        Two dressing ideas were tried and both were wrong for this scene. The
        pedestal recipe from `_visuals.py` does not apply because nothing is held
        up. Banding on the gate does not work either: decoration is `fixed=True`
        and the gate is the one body that MOVES, so the stripes stayed at the rack
        the moment the arm lifted the plate. Anything marking a moving part would
        have to be re-synced every step, which is the class of thing that drifts
        out of agreement with the physics -- so the gate is told apart by colour
        instead, which costs nothing and cannot desynchronize.
        """

        return

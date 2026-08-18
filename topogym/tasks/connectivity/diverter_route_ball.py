"""Diverter Route Ball (docx 4.3): turn the flap, and the ball leaves by the exit you were told.

Scene: a straight feed lane along +x forks into two branches at +/- `branch.angle`,
and a flap on a vertical pivot at the splitter nose decides which branch the entry
connects to. The robot turns the flap by its lever and never touches the ball --
the state change is on the BALL's free space, as in `gate_cage_ball`.

**The flap is a guide vane, not a transverse gate, and the task does not work if
it is built as one.** Seated, the flap lies along one branch's inner boundary,
extended upstream to the opposite wall. Two things follow at once, from the same
piece of geometry: the other branch's mouth is unreachable from the entry (it is
on the far side of the flap), and a ball arriving down the centre is deflected by
the flap's face into exactly the branch axis -- the tangential component of a
zero-restitution contact with a face at `angle` to the lane is `v cos(angle)`
along that branch. A flap placed ACROSS a branch mouth instead seals it just as
well and fails the second half: the ball slides down the face into the sealed
mouth and wedges there.

Half-open (joint angle 0) points the flap straight upstream and splits the lane
down the middle. The ball meets its edge head-on and stops -- the intermediate
failure state docx 4.3 asks for, and it comes out of the same geometry rather
than being detected and staged.

**Horizontal, where the docx draws a vertical chute.** The ball is driven at
constant speed (`_ball_drive.HeadingDrive`) rather than dropped, which is the
choice `gate_cage_ball` already made and documented. Three things follow: the
xy flood-fill judge from 4.1 applies unchanged; a ball at rest on a flat lane
stays at rest, so nothing has to hold it while the arm works; and the step-wise
travel stays at ~1 mm instead of the ~17 mm a 0.15 m drop would give at dt=0.01.
The S-T connectivity the task is about is untouched by the change of plane. See
`docs/develop/tasks/diverter_route_ball_zh.md` section 2.

Sign conventions, fixed here and used by the planner and the verifier:

- ``side`` is ``"left"`` (-y) or ``"right"`` (+y). The front camera looks down -x
  with +z up, so its screen-right is +y: "right" on screen is "right" here.
- The flap's joint angle is 0 pointing straight upstream, positive counter-
  clockwise about +z. Seating it at ``+angle`` seals the LEFT branch, at
  ``-angle`` the RIGHT one -- the flap leans toward the branch it feeds.

Everything is generated from config numbers, and the fork geometry is derived
rather than tabulated: the nose position, the junction where the entry walls hand
over to the branch walls, and the flap's length all follow from the lane width and
the branch angle, so changing either keeps the scene consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._fixtures import HingeShape, add_hinge_mechanism, hinge_joint_dof
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir

SIDES = ("left", "right")


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def side_sign(side: str) -> float:
    """-1 for the left (-y) branch, +1 for the right (+y) one."""

    side = str(side)
    if side not in SIDES:
        raise ValueError(f"Unknown side {side!r}; expected one of {SIDES}.")
    return -1.0 if side == "left" else 1.0


def other_side(side: str) -> str:
    return "right" if str(side) == "left" else "left"


@dataclass(frozen=True)
class DiverterRouteBallLayout:
    """Lane, fork, flap and ball geometry for Diverter Route Ball."""

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
            f"Unsupported DiverterRouteBall coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        return float(self.task_origin[2]) + float(z)

    # ----- lane -------------------------------------------------------------

    @property
    def angle(self) -> float:
        return float(np.deg2rad(float(self.cfg.branch.angle_deg)))

    @property
    def half_width(self) -> float:
        return 0.5 * float(self.cfg.channel.inner_width)

    @property
    def wall_thickness(self) -> float:
        return float(self.cfg.channel.wall_thickness)

    @property
    def wall_height(self) -> float:
        return float(self.cfg.channel.wall_height)

    @property
    def floor_top_z(self) -> float:
        return float(self.cfg.channel.floor_top_z)

    @property
    def wall_top_z(self) -> float:
        return self.floor_top_z + self.wall_height

    @property
    def entry_start_x(self) -> float:
        return float(self.cfg.channel.entry_start_x)

    @property
    def fork_origin_x(self) -> float:
        """Where both branch centre lines are taken to start."""

        return float(self.cfg.channel.fork_origin_x)

    @property
    def exit_station(self) -> float:
        """Axial distance from the fork origin to a branch's exit plane."""

        return float(self.cfg.branch.exit_station)

    def branch_dir(self, side: str) -> np.ndarray:
        angle = self.angle
        return np.array([np.cos(angle), side_sign(side) * np.sin(angle)], dtype=float)

    def branch_inner_normal(self, side: str) -> np.ndarray:
        """Unit normal of a branch pointing at the splitter (toward the other one)."""

        angle = self.angle
        return np.array([np.sin(angle), -side_sign(side) * np.cos(angle)], dtype=float)

    def branch_yaw_deg(self, side: str) -> float:
        return float(side_sign(side) * float(self.cfg.branch.angle_deg))

    @property
    def nose_x(self) -> float:
        """Where the two branches' inner boundaries cross: the splitter tip.

        Both inner boundaries pass one half-width to the inside of their own
        centre line and converge at the lane axis; the crossing sits
        ``half_width / sin(angle)`` downstream of the fork origin. Upstream of it
        the fork is a single open chamber, which is what gives the ball room to
        be steered before the branches separate.
        """

        return self.fork_origin_x + self.half_width / np.sin(self.angle)

    def nose_xy(self) -> np.ndarray:
        return np.array([self.nose_x, 0.0], dtype=float)

    @property
    def junction_x(self) -> float:
        """Where the straight entry wall hands over to a branch's outer wall.

        The two meet exactly at this x, so the walls tile edge to edge instead of
        sharing a volume -- the same rule `gate_cage_ball.slot_y_extent` follows.
        """

        angle = self.angle
        return self.fork_origin_x + self.half_width * (np.cos(angle) - 1.0) / np.sin(angle)

    @property
    def outer_wall_station(self) -> float:
        """Axial position of a branch's outer wall start (at the junction)."""

        angle = self.angle
        return self.half_width * (1.0 - np.cos(angle)) / np.sin(angle)

    @property
    def inner_wall_station(self) -> float:
        """Axial position of a branch's inner wall start, set back from the nose.

        The setback leaves room for the flap's pivot end, which occupies the nose
        itself. It opens a notch a few millimetres deep between the flap and the
        wall; the ball is an order of magnitude wider than that.
        """

        angle = self.angle
        return self.half_width * np.cos(angle) / np.sin(angle) + float(
            self.cfg.diverter.nose_setback
        )

    def branch_point(self, side: str, station: float, offset: float = 0.0) -> np.ndarray:
        """Task-frame xy at ``station`` along a branch, ``offset`` toward the splitter."""

        origin = np.array([self.fork_origin_x, 0.0], dtype=float)
        return (
            origin
            + float(station) * self.branch_dir(side)
            + float(offset) * self.branch_inner_normal(side)
        )

    def exit_center(self, side: str) -> np.ndarray:
        return self.branch_point(side, self.exit_station)

    # ----- target pad -------------------------------------------------------

    @property
    def target_pad_cfg(self):
        return getattr(self.cfg, "target_pad", None)

    def target_pad_enabled(self) -> bool:
        pad = self.target_pad_cfg
        return pad is not None and bool(getattr(pad, "enabled", True))

    def target_pad_center(self, side: str) -> np.ndarray:
        """Centre of the landing pad, just outside a branch's exit mouth."""

        pad = self.target_pad_cfg
        station = (
            self.exit_station + float(pad.pad_offset) + 0.5 * float(pad.pad_length)
        )
        return self.branch_point(side, station)

    def target_pad_rect_world(self, side: str) -> tuple[float, float, float, float, float]:
        """(cx, cy, half_along, half_across, yaw) of the pad, in world xy.

        The braking region handed to the feeder. Oriented to the branch, because
        the ball arrives along it and a square in x/y would brake it early on one
        corner and late on the other.
        """

        pad = self.target_pad_cfg
        center = self.position_to_world((*self.target_pad_center(side), 0.0))
        return (
            float(center[0]),
            float(center[1]),
            0.5 * float(pad.pad_length),
            0.5 * float(pad.pad_width),
            float(np.deg2rad(self.branch_yaw_deg(side))),
        )

    def exit_patch_center(self, side: str) -> np.ndarray:
        """Centre of the region the judge tests, just inside the exit mouth.

        The target marker is drawn on exactly this, so what a viewer sees is what
        the flood fill asks about.
        """

        patch = float(self.cfg.success.exit_patch)
        return self.branch_point(side, self.exit_station - 0.5 * patch)

    @property
    def exit_plane_x(self) -> float:
        """x of both exit centres. Equal by construction -- the branches mirror.

        Used only by the judge's flood fill, as the plane it clips the fill at.
        It is NOT how "the ball left" is decided; see `exited_side` for why.
        """

        return self.fork_origin_x + self.exit_station * np.cos(self.angle)

    def branch_station(self, side: str, xy) -> tuple[float, float]:
        """A point resolved into one branch's own frame: (along, toward-splitter)."""

        rel = np.asarray(xy, dtype=float).reshape(2) - np.array(
            [self.fork_origin_x, 0.0], dtype=float
        )
        return (
            float(rel @ self.branch_dir(side)),
            float(rel @ self.branch_inner_normal(side)),
        )

    def exited_side(self, xy) -> str | None:
        """Which exit the ball has passed, by station ALONG the branch.

        Not a plane of constant x, which is what this used to be. The branches
        run at `angle` to x, so one x plane cuts them at a station that depends on
        how far off the centre line the ball is: measured 2026-08-19, a ball
        riding the inner wall crosses x = `exit_plane_x` a full 11 mm BEFORE the
        mouth, and one riding the outer wall 11 mm after -- 22 mm of spread on a
        90 mm channel, all of it invisible in the reading. Resolving into the
        branch's own frame removes the dependence entirely.

        The lateral guard is not redundant: it keeps a ball deep in one branch
        from being read as having left by the other. At the far end of the left
        branch the right branch's station reads only half as much, and its
        lateral offset is 173 mm against a 45 mm half width, so both guards
        exclude it independently.
        """

        for side in SIDES:
            station, across = self.branch_station(side, xy)
            if station >= self.exit_station and abs(across) <= self.half_width:
                return side
        return None

    # ----- flap -------------------------------------------------------------

    @property
    def flap_reach(self) -> float:
        """Nose-to-wall distance along a seated flap.

        The seated flap runs along one branch's inner boundary extended upstream;
        that line meets the opposite outer wall at ``half_width / (sin a cos a)``
        from the nose. Deriving it is what keeps the seal tight when the lane
        width or the branch angle changes.
        """

        angle = self.angle
        return self.half_width / (np.sin(angle) * np.cos(angle))

    @property
    def flap_length(self) -> float:
        """Slightly short of the wall, so the joint limit seats it, not a contact.

        A flap sized to touch would be held by wall contact fighting the joint
        limit every step. The gap it leaves instead is millimetres against a ball
        tens of millimetres across, so nothing gets through it.
        """

        return self.flap_reach - float(self.cfg.diverter.flap.wall_gap)

    @property
    def flap_bottom_z(self) -> float:
        return self.floor_top_z + float(self.cfg.diverter.flap.ground_clearance)

    @property
    def flap_height(self) -> float:
        return self.wall_top_z - self.flap_bottom_z

    def seat_angle(self, sealed_side: str) -> float:
        """Joint angle that seals ``sealed_side`` (and feeds the other one)."""

        return -side_sign(sealed_side) * self.angle

    def sealed_side_at(self, joint_angle: float) -> str | None:
        """Which branch a joint angle seals; ``None`` when it is short of a seat."""

        tolerance = float(np.deg2rad(float(self.cfg.success.seat_tolerance_deg)))
        angle = float(joint_angle)
        if abs(angle - self.seat_angle("left")) <= tolerance:
            return "left"
        if abs(angle - self.seat_angle("right")) <= tolerance:
            return "right"
        return None

    def open_side_at(self, joint_angle: float) -> str | None:
        sealed = self.sealed_side_at(joint_angle)
        return None if sealed is None else other_side(sealed)

    @property
    def commanded_side(self) -> str:
        """Which exit this episode asks for. Part of the instance, not the run mode."""

        side = str(self.cfg.command.side)
        if side not in SIDES:
            raise ValueError(f"command.side must be one of {SIDES}, got {side!r}.")
        return side

    def command_prompt(self, side: str | None = None) -> str:
        """The episode's language instruction, generated from the commanded side.

        Generated rather than hand-written per demo because it has to agree with
        `command.side` in every episode -- this is the repo's first task whose
        prompt varies per instance, and the H5 writer takes it as a per-episode
        argument already.
        """

        side = self.commanded_side if side is None else str(side)
        return f"Send the ball out the {side} exit."

    def target_angle(self, side: str) -> float:
        """Joint angle that routes the ball to ``side`` (by sealing the other)."""

        return self.seat_angle(other_side(side))

    @property
    def initial_sealed_side(self) -> str:
        side = str(self.cfg.diverter.init_sealed_side)
        if side not in SIDES:
            raise ValueError(f"diverter.init_sealed_side must be one of {SIDES}, got {side!r}.")
        return side

    def flap_tip_xy(self, joint_angle: float) -> np.ndarray:
        """Free end of the flap, for judging and for logging."""

        angle = float(joint_angle)
        direction = np.array([-np.cos(angle), -np.sin(angle)], dtype=float)
        return self.nose_xy() + self.flap_length * direction

    # ----- lever ------------------------------------------------------------

    @property
    def lever_radius(self) -> float:
        return float(self.cfg.diverter.lever.radius)

    @property
    def lever_arm_bottom_z(self) -> float:
        return self.wall_top_z + float(self.cfg.diverter.lever.arm_gap)

    @property
    def lever_arm_top_z(self) -> float:
        return self.lever_arm_bottom_z + float(self.cfg.diverter.lever.arm_height)

    @property
    def knob_top_z(self) -> float:
        return self.lever_arm_top_z + float(self.cfg.diverter.lever.knob_height)

    def knob_center_xy(self, joint_angle: float) -> np.ndarray:
        """Where the knob sits at a joint angle. The arm points downstream.

        Opposite the flap, so the knob rides over the empty wedge between the two
        branches rather than over a channel, and above the walls either way.
        """

        angle = float(joint_angle)
        direction = np.array([np.cos(angle), np.sin(angle)], dtype=float)
        return self.nose_xy() + self.lever_radius * direction

    def knob_grasp_world(self, joint_angle: float) -> np.ndarray:
        """World point the finger pads should close on."""

        xy = self.knob_center_xy(joint_angle)
        z = self.lever_arm_top_z + float(self.cfg.diverter.lever.grasp_height)
        return self.position_to_world((float(xy[0]), float(xy[1]), z))

    # ----- ball -------------------------------------------------------------

    @property
    def ball_radius(self) -> float:
        return float(self.cfg.ball.radius)

    @property
    def ball_speed(self) -> float:
        return float(self.cfg.ball.speed)

    def ball_release_center(self) -> np.ndarray:
        return self.position_to_world(
            (float(self.cfg.ball.release_x), 0.0, self.floor_top_z + self.ball_radius)
        )

    def drive_region_world(self) -> tuple[float, float, float, float]:
        """(x_lo, x_hi, y_lo, y_hi) in world xy over which the feeder drives.

        The layout's footprint: the feeder drives over it, and the ball coasts once
        it runs past the end. Taking a REGION rather than the old single x
        threshold is what lets the ball leave under power instead of being cut
        loose inside the channel -- measured 2026-08-19, handing over 11 mm short
        of the mouth left the ball still touching the branch wall, and it lost
        the remaining 0.103 m/s in 5.6 mm against a coast model that predicts
        59 mm. Past the wall ends there is nothing to rub against and the coast
        behaves as modelled.

        A rectangle rather than a distance from the fork, because the plate is a
        thing in the scene and the drive should stop where the tray stops.
        """

        x_lo, x_hi, y_half = self.footprint_bounds()
        lo = self.position_to_world((x_lo, -y_half, 0.0))
        hi = self.position_to_world((x_hi, y_half, 0.0))
        return float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1])

    def travel_time(self) -> float:
        """Seconds from release to the exit plane, along the shorter of the two.

        Exact rather than integrated, for the same reason as
        `gate_cage_ball.predicted_window`: the drive holds the speed, so the trip
        is a distance over a speed. It sizes the rollout budget.
        """

        speed = self.ball_speed
        if speed <= 0.0:
            return float("inf")
        lane = self.nose_x - float(self.cfg.ball.release_x)
        branch = self.exit_station - self.half_width * np.cos(self.angle) / np.sin(self.angle)
        return float((lane + branch) / speed)

    # ----- footprint --------------------------------------------------------

    def footprint_bounds(self) -> tuple[float, float, float]:
        """(x_min, x_max, y_half) of the layout, from its outermost parts.

        Generates nothing -- there is no base plate any more, the walls stand on
        the table. Two things still need the rectangle: where the feeder drives,
        and how far the judge's grid has to reach.
        """

        margin = float(self.cfg.footprint.margin)
        outer = self.half_width + self.wall_thickness
        y_half = self.exit_station * np.sin(self.angle) + outer * np.cos(self.angle) + margin
        return (
            self.entry_start_x - self.wall_thickness - margin,
            self.exit_plane_x + margin,
            float(y_half),
        )


@dataclass
class DiverterRouteBallScene:
    scene: Any
    manifest: EntityManifest
    layout: DiverterRouteBallLayout
    joint_name: str = "diverter_joint"
    joint_dof: int = 0
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def ball_entity(self):
        return self.manifest.get("ball")

    def diverter_entity(self):
        return self.manifest.get("diverter")

    def flap_angle(self) -> float:
        value = self.diverter_entity().get_dofs_position(dofs_idx_local=[int(self.joint_dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    def set_flap_angle(self, angle: float) -> None:
        """Write the joint directly. Episode reset and inspection only.

        Never during an episode: a flap that moved without the arm moving is a
        state change no action explains (`rigid_first_track_zh.md` section 3.1).
        """

        self.diverter_entity().set_dofs_position(
            [float(angle)], dofs_idx_local=[int(self.joint_dof)], zero_velocity=True
        )


class DiverterRouteBallSceneBuilder:
    """Build the common table plus the base plate, lane, fork, flap and ball."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> DiverterRouteBallScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = DiverterRouteBallLayout(
            self.task_cfg, task_origin=tabletop.frames.task_origin
        )
        self._add_entry(scene, manifest, layout)
        self._add_branches(scene, manifest, layout)
        entity, joint_name = self._add_diverter(scene, manifest, layout)
        self._add_ball(scene, manifest, layout)
        self._add_target_marker(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        joint_dof = hinge_joint_dof(entity, joint_name)
        ball_scene = DiverterRouteBallScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            joint_name=joint_name,
            joint_dof=joint_dof,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        ball_scene.set_flap_angle(layout.seat_angle(layout.initial_sealed_side))
        return ball_scene

    def _box(self, scene, manifest, name, center, size, color, *, role="fixture", yaw_deg=0.0):
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(float(v) for v in center),
                    size=tuple(float(v) for v in size),
                    euler=(0.0, 0.0, float(yaw_deg)),
                    fixed=True,
                ),
                surface=materials.plastic(role, _list(color)),
                name=name,
            ),
        )

    def _wall(self, scene, manifest, layout, name, center_xy, length, yaw_deg) -> None:
        """One wall segment standing on the plate, rotated about z."""

        height = layout.wall_height
        self._box(
            scene,
            manifest,
            name,
            layout.position_to_world(
                (float(center_xy[0]), float(center_xy[1]), layout.floor_top_z + 0.5 * height)
            ),
            (float(length), layout.wall_thickness, height),
            self.task_cfg.channel.color,
            yaw_deg=yaw_deg,
        )

    # ----------------------------------------------------------------- lane

    def _add_entry(self, scene, manifest, layout) -> None:
        """The straight feed lane: two side walls and a back stop behind the ball."""

        x0 = layout.entry_start_x
        x1 = layout.junction_x
        offset = layout.half_width + 0.5 * layout.wall_thickness
        for side in SIDES:
            self._wall(
                scene,
                manifest,
                layout,
                f"entry_wall_{side}",
                (0.5 * (x0 + x1), side_sign(side) * offset),
                x1 - x0,
                0.0,
            )
        # The inlet end. The ball is released just inside it and never comes back
        # this way, so it is there to read as an inlet rather than to stop anything.
        self._box(
            scene,
            manifest,
            "entry_back",
            layout.position_to_world(
                (
                    x0 - 0.5 * layout.wall_thickness,
                    0.0,
                    layout.floor_top_z + 0.5 * layout.wall_height,
                )
            ),
            (
                layout.wall_thickness,
                2.0 * (layout.half_width + layout.wall_thickness),
                layout.wall_height,
            ),
            self.task_cfg.channel.color,
        )

    def _add_branches(self, scene, manifest, layout) -> None:
        """Each branch's outer and inner wall, as rotated boxes.

        Nothing fills the wedge between the two branches: it is the space between
        two diverging chutes, which is empty on a real one too, and the inner
        walls already bound the ball on both sides.
        """

        offset = layout.half_width + 0.5 * layout.wall_thickness
        exit_station = layout.exit_station
        for side in SIDES:
            yaw = layout.branch_yaw_deg(side)
            for tag, station, sign in (
                ("outer", layout.outer_wall_station, -1.0),
                ("inner", layout.inner_wall_station, 1.0),
            ):
                length = exit_station - station
                if length <= 0.0:
                    raise ValueError(
                        f"branch.exit_station={exit_station} is shorter than the "
                        f"{tag} wall's start ({station:.4f}); lengthen the branch."
                    )
                center = layout.branch_point(
                    side, 0.5 * (station + exit_station), sign * offset
                )
                self._wall(
                    scene, manifest, layout, f"branch_{side}_{tag}", center, length, yaw
                )

    # -------------------------------------------------------------- diverter

    def _add_diverter(self, scene, manifest, layout) -> tuple[Any, str]:
        """The flap, its lever and the post joining them: one rotating link.

        One link, because they are one part -- the lever is how the flap is
        turned, and two free bodies with nothing joining them would come apart on
        the first push. The lever rides above the wall tops so the gripper never
        reaches into a channel, and the ball never meets anything but the flap.
        """

        diverter = self.task_cfg.diverter
        flap = diverter.flap
        lever = diverter.lever
        mech = diverter.mechanism

        length = layout.flap_length
        height = layout.flap_height
        arm_bottom = layout.lever_arm_bottom_z
        arm_height = float(lever.arm_height)
        knob_height = float(lever.knob_height)
        knob_size = float(lever.knob_size)
        post = float(lever.post_size)
        post_height = arm_bottom - layout.wall_top_z

        shapes = [
            HingeShape(
                kind="box",
                size=(length, float(flap.thickness), height),
                origin=(-0.5 * length, 0.0, layout.flap_bottom_z + 0.5 * height),
                color=_list(flap.color),
            ),
            HingeShape(
                kind="box",
                size=(post, post, post_height),
                origin=(0.0, 0.0, layout.wall_top_z + 0.5 * post_height),
                color=_list(lever.color),
            ),
            HingeShape(
                kind="box",
                size=(layout.lever_radius, float(lever.arm_thickness), arm_height),
                origin=(0.5 * layout.lever_radius, 0.0, arm_bottom + 0.5 * arm_height),
                color=_list(lever.color),
            ),
            HingeShape(
                kind="box",
                size=(knob_size, knob_size, knob_height),
                origin=(
                    layout.lever_radius,
                    0.0,
                    layout.lever_arm_top_z + 0.5 * knob_height,
                ),
                color=_list(lever.knob_color),
            ),
        ]

        asset_root = resolve_mesh_dir("runs/generated_meshes/diverter_route_ball")
        # A limit at the seats would make "turn until it stops" land the flap
        # perfectly every time, and getting the angle right is what this task is
        # for. Off by default; the flap is also short enough (see flap.wall_gap)
        # that the WALL is not a stop either.
        limited = bool(getattr(mech, "joint_limited", False))
        limit = float(layout.angle)
        return add_hinge_mechanism(
            scene,
            manifest,
            name="diverter",
            urdf_path=asset_root / "diverter.urdf",
            world_pos=layout.position_to_world((layout.nose_x, 0.0, 0.0)),
            axis=(0.0, 0.0, 1.0),
            shapes=shapes,
            mass=float(mech.mass),
            color=_list(flap.color),
            joint_name=str(mech.joint_name),
            limit_rad=(-limit, limit) if limited else None,
            damping=float(mech.joint_damping),
            friction=float(mech.joint_friction),
            armature=float(mech.joint_armature),
            contact_friction=float(mech.contact_friction),
        )

    # ------------------------------------------------------------------ ball

    # --------------------------------------------------------- target marker

    def _add_target_marker(self, scene, manifest, layout) -> None:
        """A red/white bullseye on the landing pad outside the commanded exit.

        Same construction as `routing/cable_routing._add_connector_target_marker`:
        concentric rectangles, `collision=False`, so it can never touch the ball
        or the gripper. Rotated to the branch so it reads as part of the chute.

        The pad is also where the feeder brakes (see
        `DiverterRouteBallLayout.target_pad_rect_world`), so the ball comes to
        rest on it. Only the commanded side gets one -- a ball that went the
        wrong way rolls on and stops wherever it stops, which is what makes the
        two outcomes tell themselves apart in a single frame.

        Drawn only where the ball can arrive by leaving through this exit, so
        "resting on the bullseye" and "left by the commanded exit" are the same
        event; the judge still decides at the mouth, upstream of here.
        """

        if not layout.target_pad_enabled():
            return
        pad = layout.target_pad_cfg
        side = layout.commanded_side
        center = layout.target_pad_center(side)
        along = float(pad.pad_length)
        across = float(pad.pad_width)
        rings = max(2, int(pad.ring_count))
        thickness = float(pad.thickness)
        red = _list(pad.red_color)
        white = _list(pad.white_color)
        base_z = layout.floor_top_z + float(pad.z_offset)
        for index in range(rings):
            shrink = index / float(rings)
            size_along = along * (1.0 - shrink)
            size_across = across * (1.0 - shrink)
            if size_along <= 0.0 or size_across <= 0.0:
                break
            name = f"target_{side}_{index:02d}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world(
                                (float(center[0]), float(center[1]),
                                 base_z + index * thickness)
                            )
                        ),
                        size=(size_along, size_across, thickness),
                        euler=(0.0, 0.0, layout.branch_yaw_deg(side)),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic(
                        "deformable", red if index % 2 == 0 else white
                    ),
                    name=name,
                ),
            )

    def _add_ball(self, scene, manifest, layout) -> None:
        """The ball, at rest on the feed lane. Nothing holds it: the lane is flat."""

        ball = self.task_cfg.ball
        manifest.add(
            "ball",
            scene.add_entity(
                gs.morphs.Sphere(
                    pos=tuple(layout.ball_release_center()),
                    radius=layout.ball_radius,
                    fixed=False,
                ),
                material=gs.materials.Rigid(
                    rho=float(ball.rho), friction=float(ball.friction)
                ),
                surface=materials.plastic("object", _list(ball.color)),
                name="ball",
            ),
        )

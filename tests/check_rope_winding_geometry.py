"""Offline gate for the rope_winding layout: geometry, oracle, and topology.

Runs the REAL planner and the REAL winding-number code against the REAL task
config with a stand-in layout, so a layout edit that breaks the task is caught
without a GPU run (a full winding episode is minutes of IPC solving).

What it proves:
  - the oracle's waypoints are the helix the config asks for (radius, climb,
    count) and stay below the post top -- the gateway semantics of task book 2.4;
  - the spawn route does NOT already encircle the post, so the episode starts at
    winding 0;
  - a finished rope reads exactly +turns, and the mirrored run exactly -turns
    (the task's contrast pair);
  - the cable can get from the plug to the post's shaft with room to bend;
  - the rope is long enough for the tightest moment of the route, with margin;
  - the wrist schedule tracks the orbit 1:1 through the forward stretch, hands
    all of that travel back over the points that remain so every turn closes,
    stays inside joint7's travel, and never asks one waypoint for half a turn;
  - the gripper-wrap metric reads one turn per orbit for a fixed wrist and zero
    for one that turns with the orbit -- the arithmetic behind the wrist spin
    that is meant to keep the rope off the gripper;
  - `RigidAttachment` really does hold the plug still relative to the gripper
    through the sharpest turn the route asks for, which the shipped code did not
    do until 2026-08-15.

    python tests/check_rope_winding_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): `topogym.planning` and
`topogym.supervision.rope_winding` are numpy-only, and the handful of `${}`
references this reads are resolved here by hand.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.planning.rope_winding_planner import (  # noqa: E402
    MAX_WRIST_STEP,
    SLACK_BAND,
    WRIST_BUDGET,
    WindingSpec,
    free_end_winding_delta,
    plan_rope_winding_route,
    post_center,
    spawn_winding,
    taut_demand,
)
from topogym.planning.waypoint import (  # noqa: E402
    arc_route_points,
    helix_route_points,
    lead_in_route_point,
    plug_spawn_point,
    tail_arc_route_points,
)
from topogym.primitives.attachment import (  # noqa: E402
    RigidAttachment,
    _quat_rotate as _rotate_by_quat,
)
from topogym.primitives.physical_contact import (  # noqa: E402
    quat_about_axis,
    quat_mul,
)
from topogym.primitives.pick_place import HAND_TO_PAD_Z  # noqa: E402
from topogym.supervision.rope_twist import TwistTracker  # noqa: E402
from topogym.supervision.rope_winding import (  # noqa: E402
    gripper_frame_metrics,
    winding_number,
    winding_sweep,
)

TASK_CFG = REPO / "configs" / "task_configs" / "rope_winding_topogym_tabletop_v1.yaml"
PREFABS = REPO / "configs" / "prefab_configs" / "topogym_prefabs_v1.yaml"
# Any task-frame origin works: every quantity checked here is a difference or a
# distance, and the winding number is translation invariant.
TASK_ORIGIN = np.array([0.55, 0.0, 0.92])

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class Node(dict):
    """Config node with both attribute and item access, as OmegaConf has."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def wrap(value):
    if isinstance(value, dict):
        return Node({key: wrap(item) for key, item in value.items()})
    if isinstance(value, list):
        return [wrap(item) for item in value]
    return value


class StandInLayout:
    """The layout surface the planner and the winding metrics actually use."""

    def __init__(self, cfg):
        self.cfg = cfg

    def position_to_world(self, pos):
        return np.asarray(pos, dtype=float) + TASK_ORIGIN

    def world_z(self, z):
        return float(TASK_ORIGIN[2]) + float(z)

    def fixture_pos(self, name, *, z=None):
        fixture = self.cfg.fixtures[str(name)]
        if "pos" in fixture:
            pos = np.asarray(fixture.pos, dtype=float).copy()
        else:  # scalar x / y / z keys (a fixture whose position is a variation axis)
            pos = np.array([fixture.x, fixture.y, fixture.z], dtype=float)
        if z is not None:
            pos[2] = float(z)
        return self.position_to_world(pos)

    def route_point(self, spec):
        if "plug_spawn_from" in spec:
            arc = self.cfg.rope.spawn_arc
            return plug_spawn_point(
                self.fixture_pos(str(spec.get("anchor", "S")), z=0.0),
                self.fixture_pos(str(spec["plug_spawn_from"]), z=0.0),
                float(arc.plug_distance),
                math.radians(float(arc.plug_bearing_deg)),
                math.radians(float(arc.anchor_lead_deg)),
                self.world_z(float(self.cfg.rope.z)),
            )
        if "pos" in spec:
            return self.position_to_world(spec["pos"])
        return self.fixture_pos(str(spec["fixture"]), z=float(self.cfg.rope.z))

    def route_polyline(self, name):
        # Mirrors `CableRoutingLayout.route_polyline`, arc entries included --
        # the spawn arc's length IS the rope's length, so a stand-in that could
        # not expand it would be checking a different rope than the sim builds.
        points = []
        for entry in self.cfg.routes[name]:
            if not isinstance(entry, str) and "arc_to" in entry:
                sweep_deg = entry.get("sweep_deg", None)
                if sweep_deg is None:
                    sweep_deg = self.cfg.rope.spawn_arc.sweep_deg
                points.extend(
                    arc_route_points(
                        points[-1],
                        self.route_point(entry["arc_to"]),
                        math.radians(float(sweep_deg)),
                        samples=entry.get("samples"),
                    )
                )
            elif not isinstance(entry, str) and "helix_around" in entry:
                winding = self.cfg.winding
                post = self.cfg.fixtures[str(entry["helix_around"])]
                radius = (
                    float(post.radius)
                    + float(self.cfg.rope.radius)
                    + float(entry.get("standoff", 0.002))
                )
                points.extend(
                    helix_route_points(
                        points[-1],
                        self.fixture_pos(str(entry["helix_around"]), z=0.0),
                        radius,
                        float(entry.get("turns", winding.start_turns)),
                        float(entry.get("climb", winding.climb_per_turn)),
                        1.0 if str(entry.get("direction", winding.direction)).lower() == "ccw" else -1.0,
                        z_start=self.world_z(float(entry.get("z_start", winding.wind_z_start))),
                    )
                )
            elif not isinstance(entry, str) and "lead_in_toward" in entry:
                points.append(
                    lead_in_route_point(
                        points[-1],
                        self.fixture_pos(str(entry["lead_in_toward"]), z=0.0),
                        float(entry["length"]),
                        self.world_z(float(self.cfg.rope.z)),
                    )
                )
            elif not isinstance(entry, str) and "tail_arc" in entry:
                points.extend(
                    tail_arc_route_points(
                        points[-1],
                        self.fixture_pos(str(entry["tail_arc"]), z=0.0),
                        1.0 if str(self.cfg.winding.direction).lower() == "ccw" else -1.0,
                        float(self.cfg.rope.spawn_arc.chord),
                        math.radians(float(self.cfg.rope.spawn_arc.sweep_deg)),
                        self.world_z(float(self.cfg.rope.z)),
                    )
                )
            else:
                points.append(self.route_point(entry))
        return np.stack(points, axis=0)


def _quat_axis_z(quat) -> np.ndarray:
    """Local +z of a (w, x, y, z) quaternion, in world axes."""

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)], dtype=float
    )


def densify(points, step=0.002):
    """Resample a polyline so azimuth steps stay far below pi.

    The real centerline is `success.centerline_bins` material bins along the
    rope, which is already this dense; a raw waypoint list is not, and unwrap
    would mis-read a long chord.
    """

    points = np.asarray(points, dtype=float)
    out = [points[0]]
    for start, end in zip(points[:-1], points[1:]):
        steps = max(1, int(np.linalg.norm(end - start) / step))
        out.extend(start + (end - start) * k / steps for k in range(1, steps + 1))
    return np.asarray(out)


def resolve(raw, prefabs, *, turns=None, sweep_deg=None):
    """Dereference the `${}` interpolations the checks below read, and pin the
    yaml's literal copies of prefab values to the prefabs."""

    if abs(float(raw["rope"]["radius"]) - float(prefabs["rope_pbd"]["radius"])) > 1e-12:
        raise SystemExit("rope.radius in the task yaml must equal prefabs.rope_pbd.radius (literal copy)")
    if abs(float(raw["fixtures"]["POST"]["base_height"]) - float(prefabs["rope_routing_post"]["base_height"])) > 1e-12:
        raise SystemExit("POST.base_height in the task yaml must equal prefabs.rope_routing_post.base_height")
    raw["rope"]["endpoint_handle"]["z_offset"] = raw["physical_handle"]["z_offset"]
    if turns is not None:
        raw["winding"]["turns"] = int(turns)
    if sweep_deg is not None:
        raw["rope"]["spawn_arc"]["sweep_deg"] = float(sweep_deg)
    return raw


def main(argv=None) -> int:
    raw = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    prefabs = yaml.safe_load(PREFABS.read_text(encoding="utf-8"))
    # `turns` and `sweep_deg` are the one pair a run has to get right together,
    # and both are set on the command line for anything but the default. Check
    # the pair here, in a second, rather than 40 minutes into a GPU run.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, help="override task.winding.turns")
    parser.add_argument(
        "--sweep-deg", type=float, help="override task.rope.spawn_arc.sweep_deg"
    )
    args = parser.parse_args(argv)
    raw = resolve(raw, prefabs, turns=args.turns, sweep_deg=args.sweep_deg)
    cfg = wrap(raw)

    layout = StandInLayout(cfg)
    spec = WindingSpec.from_config(cfg)
    center = post_center(layout, spec)
    post = cfg.fixtures[spec.post]
    settle_radius = float(post.radius) + float(cfg.rope.radius)
    # The winding count's band, tighter than the gateway's on purpose -- see
    # `settled_band_radius`.
    wrap_band = float(post.radius) + 2.0 * float(cfg.rope.radius)
    anchor = layout.route_point({"fixture": "S", "relation": "center"})
    seat = layout.route_point({"fixture": "C", "relation": "endpoint"})

    print(
        f"rope_winding: turns={spec.turns} direction={spec.direction} "
        f"target_winding={spec.target_winding:+.1f}"
    )

    print("\noracle")
    command, plan = plan_rope_winding_route(layout)
    labels = [waypoint.label for waypoint in plan.waypoints]
    points = np.array([waypoint.position for waypoint in plan.waypoints])
    expected = 2 + spec.turns * spec.arc_points_per_turn + 3
    check(
        "waypoint count = lift + entry + turns*points + exit + hover + insert",
        len(labels) == expected,
        f"{len(labels)} (expected {expected}); the wrist gives its travel back "
        f"over the last {spec.arc_points_per_turn - spec.yaw_forward_points} "
        "points of each turn rather than at a standstill, so there are no "
        "wrist-only waypoints",
    )
    orbit = [
        index for index, label in enumerate(labels) if label.startswith("wind_t")
    ]
    radii = np.linalg.norm(points[orbit][:, :2] - center[None, :2], axis=1)
    check(
        "orbit points sit on wind_radius",
        bool(np.allclose(radii, spec.wind_radius)),
        f"{radii.min():.4f}..{radii.max():.4f} vs {spec.wind_radius}",
    )
    entry_z = points[labels.index("wind_entry")][2]
    heights = points[orbit][:, 2]
    check(
        "helix climbs turns * climb_per_turn, monotonically",
        bool(
            abs((heights[-1] - entry_z) - spec.climb_per_turn * spec.turns) < 1e-9
            and np.all(np.diff(heights) > 0)
        ),
        f"{heights[-1] - entry_z:.4f} m",
    )
    # Each turn has to pass OVER the last one, not graze it. The outlet's
    # underside is half a rope below the orbit height and the previous wrap's top
    # is half a rope above its own, so the gap between consecutive turns is
    # `climb - 2*rope_radius`. At the 0.008 this shipped with, that gap was
    # exactly ZERO: turn two went past turn one touching it. That is the position
    # the second turn kept failing at, and the one that lifting the hand by hand
    # got past.
    turn_gap = spec.climb_per_turn - 2.0 * float(cfg.rope.radius)
    check(
        "consecutive turns clear each other",
        turn_gap > 0.0,
        f"{turn_gap * 1000:+.1f} mm between the outlet's underside and the "
        f"previous wrap's top (climb {spec.climb_per_turn * 1000:.0f} mm, rope "
        f"{2 * float(cfg.rope.radius) * 1000:.0f} mm thick)",
    )
    # ...and the whole spiral has to fit under the post's top, which is what
    # bounds how many turns this layout can do at all. Stated as a relation, not
    # a number, so raising `turns` fails here instead of in the sim.
    post_top_task = float(post.z) + 0.5 * float(post.height)
    spiral_top = (
        spec.wind_z_start + spec.turns * spec.climb_per_turn + float(cfg.rope.radius)
    )
    room = post_top_task - 0.010
    check(
        "the whole spiral fits below the post top",
        spiral_top <= room + 1e-9,
        f"top wrap at {spiral_top:.3f} vs {room:.3f} usable ({post_top_task:.3f} "
        f"post top less 10 mm); this post and climb hold "
        f"{int((room - spec.wind_z_start) // spec.climb_per_turn)} turns",
    )
    post_top = layout.world_z(float(post.z) + 0.5 * float(post.height))
    check(
        "oracle stays below the post top (the gateway is not used)",
        float(heights.max()) < post_top,
        f"max {heights.max():.4f} vs top {post_top:.4f}",
    )

    print("\nplug entry")
    # Where the cable meets the plug. `connector_mesh` is a SOLID of revolution
    # with no bore, so the rope's tube always passes through the plug's surface;
    # the only thing that decides whether that reads as a cable entering a
    # fitting or as clipping is whether it goes in through the cap ON THE AXIS.
    #
    # Lying on its side the plug rests on its flange, so its axis sits exactly
    # `flange_radius` above the board (`cable_routing.py` `_add_endpoint_handle`)
    # -- a height the placement fixes on its own, without consulting `rope.z`.
    # If the two disagree the cable goes in through the side of the cap.
    connector_cfg = cfg.rope.endpoint_handle.connector
    if str(getattr(connector_cfg, "pose", "upright")) == "flat":
        axis_z = float(connector_cfg.flange_radius)
        rope_z = float(cfg.rope.z)
        rope_r = float(cfg.rope.radius)
        check(
            "the cable meets the plug's cap on its axis",
            abs(rope_z - axis_z) <= rope_r,
            f"rope centreline at {rope_z * 1000:.0f} mm, plug axis at "
            f"{axis_z * 1000:.0f} mm (flange_radius), off by "
            f"{(rope_z - axis_z) * 1000:+.0f} mm for a {rope_r * 1000:.0f} mm rope",
        )
        check(
            "and clears the column wall it runs inside",
            rope_z - rope_r >= axis_z - float(connector_cfg.column_radius),
            f"rope bottom at {(rope_z - rope_r) * 1000:.0f} mm vs column bottom at "
            f"{(axis_z - float(connector_cfg.column_radius)) * 1000:.0f} mm",
        )

    print("\ncable exit")
    # Where the cable leaves the plug, and whether it can get from there to the
    # post. `physical_handle.carry_pitch_deg` decides: 0 carries it in the pose it
    # was grasped in (on its side, cable out along the axis at the grip centre's
    # own height), -90 stands it up with the cap on top, +90 stands it on its cap.
    connector = cfg.rope.endpoint_handle.connector
    grasp_h = float(connector.flange_height) + 0.5 * float(connector.column_height)
    cap_offset = (
        float(connector.flange_height)
        + float(connector.column_height)
        + 0.35 * float(connector.column_height)
        - grasp_h
    )
    pad_half_height = 0.0085  # panda.xml fingertip_pad_collision_1, half size along z
    # Where the cable actually leaves the plug, relative to the grip centre.
    # `connector_mesh` puts the local origin at the grasp column's middle, so the
    # cap's apex -- the point the cable enters -- is half a column plus the cap
    # beyond it. Lying flat that offset is horizontal and the exit is at the grip
    # centre's own height; pitched it is vertical, above or below by the sign.
    connector = cfg.rope.endpoint_handle.connector
    column_height = float(connector.column_height)
    cap_offset = 0.5 * column_height + float(
        getattr(connector, "cap_height", 0.35 * column_height)
    )
    pitch = math.radians(float(getattr(cfg.physical_handle, "carry_pitch_deg", 0.0)))
    exit_height = spec.wind_z_start - cap_offset * math.sin(pitch)
    # The fingertips reach 9.4 mm below the pad centre: the finger body starts
    # 58.4 mm below the hand (panda.xml `left_finger`) and its mesh runs 53.9 mm
    # further (`finger_0.obj`), against HAND_TO_PAD_Z of 102.9.
    finger_reach_below_pads = 0.0584 + 0.0539 - HAND_TO_PAD_Z
    fingertip_height = spec.wind_z_start - finger_reach_below_pads
    # Which WAY the carry pitch turns the plug, computed the same way the demo
    # does rather than asserted in prose. The plug's local +z is its cap, the end
    # that swallows the cable; about `z x plug_axis` a positive pitch sends the
    # cap down and the PIN up -- "plug up" in this task's wording, and what the
    # config asks for -- while a negative one does the opposite. The sign is the
    # whole statement of intent, and this is where it gets checked: getting the
    # cross product backwards flips both, and every number below still reads fine
    # because they all follow the pitch rather than assert a direction.
    if abs(pitch) > 1e-9:
        heading = math.atan2(
            *(
                layout.route_polyline("initial")[-1][:2]
                - layout.route_polyline("initial")[-2][:2]
            )[::-1]
        )
        flat_quat = quat_mul(
            quat_about_axis((0.0, 0.0, 1.0), heading),
            quat_about_axis((0.0, 1.0, 0.0), -0.5 * math.pi),
        )
        cap = _quat_axis_z(flat_quat)
        turned = _quat_axis_z(
            quat_mul(quat_about_axis(np.cross((0.0, 0.0, 1.0), cap), pitch), flat_quat)
        )
        wanted = -1.0 if pitch > 0.0 else 1.0
        check(
            "the carry pitch stands the plug on its axis, "
            + ("pin up / cap down" if wanted < 0 else "pin down / cap up"),
            abs(turned[2] - wanted) < 0.001,
            f"cap points {np.round(turned, 3).tolist()} after "
            f"{math.degrees(pitch):.0f}deg (flat: {np.round(cap, 3).tolist()})",
        )

    # How far the cable's exit is from the jaw. There are three ways to be clear
    # of it, and the carry pose decides which is in play:
    #   flat                 -- clear ALONG the plug's axis: cap offset vs reach
    #   pin up / cap down    -- clear BELOW the fingertips
    #   pin down / cap up    -- clear ABOVE the pads
    # The fingers reach 10.5 mm along the axis (`finger_0.obj`, x +-0.0105).
    #
    # None is comfortable at the shipped geometry, which is why this only asks
    # for "outside at all". Flat leaves 6.5 mm, and measured 2026-08-15 that was
    # not enough: the rope's last 3 cm sat inside the jaw for the whole orbit
    # (`near_s` 0.96, `near_depth` -0.011, `pad_gap` 0.0032) even at the
    # waypoints where the plug's alignment was perfect.
    #
    # Pin up -- what ships -- buys 7.6 mm below the fingertips, and is the only
    # one of the three clear at EVERY bearing. Its cost is that the outlet then
    # aims at the board and the rope folds through 90 degrees in the 28 mm below
    # it, against a 27 mm danger line this task set for itself; that is reported
    # below and watched on the run, not checked here. Pin down buys 8.5 mm above
    # the pads instead, but is clear of the PADS only: the finger bodies run
    # `finger_reach_above_pads` higher still, so the exit sits in the slot
    # between them and only the two bearings along the finger thickness are open.
    #
    # The fix that needs no compromise at all is a longer nose (`cap_height`),
    # which clears the fingers axially without bending anything. Open question
    # there: the plug is placed with its origin ON the rope's endpoint
    # (`tasks/routing/cable_routing.py` `_add_endpoint_handle`), so a longer cap
    # swallows more rope than the follow band welds.
    finger_reach_along_axis = 0.0105
    finger_reach_above_pads = HAND_TO_PAD_Z - 0.0584
    axial_clear = cap_offset * math.cos(pitch) - finger_reach_along_axis
    vertical_clear = fingertip_height - exit_height
    above_pads_clear = exit_height - (spec.wind_z_start + pad_half_height)
    check(
        "the cable's exit is outside the pads",
        max(axial_clear, vertical_clear, above_pads_clear) > 0.0,
        f"{axial_clear * 1000:+.1f} mm along the axis, "
        f"{vertical_clear * 1000:+.1f} mm below the fingertips, "
        f"{above_pads_clear * 1000:+.1f} mm above the pad tops "
        f"(carry pitch {math.degrees(pitch):.0f}deg, cap offset "
        f"{cap_offset * 1000:.0f} mm) -- thin whichever way, see the comment",
    )

    check(
        "the cable leaving the plug has room to bend back to the board",
        exit_height - float(cfg.rope.radius) > 3.0 * float(cfg.rope.radius),
        f"{(exit_height - float(cfg.rope.radius)) * 1000:.0f} mm of drop for a "
        f"{float(cfg.rope.radius) * 1000:.0f} mm rope",
    )
    # The rope has to meet the post's shaft: above the flared base, below the
    # top it must never cross.
    flare_top = 0.010  # prefabs.rope_routing_post.base_height
    check(
        "the cable meets the post on its shaft",
        flare_top < exit_height < post_top - TASK_ORIGIN[2],
        f"cable exit at z={exit_height:.4f}, shaft spans "
        f"{flare_top:.4f}..{post_top - TASK_ORIGIN[2]:.4f}",
    )
    # Reported, not checked: the cost the chosen carry pose takes on. Whether it
    # matters is a contact question only a run can answer -- watch `pad_gap`,
    # `intrusion` and `PADCONTACT`. A permanently red check for a cost we chose
    # would teach people to skim past this whole section.
    if abs(pitch) < 1e-9:
        print(
            f"  [--] cable exits along the plug axis, through the jaw: "
            f"{cap_offset * 1000:.0f} mm of cable inside pads reaching "
            f"+-{pad_half_height * 1000:.1f} mm of the axis"
        )
    elif pitch < 0.0:
        print(
            f"  [--] cable exits {above_pads_clear * 1000:.1f} mm above the pads "
            f"but still between the fingers, whose bodies run "
            f"{finger_reach_above_pads * 1000:.1f} mm above them; the exit "
            f"bearing sweeps a full turn per orbit and meets a finger's inner "
            f"face twice a turn"
        )
    else:
        print(
            f"  [--] cable exits {vertical_clear * 1000:.1f} mm below the "
            f"fingertips, pointing at the board: the rope turns 90 degrees "
            f"inside the {exit_height * 1000:.0f} mm between the outlet and the "
            f"surface"
        )

    print("\nplacement")
    # How high the plug's origin has to be when it is set down, for the pose it
    # is carried in -- `physical_handle.z_offset` is what carries that, and the
    # two have to be changed together. The plug is mesh-only and pinned by the
    # latch, so nothing in the solver corrects a wrong height: too low buries the
    # body in the board, too high leaves it hanging (measured 2026-08-15, 112 mm
    # of it, when the hand-off fired after the retreat instead of before).
    seat_task_z = float(points[-1][2]) - TASK_ORIGIN[2]
    if abs(abs(pitch) - 0.5 * math.pi) < 1e-9:
        # Standing on its axis: pin down rests on the flange (its pin buried in
        # the board, which is what "plugged into the target zone" looks like),
        # pin up rests on the cap itself.
        under_origin = (
            float(connector.flange_height) + 0.5 * column_height
            if pitch < 0.0
            else cap_offset
        )
    else:
        # On its side it rests on the flange's rim, so the axis is one flange
        # radius up.
        under_origin = float(connector.flange_radius)
    check(
        "the plug is set down ON the board for the pose it is carried in",
        abs(seat_task_z - under_origin) <= 0.0005,
        f"seat at {seat_task_z * 1000:.1f} mm, pose needs "
        f"{under_origin * 1000:.1f} mm (rope route {float(cfg.rope.z) * 1000:.0f} "
        f"mm + z_offset {float(cfg.physical_handle.z_offset) * 1000:.0f} mm, "
        f"carry pitch {math.degrees(pitch):.0f}deg)",
    )

    print("\ntopology")
    turns_spawn = winding_number(densify(layout.route_polyline("initial")), center, wrap_band)
    check(
        "spawn route does not encircle the post",
        abs(turns_spawn) < 0.25,
        f"winding {turns_spawn:+.3f}",
    )

    def finished_rope(sign: float) -> np.ndarray:
        """Rope in the finished state: anchor -> post -> wraps -> target port.

        Note this model closes to the seat the SHORT way, so its sweep is always
        `turns` plus something inside +-0.5 turn, and `winding_number` -- which
        rounds -- always returns exactly `turns`. That makes the two checks below
        a test of the SIGN convention and nothing more; they cannot fail on
        magnitude. The real rope does not take the short way out, and the sweep
        check further down is the one that measures what it does take.
        """

        entry = float(np.arctan2(anchor[1] - center[1], anchor[0] - center[0]))
        exit_angle = float(np.arctan2(seat[1] - center[1], seat[0] - center[0]))
        total = sign * (2.0 * math.pi * spec.turns) + (
            (exit_angle - entry + math.pi) % (2.0 * math.pi) - math.pi
        )
        angles = entry + np.linspace(0.0, total, 400)
        wrapped = np.stack(
            [
                center[0] + settle_radius * np.cos(angles),
                center[1] + settle_radius * np.sin(angles),
                np.full(len(angles), layout.world_z(float(cfg.rope.z))),
            ],
            axis=1,
        )
        return densify(np.vstack([anchor[None, :], wrapped, seat[None, :]]))

    turns_forward = winding_number(finished_rope(spec.sign), center, wrap_band)
    check(
        "a finished rope reads the target winding",
        abs(turns_forward - spec.target_winding) < 0.25,
        f"{turns_forward:+.3f} vs {spec.target_winding:+.1f}",
    )
    mirrored = "cw" if spec.direction == "ccw" else "ccw"
    command_mirror, plan_mirror = plan_rope_winding_route(layout, direction=mirrored)
    turns_mirror = winding_number(finished_rope(-spec.sign), center, wrap_band)
    check(
        f"the mirrored run ({mirrored}) reads the opposite sign",
        abs(turns_mirror - command_mirror.target_winding) < 0.25
        and command_mirror.target_winding == -spec.target_winding,
        f"{turns_mirror:+.3f} vs {command_mirror.target_winding:+.1f}",
    )
    mirror_points = np.array([waypoint.position for waypoint in plan_mirror.waypoints])

    def sweep(pts: np.ndarray) -> float:
        angles = np.unwrap(
            np.arctan2(pts[orbit][:, 1] - center[1], pts[orbit][:, 0] - center[0])
        )
        return float(angles[-1] - angles[0])

    check(
        "the mirrored orbit sweeps the other way",
        sweep(points) > 0.0 > sweep(mirror_points),
        f"{math.degrees(sweep(points)):+.0f}deg vs {math.degrees(sweep(mirror_points)):+.0f}deg",
    )

    # What the rope's sweep actually is when it leaves the post the way the
    # oracle leaves it: along the exit tangent, then across to C. `winding_number`
    # is `round(sweep)`, so the criterion is decided by which side of the nearest
    # half-integer the sweep lands on -- and the run-in from the anchor plus that
    # run-out are pure overhead on top of the wrap count. Measured 2026-08-13:
    # 2.674 turns for a two-turn wrap, i.e. past 2.5, and the GPU run duly read
    # +3.000 and failed its own success check.
    def oracle_rope(through: str) -> np.ndarray:
        """anchor -> wraps settled on the post -> the oracle's path from there."""

        entry = float(np.arctan2(anchor[1] - center[1], anchor[0] - center[0]))
        last = orbit[-1]
        end_angle = float(
            np.arctan2(points[last][1] - center[1], points[last][0] - center[0])
        )
        total = spec.sign * (2.0 * math.pi * spec.turns) + (
            (end_angle - entry + math.pi) % (2.0 * math.pi) - math.pi
        )
        angles = entry + np.linspace(0.0, total, 600)
        wrapped = np.stack(
            [
                center[0] + settle_radius * np.cos(angles),
                center[1] + settle_radius * np.sin(angles),
                np.full(len(angles), layout.world_z(float(cfg.rope.z))),
            ],
            axis=1,
        )
        tail = points[last + 1 : labels.index(through) + 1]
        parts = [anchor[None, :], wrapped] + ([tail] if len(tail) else [])
        return densify(np.vstack(parts))

    # The verdict (2026-08-27) is the whole-rope count closed from the free end
    # back to the anchor, and that count moves whenever the free end crosses the
    # ray opposite the anchor -- so the run to C is part of the count. Summed
    # along the free end's whole path, spawn to C, it has to land on the target.
    # Reported alongside: what the spawn route reads under that closure. This
    # layout's spawn arc passes the post on the far side from the closure and
    # reads -1 where the task book's "0 -> 2" says 0; the oracle's three
    # crossings (two orbits and the run to C) then land on +2. Not a failure --
    # the target is met -- but the "starts at 0" in the docs is the on-post
    # reading, not this one.
    spawn_reading = spawn_winding(layout, spec)
    path_delta = free_end_winding_delta(
        [layout.route_polyline("initial")[-1]] + list(points), center, anchor
    )
    # 2026-09-05: the run to C is chosen by the planner (`to_c_route: closure`),
    # straight where that keeps the count right -- the shipped layout -- and
    # round the far side (`to_C_around`) where a randomised C sits past the ray
    # opposite the anchor. On the shipped layout the run is still straight.
    check(
        "the verdict is the closed whole-rope count, chosen route to C",
        str(getattr(getattr(cfg, "success", None), "winding_metric", "on_post")) == "closure"
        and spec.to_c_route == "closure",
        "straight run on the shipped layout" if "to_C_around" not in labels else "via to_C_around",
    )
    check(
        "spawn reading + the free end's whole path (orbits AND the run to C) = target",
        abs(spawn_reading + path_delta - spec.target_winding) < 1e-6,
        f"{spawn_reading:+.0f} {path_delta:+d} = {spawn_reading + path_delta:+.0f}, "
        f"target {spec.target_winding:+.0f}",
    )
    check(
        "the shipped layout's run to C is the straight one",
        "to_C_around" not in labels,
        "C south of the post (bearing 290) is short of the ray opposite the anchor (335)",
    )
    sweep_final = winding_sweep(oracle_rope("place_at_C"), center, wrap_band)
    margin = 0.5 - abs(sweep_final - round(sweep_final))
    check(
        "the finished sweep stays on the target's side of the rounding boundary",
        abs(round(sweep_final) - spec.target_winding) < 0.5,
        f"sweep {sweep_final:+.3f} turns rounds to {round(sweep_final):+d}, "
        f"target {spec.target_winding:+.1f} "
        f"(sweep at the last orbit point: "
        f"{winding_sweep(oracle_rope('wind_t%d_%02d' % (spec.turns, spec.arc_points_per_turn)), center, wrap_band):+.3f}; "
        f"margin to the boundary {margin:.3f})",
    )

    # The wrist schedule. `yaw` on a winding waypoint is a tool roll relative to
    # the grasp yaw, and the whole gripper turns by it -- hand, plug and rope end
    # together. It tracks the orbit 1:1 for `yaw_forward_points` of each turn,
    # then hands all of that back over the points that remain -- except on the
    # last turn, which holds instead, because a return only ever buys travel for
    # the tracking that follows it.
    print("\nwrist schedule")
    rolls = {w.label: (w.yaw or 0.0) for w in plan.waypoints}
    if not spec.yaw_track:
        check("yaw tracking is off; the wrist holds the grasp pose", not any(rolls.values()))
    else:
        orbit_labels = [lab for lab in labels if lab.startswith("wind_t")]
        step_angle = 2.0 * math.pi / spec.arc_points_per_turn
        forward = spec.yaw_forward_points
        # Gains, in units of the orbit step, between consecutive orbit points.
        # The step INTO point k has index k-2 here: the first orbit point's step
        # comes from wind_entry, which is not in this list.
        gains = [
            (rolls[b] - rolls[a]) / (spec.sign * step_angle)
            for a, b in zip(orbit_labels[:-1], orbit_labels[1:])
        ]
        forward_gains = [
            gain
            for i, gain in enumerate(gains)
            if (i + 1) % spec.arc_points_per_turn + 1 <= forward
        ]
        check(
            "the wrist tracks the orbit 1:1 through the forward stretch",
            bool(forward_gains) and max(abs(g - 1.0) for g in forward_gains) < 1e-9,
            f"{len(forward_gains)} forward steps, gain "
            f"{min(forward_gains):.3f}..{max(forward_gains):.3f}",
        )
        # The lift must not roll. It is a 35 mm vertical move off the board with
        # the rope still lying on it, floored at 40 steps, and the plug has just
        # been picked up -- the worst place in the route to ask the wrist for a
        # large angle. It took the full pre-roll until 2026-08-15, which at the
        # old flick schedule's -90 degrees survived and at -132 dragged the plug
        # 10 mm through the board on waypoint 1. The pre-roll belongs on the long
        # travel to `wind_entry`.
        check(
            "the lift off the port holds the pose the plug was grasped in",
            abs(rolls["lift_from_port"]) < 1e-12,
            f"lift roll {math.degrees(rolls['lift_from_port']):+.1f}deg, "
            f"pre-roll deferred to wind_entry "
            f"({math.degrees(rolls['wind_entry']):+.1f}deg)",
        )
        # Nothing may turn the wrist once the orbit is done: the rope is already
        # wound and has nowhere to pay out the torsion, so a roll during the exit
        # or the set-down goes straight into the rope.
        after = [lab for lab in labels[labels.index(orbit_labels[-1]) :]]
        check(
            "the wrist locks after the last orbit point",
            len({round(rolls[lab], 12) for lab in after}) == 1,
            "held at "
            f"{math.degrees(rolls[after[0]]):+.0f}deg through {', '.join(after[1:])}",
        )
        # Franka joint7 travels +-2.8973 rad (166 deg) and the grasp does not land
        # it centred -- measured 2026-08-15, a run started at -0.4296 rad, 25
        # degrees off. `WRIST_BUDGET` is what is left, and the planner clamps the
        # alignment phase so the whole schedule fits inside it. Measure the
        # absolute roll, not the span: the phase slides the band, and an
        # unclamped one put a one-turn plan at +227 degrees.
        worst_roll = max(abs(value) for value in rolls.values())
        check(
            "the whole schedule fits the wrist's travel, phase included",
            worst_roll <= WRIST_BUDGET + 1e-9,
            f"worst roll {math.degrees(worst_roll):+.0f}deg of a "
            f"{math.degrees(WRIST_BUDGET):.0f}deg budget "
            "(joint7 166 less a 25deg grasp offset)",
        )

        def turn_end(turn):
            return rolls[f"wind_t{turn}_{spec.arc_points_per_turn:02d}"]

        # Every turn but the last must close, or the roll ratchets and turn two is
        # not turn one. The first shipped schedule did not close evenly -- flicks
        # at points 2 and 6 threw 270 in turn 1 and 360 in turn 2, and the
        # reported symptom was "turn 1 looks fine, turn 2 twists".
        closing = [
            turn_end(turn) - (turn_end(turn - 1) if turn > 1 else rolls["wind_entry"])
            for turn in range(1, spec.turns)
        ]
        check(
            "every turn but the last returns the wrist to where it started",
            all(abs(v) < 1e-9 for v in closing),
            (
                ", ".join(f"{math.degrees(v):+.1f}" for v in closing) + "deg net"
                if closing
                else "single turn; nothing to close"
            ),
        )
        # ...and the last turn does NOT return. The return buys travel for the
        # tracking that follows it, and after the last turn there is none: on a
        # one-turn run `winding` already reads +1.000 when the return starts, and
        # giving the travel back swept the plug's alignment through a whole turn
        # and dragged the rope into the jaw (`runs/rolling_return_1turn.log`,
        # `intrusion` 51 -> 190). The old flick schedule made the same call for
        # the same reason; this check exists because replacing the flicks lost it.
        held = [
            rolls[f"wind_t{spec.turns}_{i:02d}"]
            for i in range(forward, spec.arc_points_per_turn + 1)
        ]
        check(
            "the last turn holds its roll instead of handing it back",
            max(held) - min(held) < 1e-9,
            f"held at {math.degrees(held[0]):+.0f}deg for the last "
            f"{spec.arc_points_per_turn - forward} orbit points",
        )
        # No waypoint may ask the wrist for half a turn or more. The command is a
        # quaternion and the interpolation takes the short arc, so a 264-degree
        # request is executed as 96 in the opposite direction: measured
        # 2026-08-15, that drove joint7 onto its stop and left it welded there for
        # the rest of the route. `WindingSpec.from_config` refuses such a schedule
        # outright; this is the same guard against the emitted waypoints.
        steps = [abs(rolls[b] - rolls[a]) for a, b in zip(labels[:-1], labels[1:])]
        check(
            "no single waypoint asks the wrist past the short-arc boundary",
            max(steps) < math.pi - 1e-9,
            f"largest single turn {math.degrees(max(steps)):.0f}deg "
            f"(hard limit 180, spec refuses past {math.degrees(MAX_WRIST_STEP):.0f})",
        )
        # The alignment error: where the plug's bore points minus where the rope
        # arrives at it. Constant through the forward stretch by construction (the
        # planner puts the phase there, as far as the joint can spare); past 90
        # degrees the rope enters through the plug's side rather than its cap.
        errors = [
            math.atan2(math.sin(raw), math.cos(raw))
            for raw in (
                rolls[lab] - spec.sign * step_angle * (i + 1)
                for i, lab in enumerate(orbit_labels)
            )
        ]
        forward_errors = [
            e
            for i, e in enumerate(errors)
            if i % spec.arc_points_per_turn + 1 <= forward
        ]
        spread = max(forward_errors) - min(forward_errors)
        check(
            "the plug holds one alignment through the whole forward stretch",
            spread < 1e-9,
            f"{len(forward_errors)} forward points, spread "
            f"{math.degrees(spread):.1e}deg",
        )
        # Half a return sweep is obtuse; a hold only drifts, and over
        # (per_turn - forward) steps of one orbit step each it reaches 90 degrees
        # at worst, which is the boundary and not past it. So only the turns that
        # return cost anything here.
        returning = max(0, spec.turns - 1)
        obtuse = (
            0.5
            * returning
            * (spec.arc_points_per_turn - forward)
            / (spec.turns * spec.arc_points_per_turn)
        )
        check(
            "the returns cost at most a quarter of the route in side-on entry",
            obtuse <= 0.25 + 1e-9,
            f"{obtuse * 100:.1f}% of the orbit obtuse: {returning} turn(s) return, "
            f"the last holds; forward {forward}/{spec.arc_points_per_turn} points "
            "exactly aligned",
        )

    # The twist tracker, against synthesised motion rather than a solver. The
    # measure it replaces read +0.40 turns on a rope lying still, so the first
    # check below -- bend the rope without wringing it, read zero -- is the whole
    # reason this exists, and the rest bound what the reading can be trusted for.
    print("\ntwist tracking")
    TWIST_BINS, TWIST_RING = 24, 8

    def twist_rope(bend: float, twist_turns, length: float = 0.5) -> np.ndarray:
        """A tube of ring nodes: bent by ``bend`` radians, wrung by ``twist_turns``.

        ``twist_turns`` is per-bin (an array) or a scalar applied to every bin.
        The rings are laid on a frame parallel-transported along the centreline,
        so with ``twist_turns`` zero the tube carries no torsion by construction
        no matter how it is bent -- which is what the tracker has to agree with.
        The bend is planar, where spatial and time transport must give the same
        answer, so a disagreement here is the tracker's and not the test's.
        """

        s = np.linspace(0.0, length, TWIST_BINS)
        if abs(bend) < 1e-9:
            centre = np.stack([s, np.zeros_like(s), np.zeros_like(s)], axis=1)
            tangent = np.tile(np.array([1.0, 0.0, 0.0]), (TWIST_BINS, 1))
        else:
            radius = length / bend
            angle = s / radius
            centre = np.stack(
                [radius * np.sin(angle), radius * (1.0 - np.cos(angle)), np.zeros_like(s)],
                axis=1,
            )
            tangent = np.stack([np.cos(angle), np.sin(angle), np.zeros_like(s)], axis=1)
        # Planar curve: the out-of-plane direction is parallel along it.
        normal = np.tile(np.array([0.0, 0.0, 1.0]), (TWIST_BINS, 1))
        binormal = np.cross(tangent, normal)
        phase = np.broadcast_to(np.asarray(twist_turns, dtype=float), (TWIST_BINS,))
        ring = np.linspace(0.0, 2.0 * math.pi, TWIST_RING, endpoint=False)
        out = np.empty((TWIST_BINS * TWIST_RING, 3))
        for i in range(TWIST_BINS):
            a = ring + 2.0 * math.pi * phase[i]
            out[i * TWIST_RING : (i + 1) * TWIST_RING] = (
                centre[i]
                + 0.004 * np.cos(a)[:, None] * normal[i]
                + 0.004 * np.sin(a)[:, None] * binormal[i]
            )
        return out

    twist_groups = [
        np.arange(i * TWIST_RING, (i + 1) * TWIST_RING) for i in range(TWIST_BINS)
    ]
    twist_outer = np.ones(TWIST_BINS * TWIST_RING, dtype=bool)

    def run_twist(frames) -> dict:
        tracker = TwistTracker(frames[0], twist_groups, twist_outer)
        result = {}
        for frame in frames[1:]:
            result = tracker.update(frame)
        return result

    ramp = np.linspace(0.0, 1.0, TWIST_BINS)

    bent = run_twist([twist_rope(b, 0.0) for b in np.linspace(0.0, 0.5 * math.pi, 20)])
    check(
        "bending the rope without wringing it reads no twist",
        abs(bent["net"]) < 0.01 and abs(bent["span"]) < 0.01,
        f"net {bent['net']:+.4f}, span {bent['span']:.4f} through a 90deg bend",
    )
    wrung = run_twist([twist_rope(0.0, 2.0 * ramp * f) for f in np.linspace(0.0, 1.0, 40)])
    check(
        "a rope wrung two turns end to end reads two turns",
        abs(wrung["net"] - 2.0) < 0.01,
        f"net {wrung['net']:+.4f}",
    )
    # Half a turn per sample is where the unwrap breaks. Well inside it the
    # reading must still exceed one turn -- the failure this replaces was a
    # measure that could not.
    coarse = run_twist([twist_rope(0.0, 3.0 * ramp * f) for f in np.linspace(0.0, 1.0, 13)])
    check(
        "three turns still read three at a quarter turn per sample",
        abs(coarse["net"] - 3.0) < 0.02 and coarse["max_step"] < math.pi,
        f"net {coarse['net']:+.4f}, worst step "
        f"{math.degrees(coarse['max_step']):.0f}deg",
    )
    starved = run_twist([twist_rope(0.0, 3.0 * ramp * f) for f in np.linspace(0.0, 1.0, 6)])
    check(
        "and an under-sampled run says so instead of reading low quietly",
        starved["max_step"] > 0.5 * math.pi,
        f"worst step {math.degrees(starved['max_step']):.0f}deg "
        f"(net read {starved['net']:+.3f} against a true 3.000)",
    )
    # Wrung in the middle, both ends untwisted: end-to-end cancels to nothing and
    # only the span sees it. This is why the reading is not net alone.
    hump = np.sin(math.pi * ramp)
    middle = run_twist([twist_rope(0.0, hump * f) for f in np.linspace(0.0, 1.0, 30)])
    check(
        "a rope wrung in the middle shows in span even though net cancels",
        abs(middle["net"]) < 0.01 and abs(middle["span"] - 1.0) < 0.02,
        f"net {middle['net']:+.4f}, span {middle['span']:.4f}, "
        f"peak at s={middle['peak_s']:.2f}",
    )

    # The gripper-wrap metric, against a synthesised orbit rather than a solver.
    # The review's complaint is that the rope tangles with the gripper itself;
    # the claim behind the agreed cure is that a fixed wrist lets the strand
    # sweep one whole turn around the hand per orbit, and that a wrist turning
    # with the orbit leaves no sweep at all. Both halves are arithmetic, so both
    # are settled here before any GPU time is spent measuring them.
    print("\ngripper wrap")
    # Arbitrary: every quantity below is a difference or a distance.
    hand_z = 0.30

    def strand(hand_xy: np.ndarray, strand_z: float, count: int = 60) -> np.ndarray:
        """Centerline, free end first: from under the hand in to the post axis."""

        fractions = np.linspace(0.0, 1.0, count)[:, None]
        xy = hand_xy[None, :] + fractions * (center[:2] - hand_xy)[None, :]
        return np.hstack([xy, np.full((count, 1), strand_z)])

    def hand_frame(yaw: float) -> np.ndarray:
        """Fingers-down hand rotation at world yaw ``yaw``: Rz(yaw) @ diag(1,-1,-1)."""

        c, s = math.cos(yaw), math.sin(yaw)
        return np.array([[c, s, 0.0], [s, -c, 0.0], [0.0, 0.0, -1.0]])

    def orbit_wrap(yaw_of_angle, pad_clearance: float) -> tuple[float, int]:
        """Net wrap in turns, and the worst intrusion count, over the full route.

        ``pad_clearance`` is how far the strand hangs below the fingertip pads;
        negative puts it up among the fingers.
        """

        angles = np.linspace(0.0, spec.sign * 2.0 * math.pi * spec.turns, 16 * spec.turns + 1)
        bearings, yaws, intrusions = [], [], []
        for angle in angles:
            hand_xy = center[:2] + spec.wind_radius * np.array(
                [math.cos(angle), math.sin(angle)]
            )
            nodes = strand(hand_xy, hand_z - HAND_TO_PAD_Z - pad_clearance)
            metrics = gripper_frame_metrics(
                nodes,
                np.linspace(0.0, 1.0, len(nodes)),
                nodes,
                np.array([hand_xy[0], hand_xy[1], hand_z]),
                hand_frame(float(yaw_of_angle(angle))),
                free_end_first=True,
            )
            bearings.append(metrics["strand_bearing"])
            yaws.append(metrics["hand_yaw"])
            intrusions.append(metrics["intrusion"])
        swept = np.unwrap(bearings) - np.unwrap(yaws)
        return float((swept[-1] - swept[0]) / (2.0 * math.pi)), max(intrusions)

    fixed_wrap, clear_intrusion = orbit_wrap(lambda angle: 0.0, 0.010)
    check(
        "a fixed wrist sweeps the rope one turn around the gripper per orbit",
        abs(fixed_wrap - spec.target_winding) < 0.02,
        f"wrap {fixed_wrap:+.3f} over {spec.turns} orbits, target {spec.target_winding:+.1f}",
    )
    tracked_wrap, _ = orbit_wrap(lambda angle: angle, 0.010)
    check(
        "a wrist that turns with the orbit leaves no sweep",
        abs(tracked_wrap) < 0.02,
        f"wrap {tracked_wrap:+.3f}",
    )
    check(
        "rope hanging below the fingertips is not counted as intrusion",
        clear_intrusion == 0,
        "strand 10 mm below the pad centre, i.e. 1.5 mm clear of the fingertips",
    )
    _, jaw_intrusion = orbit_wrap(lambda angle: 0.0, -0.050)
    check(
        "rope up among the fingers is counted",
        jaw_intrusion > 0,
        f"{jaw_intrusion} nodes with the strand 50 mm above the pads",
    )

    print("\nrope length")
    rope_length = float(
        np.sum(np.linalg.norm(np.diff(layout.route_polyline("initial"), axis=0), axis=1))
    )
    # Taut-path length: anchor to the post, the wrapped part, then out to
    # wherever the plug currently is. Shared with the demo's pre-run check, so a
    # bad (turns, sweep_deg) pair cannot pass here and fail there or vice versa.
    worst, worst_label = taut_demand(layout, spec, plan.waypoints)
    margin = rope_length - worst
    check(
        "the rope reaches through the tightest moment of the route",
        margin > 0.0,
        f"need {worst:.3f} m at {worst_label}, rope {rope_length:.3f} m, margin {margin:+.3f} m",
    )
    # Slack is the fuel for the helix instability (see
    # docs/develop/physics/rope_backend_migration_zh.md): cable_routing coiled at
    # 19%. Too little and the rope fights its own anchor instead.
    slack = margin / worst
    low, high = SLACK_BAND
    check(
        "slack stays in the band that neither coils nor over-tightens",
        low <= slack <= high,
        f"{slack * 100:.1f}% at turns={spec.turns}, "
        f"sweep {float(cfg.rope.spawn_arc.sweep_deg):.0f}deg",
    )
    # ...and the same for every turn count the task ships: the demand moves
    # with the turn count (one turn on the post eats 2*pi*settle_radius =
    # 151 mm) and, since 2026-09-05, with the positions too, so the variation
    # block derives the sweep from the slack band instead of reading a table.
    # The rule must restore the hand-written pairs within a couple of degrees.
    print(
        f"  [--] one turn on the post eats "
        f"{2.0 * math.pi * settle_radius * 1000:.0f} mm of rope; "
        f"the spawn arc's sweep is what pays for it"
    )
    from topogym.tasks.routing._rope_winding_geometry import sweep_from_slack

    pairing = {1: 155.0, 2: 200.0, 3: 230.0}
    solved = {}
    for count in (1, 2, 3):
        probe_cfg = wrap({**raw, "winding": {**raw["winding"], "turns": count}})
        solved[count] = sweep_from_slack(StandInLayout(probe_cfg))
        print(f"  [--] turns={count}: sweep_deg {solved[count]:.1f} for mid-band (table {pairing[count]:.0f})")
    check(
        "the slack rule restores the turns -> sweep_deg pairing table within 3 degrees",
        all(abs(solved[c] - pairing[c]) <= 3.0 for c in (1, 2, 3)),
        ", ".join(f"{c}: {solved[c]:.1f}" for c in (1, 2, 3)),
    )
    plug_xy = np.asarray(layout.route_polyline("initial")[-1], dtype=float)[:2] - TASK_ORIGIN[:2]
    check(
        "the plug spawn rule restores the hand-written point (0.156, -0.157)",
        abs(plug_xy[0] - 0.156) < 0.001 and abs(plug_xy[1] + 0.157) < 0.001,
        f"({plug_xy[0]:+.4f}, {plug_xy[1]:+.4f})",
    )

    print("\nrun cost")
    physical = cfg.physical_handle
    steps = [int(waypoint.steps) for waypoint in plan.waypoints]
    wind_steps = sum(
        step for step, label in zip(steps, labels) if label.startswith("wind_t")
    )
    travel_steps = sum(steps) - wind_steps
    move = int(physical.move_steps)
    # HandleDragPrimitive: open, approach, descend, close, hold, lift test.
    grasp_steps = (
        int(physical.gripper_steps)          # open
        + move                                # approach
        + move // 2                           # descend
        + int(physical.gripper_steps)         # close
        + int(physical.close_hold_steps)      # grasp settle
        + move // 2                           # lift test
    )
    # Run-mode defaults; run.settle_steps is overridable but 60 is the shipped value.
    tail_steps = 60 + int(physical.route_settle_steps) + int(physical.release_hold_steps)
    total = grasp_steps + wind_steps + travel_steps + tail_steps

    def line(label: str, value: int) -> str:
        return f"  {label:<22} {value:>5} steps  {value * 0.66 / 60:>5.1f} min"

    print(line("grasp sequence", grasp_steps))
    print(line(f"winding ({len(orbit)} points)", wind_steps))
    print(line("travel", travel_steps))
    print(line("settle + release", tail_steps))
    print(line("TOTAL", total))
    print(
        f"  {len(labels)} waypoints; commanded wind {spec.wind_speed * 1000:.2f} mm/step, "
        f"travel {spec.travel_speed * 1000:.2f} mm/step"
    )

    check_one_turn(raw)
    check_rigid_grasp()

    print("\nvariation envelope")
    _check_variation_envelope(prefabs)

    print("\n" + ("FAIL: " + ", ".join(failures) if failures else "PASS: all checks"))
    return 1 if failures else 0


def _set(raw, dotted, value):
    node = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _derived_layout(raw):
    """The yaml's three derivations by hand (the hooks live in a module that imports Genesis)."""

    from topogym.tasks.routing._rope_winding_geometry import sweep_from_slack
    from topogym.tasks.routing._winding_post_geometry import target_x_from_frac, wind_z_from_frac

    cfg = wrap(raw)
    raw["winding"]["wind_z_start"] = wind_z_from_frac(cfg, float(raw["winding"]["wind_z_frac"]))
    raw["fixtures"]["C"]["x"] = target_x_from_frac(StandInLayout(wrap(raw)), float(raw["fixtures"]["C"]["x_frac"]))
    raw["rope"]["spawn_arc"]["sweep_deg"] = sweep_from_slack(StandInLayout(wrap(raw)))
    return StandInLayout(wrap(raw))


def _check_variation_envelope(prefabs) -> None:
    """2026-09-05, variation plan section 6.2 step 6: the yaml's `variation:` block.

    The three derivations restore the shipped layout; a cw instruction leaves
    the scene untouched (the anti-shortcut axis: same picture, opposite orbit);
    every vertex of the envelope passes the twelve feasibility rows; and two
    layouts outside the envelope fail the rows they should.
    """

    import itertools

    from topogym.tasks.routing._rope_winding_geometry import rope_winding_checks

    base = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    derived = _derived_layout(resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs))
    check(
        "frac 0.5 / 0.5 and the slack rule restore wind_z_start 0.045, C.x 0.075, sweep 200 +- 3",
        abs(float(derived.cfg.winding.wind_z_start) - 0.045) < 1e-9
        and abs(float(derived.cfg.fixtures.C.x) - 0.075) < 1e-9
        and abs(float(derived.cfg.rope.spawn_arc.sweep_deg) - 200.0) <= 3.0,
        f"wind_z_start {float(derived.cfg.winding.wind_z_start):.4f}, C.x {float(derived.cfg.fixtures.C.x):.4f}, "
        f"sweep {float(derived.cfg.rope.spawn_arc.sweep_deg):.1f}",
    )
    rows = {name: (measured, limit, ok) for name, measured, limit, ok in rope_winding_checks(derived)}
    check(
        "the twelve feasibility rows pass on the shipped layout",
        len(rows) == 12 and all(ok for _, _, ok in rows.values()),
        " ".join(f"{n}={m:+.4f}" for n, (m, _, _) in rows.items()),
    )
    # cw: same spawn route, same fixtures, mirrored orbit, opposite target.
    mirrored = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    mirrored["winding"]["direction"] = "cw"
    cw = _derived_layout(mirrored)
    ccw_spawn = derived.route_polyline("initial")
    cw_spawn = cw.route_polyline("initial")
    _, ccw_plan = plan_rope_winding_route(derived)
    _, cw_plan = plan_rope_winding_route(cw)
    check(
        "a cw instruction leaves the scene untouched: same spawn route and sweep, opposite target",
        ccw_spawn.shape == cw_spawn.shape
        and bool(np.allclose(ccw_spawn, cw_spawn, atol=1e-9))
        and abs(float(cw.cfg.rope.spawn_arc.sweep_deg) - float(derived.cfg.rope.spawn_arc.sweep_deg)) < 1e-6
        and WindingSpec.from_config(cw.cfg).target_winding == -WindingSpec.from_config(derived.cfg).target_winding
        and len(cw_plan.waypoints) == len(ccw_plan.waypoints),
        f"{len(cw_spawn)} spawn points, {len(cw_plan.waypoints)} waypoints each way",
    )
    cw_rows = {n: ok for n, _, _, ok in rope_winding_checks(cw)}
    check("...and passes the same twelve rows", all(cw_rows.values()))

    axes = []
    for entry in base["variation"]:
        if entry["kind"] == "uniform":
            axes.append((entry["path"], [float(entry["lo"]), float(entry["hi"])]))
        elif entry["kind"] == "choice":
            axes.append((entry["path"], list(entry["values"])))
    tightest: dict[str, float] = {}
    infeasible = []
    count = 0
    detours = 0
    for values in itertools.product(*(vals for _, vals in axes)):
        raw = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
        for (path, _), value in zip(axes, values):
            _set(raw, path, value)
        count += 1
        try:
            corner = _derived_layout(raw)
            corner_rows = rope_winding_checks(corner)
            bad = [n for n, _, _, ok in corner_rows if not ok]
            for n, m, l, _ in corner_rows:
                margin = (l - m) if n == "hand_reach" else (m - l)
                tightest[n] = min(tightest.get(n, float("inf")), margin)
            _, corner_plan = plan_rope_winding_route(corner)
            detours += int(any(w.label == "to_C_around" for w in corner_plan.waypoints))
        except ValueError as exc:
            bad = [f"derive: {exc}"]
        if bad:
            infeasible.append((values, bad))
    check(
        f"all {count} envelope corners are feasible",
        not infeasible,
        f"{len(infeasible)} infeasible" + (f"; first: {infeasible[0]}" if infeasible else "") + f"; {detours} need to_C_around",
    )
    print("  [--] tightest margin per row over the corners: " + " ".join(f"{n}={m:+.4f}" for n, m in tightest.items()))

    far = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    far["fixtures"]["POST"]["x"] = 0.060
    far_rows = {n: ok for n, _, _, ok in rope_winding_checks(_derived_layout(far))}
    check("a post at x=0.060 fails hand_reach (the plug spawn point is the farthest waypoint)", not far_rows["hand_reach"])
    # Without the anchor-lead cap the plug would sit past the ray opposite the
    # anchor on this corner (S north-east of the post) and the spawn arc would
    # already read a wrap; with it the plug slides back and the arc reads 0.
    past = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    past["fixtures"]["S"]["x"], past["fixtures"]["S"]["y"] = -0.120, 0.130
    past["fixtures"]["POST"]["x"], past["fixtures"]["POST"]["y"] = -0.020, -0.020
    past["rope"]["spawn_arc"]["anchor_lead_deg"] = -30.0
    past_layout = StandInLayout(wrap(past))
    past_reading = spawn_winding(past_layout, WindingSpec.from_config(past_layout.cfg))
    past["rope"]["spawn_arc"]["anchor_lead_deg"] = 20.0
    capped_layout = StandInLayout(wrap(past))
    capped_reading = spawn_winding(capped_layout, WindingSpec.from_config(capped_layout.cfg))
    check(
        "S north-east of the post: the uncapped plug spawn reads a wrap, the capped one reads 0",
        abs(past_reading) > 0.5 and abs(capped_reading) < 1e-6,
        f"uncapped {past_reading:+.0f}, capped {capped_reading:+.0f}",
    )


def check_one_turn(raw) -> None:
    """The same schedule checks again at `turns=1`, which is what gets run.

    The config ships `turns: 2` and everything above reads it, but the demo is
    driven at `task.winding.turns=1` for nearly every diagnostic run -- and the
    two are not the same schedule. On a one-turn plan the last turn is the ONLY
    turn, so it holds rather than returns and never reaches the low end of the
    band; sizing the alignment phase off `rolls` alone therefore read the band as
    112 degrees instead of 135 and let the phase push the plan to 154 of a 141
    budget. Nothing here caught it, because nothing here ran a one-turn plan.
    """

    print("\none turn")
    raw = {**raw, "winding": {**raw["winding"], "turns": 1}}
    cfg = wrap(raw)
    spec = WindingSpec.from_config(cfg)
    _, plan = plan_rope_winding_route(StandInLayout(cfg))
    rolls = [w.yaw or 0.0 for w in plan.waypoints]
    labels = [w.label for w in plan.waypoints]
    check(
        "the one-turn schedule fits the wrist's travel too",
        max(abs(v) for v in rolls) <= WRIST_BUDGET + 1e-9,
        f"worst roll {math.degrees(max(abs(v) for v in rolls)):+.0f}deg of a "
        f"{math.degrees(WRIST_BUDGET):.0f}deg budget",
    )
    steps = [abs(b - a) for a, b in zip(rolls[:-1], rolls[1:])]
    check(
        "and asks no waypoint past the short-arc boundary",
        max(steps) < math.pi - 1e-9,
        f"largest single turn {math.degrees(max(steps)):.0f}deg; the only turn "
        "holds instead of returning, so there is no fast unwind at all",
    )
    orbit = [lab for lab in labels if lab.startswith("wind_t")]
    held = [
        rolls[labels.index(f"wind_t1_{i:02d}")]
        for i in range(spec.yaw_forward_points, spec.arc_points_per_turn + 1)
    ]
    check(
        "and holds through the tail of its only turn",
        max(held) - min(held) < 1e-9,
        f"{len(orbit)} orbit points, held at {math.degrees(held[0]):+.0f}deg "
        f"for the last {spec.arc_points_per_turn - spec.yaw_forward_points}",
    )


class _StubBody:
    """Just enough of a Genesis entity for `RigidAttachment` to drive."""

    def __init__(self, pos, quat) -> None:
        self.pos = np.asarray(pos, dtype=float)
        self.quat = np.asarray(quat, dtype=float)

    def get_pos(self):
        return self.pos

    def get_quat(self):
        return self.quat

    def set_pos(self, pos, **_) -> None:
        self.pos = np.asarray(pos, dtype=float)

    def set_quat(self, quat, **_) -> None:
        self.quat = np.asarray(quat, dtype=float)


def check_rigid_grasp() -> None:
    """The held plug must not turn or slide inside the pads. Ever.

    This is the promise `planning/rope_winding_planner.py` states in prose --
    "the WHOLE GRIPPER turns by it -- hand, plug and rope end together, so
    nothing slides on the finger pads" -- and which was false in the shipped code
    until 2026-08-15: the grasp attachment pinned the plug to one WORLD
    orientation, so the wrist's whole +-135 degree schedule swept the pads across
    a plug that never moved.

    No solver needed: `RigidAttachment` is arithmetic on poses, so drive a stub
    body from a stub hand through more roll than the route asks for and check
    the relative pose is the one it was grasped in.
    """

    print("\nrigid grasp")
    hand = {"pos": np.array([0.1, 0.2, 1.05]), "quat": quat_about_axis((0, 1, 0), math.pi)}
    # The plug as this task holds it: lying flat, 103 mm below the hand.
    plug = _StubBody(
        hand["pos"] + np.array([0.0, 0.0, -HAND_TO_PAD_Z]),
        quat_mul(quat_about_axis((0, 0, 1), 0.89), quat_about_axis((0, 1, 0), -0.5 * math.pi)),
    )
    attachment = RigidAttachment(
        entity=plug,
        parent_pos_fn=lambda: hand["pos"],
        offset=np.zeros(3),
        parent_quat_fn=lambda: hand["quat"],
    )
    attachment.attach()

    def relative():
        w, x, y, z = plug.quat
        inverse = np.array([hand["quat"][0], -hand["quat"][1], -hand["quat"][2], -hand["quat"][3]])
        return quat_mul(inverse, plug.quat), _rotate_by_quat(inverse, plug.pos - hand["pos"])

    quat0, offset0 = relative()
    worst_turn = 0.0
    worst_slide = 0.0
    base = np.array(hand["quat"], dtype=float)
    for step in range(1, 61):
        # More roll than any waypoint asks for, about the vertical, plus a
        # little drift in the other axes so a yaw-only implementation cannot pass.
        hand["quat"] = quat_mul(
            quat_about_axis((0, 0, 1), math.radians(270.0) * step / 60.0), base
        )
        hand["pos"] = hand["pos"] + np.array([0.0, 0.0, 1e-4])
        attachment.sync()
        quat, offset = relative()
        # Angle between the two orientations, via the drift quaternion's vector
        # part. `2*acos(w)` is the textbook form and is useless here: near
        # identity it reads the square root of the floating-point error, which
        # showed up as a 2.4e-06 degree "slip" that is entirely acos.
        drift = quat_mul(np.array([quat0[0], -quat0[1], -quat0[2], -quat0[3]]), quat)
        worst_turn = max(
            worst_turn,
            2.0 * math.atan2(float(np.linalg.norm(drift[1:])), abs(float(drift[0]))),
        )
        worst_slide = max(worst_slide, float(np.linalg.norm(offset - offset0)))
    check(
        "the held plug neither turns nor slides in the gripper's frame",
        worst_turn < 1e-9 and worst_slide < 1e-9,
        f"through 270deg of roll: turned {math.degrees(worst_turn):.2e}deg, "
        f"slid {worst_slide * 1000:.2e}mm",
    )

    # The same attachment with the orbit spin fitted. Two things have to hold, and
    # they pull in opposite directions: the plug must turn by EXACTLY the
    # commanded angle about the world vertical (too little and torsion is still
    # injected, too much and it is injected the other way), and it must turn about
    # ITS OWN origin, because the rope is welded there -- a spin implemented about
    # the world's origin would swing the plug on a 1.1 m arm.
    spin = {"angle": 0.0}
    spun = _StubBody(plug.pos.copy(), plug.quat.copy())
    spun_attachment = RigidAttachment(
        entity=spun,
        parent_pos_fn=lambda: hand["pos"],
        offset=np.zeros(3),
        parent_quat_fn=lambda: hand["quat"],
        yaw_spin_fn=lambda: spin["angle"],
    )
    spun_attachment.attach()
    base_quat = np.asarray(spun.quat, dtype=float)
    base_pos = np.asarray(spun.pos, dtype=float)
    worst_angle = 0.0
    worst_move = 0.0
    for step in range(1, 91):
        # More than a full turn: two orbits ask for 720 degrees, which is exactly
        # why this cannot be the wrist's job.
        spin["angle"] = 2.0 * math.pi * step / 45.0
        spun_attachment.sync()
        wanted = quat_mul(quat_about_axis((0, 0, 1), spin["angle"]), base_quat)
        drift = quat_mul(
            np.array([wanted[0], -wanted[1], -wanted[2], -wanted[3]]), spun.quat
        )
        worst_angle = max(
            worst_angle,
            2.0 * math.atan2(float(np.linalg.norm(drift[1:])), abs(float(drift[0]))),
        )
        worst_move = max(worst_move, float(np.linalg.norm(spun.pos - base_pos)))
    check(
        "the orbit spin turns the plug about the vertical, through its own origin",
        worst_angle < 1e-9 and worst_move < 1e-9,
        f"through 720deg of spin: off by {math.degrees(worst_angle):.2e}deg, "
        f"moved {worst_move * 1000:.2e}mm",
    )

    # And the position-only default, which every other task was written against,
    # must be untouched by the above.
    plain_hand = {"pos": np.array([0.0, 0.0, 1.0])}
    plain = _StubBody(np.array([0.0, 0.0, 0.9]), np.array([1.0, 0.0, 0.0, 0.0]))
    plain_attachment = RigidAttachment(
        entity=plain,
        parent_pos_fn=lambda: plain_hand["pos"],
        offset=np.array([0.0, 0.0, -0.1]),
        quat=(1.0, 0.0, 0.0, 0.0),
    )
    plain_attachment.attach()
    plain_hand["pos"] = np.array([0.3, -0.2, 1.4])
    plain_attachment.sync()
    check(
        "the position-only attachment other tasks use is unchanged",
        bool(np.allclose(plain.pos, plain_hand["pos"] + np.array([0.0, 0.0, -0.1]))),
        f"child at {np.round(plain.pos, 4).tolist()}",
    )


if __name__ == "__main__":
    raise SystemExit(main())

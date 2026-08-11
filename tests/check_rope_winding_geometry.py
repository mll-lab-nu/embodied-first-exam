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
  - the rope is long enough for the tightest moment of the route, with margin.

    python tests/check_rope_winding_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): `topogym.planning` and
`topogym.supervision.rope_winding` are numpy-only, and the handful of `${}`
references this reads are resolved here by hand.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.planning.rope_winding_planner import (  # noqa: E402
    WindingSpec,
    plan_rope_winding_route,
    post_center,
)
from topogym.supervision.rope_winding import winding_number  # noqa: E402

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
        pos = np.asarray(self.cfg.fixtures[str(name)].pos, dtype=float).copy()
        if z is not None:
            pos[2] = float(z)
        return self.position_to_world(pos)

    def route_point(self, spec):
        if "pos" in spec:
            return self.position_to_world(spec["pos"])
        return self.fixture_pos(str(spec["fixture"]), z=float(self.cfg.rope.z))

    def route_polyline(self, name):
        return np.stack([self.route_point(p) for p in self.cfg.routes[name]], axis=0)


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


def main() -> int:
    raw = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    prefabs = yaml.safe_load(PREFABS.read_text(encoding="utf-8"))
    # The two interpolations the checks below dereference.
    raw["rope"]["radius"] = prefabs["rope_pbd"]["radius"]
    raw["rope"]["endpoint_handle"]["z_offset"] = raw["physical_handle"]["z_offset"]
    cfg = wrap(raw)

    layout = StandInLayout(cfg)
    spec = WindingSpec.from_config(cfg)
    center = post_center(layout, spec)
    post = cfg.fixtures[spec.post]
    settle_radius = float(post.radius) + float(cfg.rope.radius)
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
        f"{len(labels)} (expected {expected})",
    )
    orbit = [index for index, label in enumerate(labels) if label.startswith("wind_t")]
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
    post_top = layout.world_z(float(post.pos[2]) + 0.5 * float(post.height))
    check(
        "oracle stays below the post top (the gateway is not used)",
        float(heights.max()) < post_top,
        f"max {heights.max():.4f} vs top {post_top:.4f}",
    )

    print("\ntopology")
    turns_spawn = winding_number(densify(layout.route_polyline("initial")), center)
    check(
        "spawn route does not encircle the post",
        abs(turns_spawn) < 0.25,
        f"winding {turns_spawn:+.3f}",
    )

    def finished_rope(sign: float) -> np.ndarray:
        """Rope in the finished state: anchor -> post -> wraps -> target port."""

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

    turns_forward = winding_number(finished_rope(spec.sign), center)
    check(
        "a finished rope reads the target winding",
        abs(turns_forward - spec.target_winding) < 0.25,
        f"{turns_forward:+.3f} vs {spec.target_winding:+.1f}",
    )
    mirrored = "cw" if spec.direction == "ccw" else "ccw"
    command_mirror, plan_mirror = plan_rope_winding_route(layout, direction=mirrored)
    turns_mirror = winding_number(finished_rope(-spec.sign), center)
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

    # The oracle must not turn the plug: the rope end is welded to it, so any
    # plug rotation wrings the rope against the stationary finger pads. Twist is
    # relieved at the rope's end instead (`rope.fem.follow_swivel`).
    check(
        "the oracle never turns the plug",
        all((waypoint.yaw or 0.0) == 0.0 for waypoint in plan.waypoints),
        "twist is relieved by the end swivel, not by rotating the plug",
    )

    print("\nrope length")
    rope_length = float(
        np.sum(np.linalg.norm(np.diff(layout.route_polyline("initial"), axis=0), axis=1))
    )
    worst, worst_label = 0.0, ""
    for index, label in enumerate(labels):
        if label.startswith("wind_t"):
            wound = (orbit.index(index) + 1) / spec.arc_points_per_turn
        elif orbit and index > orbit[-1]:
            wound = float(spec.turns)
        else:
            wound = 0.0
        # Taut-path length: anchor to the post, the wrapped part, then out to
        # wherever the plug currently is.
        need = (
            float(np.linalg.norm(anchor[:2] - center[:2]))
            + wound * 2.0 * math.pi * settle_radius
            + float(np.linalg.norm(points[index][:2] - center[:2]))
        )
        if need > worst:
            worst, worst_label = need, label
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
    check(
        "slack stays in the band that neither coils nor over-tightens",
        0.05 <= slack <= 0.15,
        f"{slack * 100:.1f}%",
    )

    # Wall clock is why this route is kept short. One FEM+IPC step is ~0.66 s on
    # the reference machine (2026-08-11, docs/develop/physics/fem_ipc_step_cost_zh.md)
    # and no solver knob has moved it, so the only lever is how many steps the
    # run asks for. Counting only the waypoints understates it badly: the grasp
    # sequence in front of them is a fixed cost that was 40% of the first real
    # run, which is exactly the kind of thing an estimate has to include.
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

    print("\n" + ("FAIL: " + ", ".join(failures) if failures else "PASS: all checks"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

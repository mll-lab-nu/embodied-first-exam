"""Offline gate for `band_untwist` (docx 3.3, open-rope tabletop version).

No Genesis, no GPU: numpy + PyYAML, on the literal values in
`configs/task_configs/band_untwist_topogym_tabletop_v1.yaml` so the two cannot
drift. The rope spawns crossing itself once or twice in one of four shapes
(figure-8, "6", twist, O|-|O; `band.shape`); the shapes and the oracle's move
model have their own gate (`tests/check_band_untwist_sequence.py`), the
envelope's corners go through `tests/check_variant_corners.py --task
band_untwist`. This one covers what sits between them:

1. **Config and spawn geometry** -- the yaml's copies (tube radius, workspace
   box, arm base) equal their sources; the default layout is the figure-8 it
   has always been; the 8's analytic arc length matches its polyline at 30, 45
   and 60 degrees (the lobe-arc formula was right at 45 only until 2026-09-10);
   every shape's default block builds with its number of crossings.

2. **Self-crossing reading** (the verifier's open-polyline counter) -- the 8
   reads 1 with its over end on top, pressed flat (depth x0.02) still 1 (the
   docx's anti-shortcut: hiding the crossing does not change the judgement), a
   straight rope and a C whose ends lie side by side read 0 (the C is what a
   closed-curve counter gets wrong), a hand-built curve reads 2; on every
   shape and every over/under choice the measured crossing sequence is the one
   the generator declares; failure labels are read against the spawn count.

3. **Planner** (`band_untwist_planner`, on stub scenes whose task origin is not
   zero) -- the oracle's command is the move model's first move, `wrong_end`
   grasps the other plug at the same crossing, `one_move` caps the budget at 1,
   the waypoints are grasp / carry / cross / place, every hand target is inside
   the workspace box and under its ceiling.

    python tests/check_band_untwist_geometry.py

Prints one line per check and exits non-zero if any fails.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path

import numpy as np
import yaml
from dataclasses import replace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# `topogym.planning` is Genesis-free and imported normally; the task and
# verification packages import Genesis in their __init__, so their Genesis-free
# modules are loaded by path.
import topogym.planning.band_untwist_sequence as sequence  # noqa: E402
from topogym.planning.band_untwist_planner import (  # noqa: E402
    CROSS_RIDE_MIN,
    CROSS_TAUT,
    FLIP_SEGMENTS,
    RUNTIME_REACH_HEADROOM,
    make_band_untwist_rule,
)


def load_by_path(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fig8 = load_by_path("band_untwist_fig8", "topogym/tasks_legacy/entangle/_figure_eight_geometry.py")
shapes = load_by_path("band_untwist_shapes", "topogym/tasks_legacy/entangle/_band_shapes.py")
verifier = load_by_path("band_untwist_verifier", "topogym/verification/band_untwist_verifier.py")

TASK = yaml.safe_load((REPO / "configs/task_configs/band_untwist_topogym_tabletop_v1.yaml").read_text(encoding="utf-8"))
PREFABS = yaml.safe_load((REPO / "configs/prefab_configs/topogym_prefabs_v1.yaml").read_text(encoding="utf-8"))
COMMON = yaml.safe_load((REPO / "configs/common_configs/manipulation_space_tabletop_v1.yaml").read_text(encoding="utf-8"))
BAND = TASK["band"]
MERGE = float(TASK["success"]["crossing_merge_radius"])
WS = TASK["workspace"]


class Gate:
    def __init__(self) -> None:
        self.fails: list[str] = []

    def check(self, ok: bool, message: str) -> None:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
        if not ok:
            self.fails.append(message)


def densify(points: np.ndarray, step: float) -> np.ndarray:
    """Linear resample so segment lengths are <= ``step`` (no spline: the gate
    runs without `world/rope.py`, which imports Genesis)."""

    out = [np.asarray(points[0], dtype=float)]
    for a, b in zip(points[:-1], points[1:]):
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * (k / n))
    return np.stack(out, axis=0)


def common_leaves() -> dict:
    return dict(over_lift=float(BAND["over_lift"]), base_z=float(BAND["base_z"]), lift_ramp=float(BAND["lift_ramp"]),
                arc_points_per_quarter=int(BAND["arc_points_per_quarter"]))


def eight_spec(**changes) -> fig8.FigureEightSpec:
    e = dict(BAND["eight"])
    e.update(changes)
    return fig8.FigureEightSpec(
        closed_lobe_radius=float(e["closed_lobe_radius"]), open_lobe_radius=float(e["open_lobe_radius"]),
        end_gap=float(e["end_gap"]), half_angle_deg=float(e["half_angle_deg"]), over_end=int(e["over_end"]),
        center=(float(BAND["center_x"]), float(BAND["center_y"])), heading_deg=float(BAND["heading_deg"]),
        **common_leaves(),
    )


def shape_points(shape: str, **changes) -> np.ndarray:
    """Control points of the yaml's default block for ``shape`` (local frame
    for the new shapes, the yaml's centre for the 8)."""

    if shape == "eight":
        return fig8.figure_eight_control_points(eight_spec(**changes))
    block = dict(BAND[shape])
    block.update(changes)
    common = common_leaves()
    if shape == "six":
        spec = shapes.SixSpec(**{k: block[k] for k in ("loop_radius", "half_angle_deg", "short_len", "stem_len", "short_over")}, **common)
    elif shape == "twist":
        spec = shapes.TwistSpec(**{k: block[k] for k in ("closed_lobe_radius", "middle_lobe_radius", "open_lobe_radius",
                                                         "half_angle_deg", "end_gap", "over_end_x1", "over_end_x2")}, **common)
    else:
        spec = shapes.CurlsSpec(**{k: block[k] for k in ("loop_radius", "half_angle_deg", "stub_len", "middle_len",
                                                         "stub_side", "stub_over_a", "stub_over_b")}, **common)
    return shapes.shape_control_points(spec)


def declared(points: np.ndarray) -> tuple:
    return sequence.crossing_sequence(sequence.crossings(sequence.Rope.from_points(points), merge_radius=MERGE))


# --- 1. config and spawn geometry -------------------------------------------


def check_config(gate: Gate) -> None:
    print("\n== 1. config and spawn geometry")
    gate.check(float(BAND["tube_radius"]) == float(PREFABS["rope_pbd"]["radius"]),
               f"band.tube_radius {BAND['tube_radius']} = prefabs.rope_pbd.radius {PREFABS['rope_pbd']['radius']}")
    common_ws = COMMON["manipulation_space"]["workspace"]
    gate.check(list(WS["x"]) == list(common_ws["x"]) and list(WS["y"]) == list(common_ws["y"]),
               "task workspace box = manipulation_space.workspace (x, y)")
    mount = COMMON["robot_setup"]["mount"]["pos"]
    gate.check(list(TASK["reach"]["base_xy"]) == list(mount[:2]), f"reach.base_xy = robot_setup.mount.pos xy {mount[:2]}")

    # The default layout is today's figure-8, bit for bit.
    today = fig8.figure_eight_control_points(fig8.FigureEightSpec(
        closed_lobe_radius=0.040, open_lobe_radius=0.050, end_gap=0.080, half_angle_deg=45.0, over_lift=0.012,
        base_z=0.007, center=(0.02, 0.0), heading_deg=0.0, arc_points_per_quarter=3, lift_ramp=0.030, over_end=0))
    gate.check(BAND["shape"] == "eight" and np.array_equal(shape_points("eight"), today),
               "default layout is the figure-8 of 2026-08-27, control points bit for bit")

    for phi in (30.0, 45.0, 60.0):
        spec = replace_spec(eight_spec(half_angle_deg=phi), arc_points_per_quarter=60)
        xy = fig8.figure_eight_control_points(spec)[:, :2]
        length = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
        analytic = fig8.figure_eight_expected_arc_length(spec)
        gate.check(abs(length - analytic) < 1e-3 * analytic,
                   f"8 at {phi:.0f} deg: polyline {length * 1000:.1f} mm = analytic {analytic * 1000:.1f} mm")

    for shape in shapes.SHAPES:
        points = shape_points(shape)
        n = len(declared(points)) // 2
        gate.check(n == shapes.SHAPE_CROSSINGS[shape], f"{shape} default block: {n} crossing(s)")
        gate.check(float(points[:, 2].min()) - float(BAND["tube_radius"]) >= -1e-9, f"{shape} default block: tube clears the table")


def replace_spec(spec, **changes):
    from dataclasses import replace

    return replace(spec, **changes)


# --- 2. self-crossing reading ------------------------------------------------


def _straight(length: float, z: float) -> np.ndarray:
    return np.column_stack([np.linspace(0.0, length, 40), np.zeros(40), np.full(40, z)])


def _open_c(radius: float, gap_deg: float, z: float) -> np.ndarray:
    """A circle with a small opening: the two ends sit side by side, no crossing."""

    half = np.radians(gap_deg) / 2.0
    angles = np.linspace(np.pi + half, 3.0 * np.pi - half, 60)
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.full(60, z)])


def _two_crossings(z: float) -> np.ndarray:
    """A hand-built open curve that crosses itself exactly twice (segment 6 over
    segment 1, segment 7 over segment 0)."""

    xy = np.array([[0.00, 0.00], [0.10, 0.00], [0.10, 0.05], [-0.05, 0.05], [-0.05, -0.02],
                   [0.15, -0.02], [0.15, 0.03], [0.02, 0.03], [0.02, -0.01]])
    zs = np.full(len(xy), z)
    zs[6:] += 0.012
    return np.column_stack([xy, zs])


def state_of(points: np.ndarray, **kw):
    return verifier.BandUntwistPuzzleState(
        crossings=verifier.open_self_crossings(points, merge_radius=MERGE),
        end_heights=kw.pop("end_heights", (0.0, 0.0)), end_height_tolerance=0.005, **kw,
    )


def check_reading(gate: Gate) -> None:
    print("\n== 2. self-crossing reading")
    z0 = float(BAND["base_z"])
    dense = densify(shape_points("eight"), 0.006)
    pressed = dense.copy()
    pressed[:, 2] = z0 + (pressed[:, 2] - z0) * 0.02
    for label, polyline, expected in (
        ("figure-8 spawn", dense, 1),
        ("figure-8 pressed flat (depth x0.02)", pressed, 1),
        ("straight rope", _straight(0.5, z0), 0),
        ("C with ends side by side (no phantom closing segment)", _open_c(0.06, 20.0, z0), 0),
        ("hand-built curve with two crossings", densify(_two_crossings(z0), 0.006), 2),
    ):
        hits = verifier.open_self_crossings(polyline, merge_radius=MERGE)
        gate.check(len(hits) == expected, f"{label}: reads {len(hits)} (expected {expected})")
    hits = verifier.open_self_crossings(dense, merge_radius=MERGE)
    gate.check(hits[0].over_end == int(BAND["eight"]["over_end"]), f"figure-8: over end read {hits[0].over_end}")

    variants = [("eight", {}), ("eight", {"over_end": 1}), ("six", {"short_over": 0}), ("six", {"short_over": 1})]
    variants += [("twist", {"over_end_x1": a, "over_end_x2": b}) for a in (0, 1) for b in (0, 1)]
    variants += [("curls", {"stub_side": side}) for side in ("same", "opposite")]
    for shape, changes in variants:
        points = shape_points(shape, **changes)
        measured = state_of(densify(points, 0.006)).crossing_sequence
        gate.check(measured == declared(points), f"{shape} {changes}: measured sequence {measured} = declared")

    one = state_of(dense)
    gate.check(one.failure_label == "crossing_left", f"8 untouched: {one.failure_label} (crossing left)")
    gate.check(state_of(densify(_two_crossings(z0), 0.006)).failure_label == "crossing_added",
               "8 spawn, two crossings at the end: crossing_added (the wrong_end outcome)")
    gate.check(state_of(densify(_two_crossings(z0), 0.006), spawn_crossings=2).failure_label == "crossing_left",
               "two-crossing spawn, two at the end: crossing_left, not a wrong-end label")
    gate.check(state_of(_straight(0.5, z0), end_heights=(0.0, 0.05)).failure_label == "end_lifted",
               "no crossing but a plug held up: end_lifted")
    gate.check(state_of(_straight(0.5, z0)).is_terminal, "no crossing, plugs down: terminal")


# --- 3. planner ----------------------------------------------------------------


ORIGIN = (0.31, -0.07, 0.92)  # a task origin that is not zero, so frame handling is exercised


def stub_scene(task_points: np.ndarray):
    world = np.asarray(task_points, dtype=float) + np.asarray(ORIGIN)[None, :]
    params = sequence.ModelParams(
        rope_radius=float(BAND["tube_radius"]), lift_clearance=float(TASK["pinch"]["lift_clearance"]),
        place_clearance=float(TASK["pinch"]["place_clearance"]),
        min_plug_separation=float(TASK["rope"]["free_end_connector"]["min_clearance"]), merge_radius=MERGE,
        scene_top=float(BAND["base_z"]) + float(BAND["over_lift"]) + float(BAND["tube_radius"]),
        max_hand_height=float(WS["z_max"]), arm_base_xy=tuple(float(v) for v in TASK["reach"]["base_xy"]),
    )
    cfg = types.SimpleNamespace(
        rope=types.SimpleNamespace(radius=float(BAND["tube_radius"])),
        workspace=types.SimpleNamespace(x=list(WS["x"]), y=list(WS["y"])),
        reach=types.SimpleNamespace(max_hand_dist=float(TASK["reach"]["max_hand_dist"])),
    )
    layout = types.SimpleNamespace(
        task_origin=ORIGIN, cfg=cfg,
        world_z=lambda z: ORIGIN[2] + z, strand_name=lambda i=0: "rope_0", model_params=lambda: params,
    )
    scene = types.SimpleNamespace(layout=layout, connector_xy=lambda e: tuple(world[0 if e == 0 else -1, :2]))
    return scene, world, params


def centred(shape: str, points: np.ndarray, params) -> np.ndarray:
    """Put a local-frame shape where the randomizer would: the middle of its window."""

    if shape == "eight":
        return points
    plan = sequence.plan(sequence.Rope.from_points(points), params)
    heading = float(BAND["curls"]["base_heading_deg"]) if shape == "curls" else 0.0
    window = shapes.centre_window(points, np.array([m.place_xy for m in plan.moves]),
                                  np.array([m.grasp_xy for m in plan.moves]), heading_deg=heading,
                                  workspace_x=tuple(WS["x"]), workspace_y=tuple(WS["y"]), margin=float(WS["margin"]),
                                  arm_base_xy=tuple(TASK["reach"]["base_xy"]), max_hand_dist=float(TASK["reach"]["max_hand_dist"]))
    return shapes.to_task_frame(points, window.at(0.5, 0.5), heading)


def check_planner(gate: Gate) -> None:
    print("\n== 3. planner")
    pinch = types.SimpleNamespace(lift_clearance=float(TASK["pinch"]["lift_clearance"]),
                                  place_clearance=float(TASK["pinch"]["place_clearance"]))
    for shape, changes in (("eight", {}), ("six", {"short_over": 0}), ("six", {"short_over": 1}),
                           ("twist", {"over_end_x1": 0, "over_end_x2": 1}), ("twist", {"over_end_x1": 1, "over_end_x2": 1}),
                           ("curls", {})):
        _scene, _world, params = stub_scene(np.zeros((2, 3)))
        points = centred(shape, shape_points(shape, **changes), params)
        scene, world, params = stub_scene(points)
        state = state_of(world)
        # The same limits `plan_untwist_move` puts on a landing when it plans on
        # the measured rope, or the two need not pick the same one.
        options = sequence.plans(sequence.Rope.from_points(points), replace(
            params,
            landing_box=((float(WS["x"][0]), float(WS["x"][1])), (float(WS["y"][0]), float(WS["y"][1]))),
            max_reach=float(TASK["reach"]["max_hand_dist"]) + RUNTIME_REACH_HEADROOM,
        ))
        tag = f"{shape} {changes}"
        oracle = make_band_untwist_rule("oracle").decide(scene, state, world, pinch_cfg=pinch)
        gate.check(oracle is not None, f"{tag}: oracle has a move")
        if oracle is None:
            continue
        cmd, plan = oracle
        # Any plan of the fewest moves: O|-|O's two orders tie by symmetry, and
        # the last bits of the task-frame points decide which one comes back.
        firsts = [p.moves[0] for p in options]
        gate.check(any(cmd.end == m.end and np.allclose(np.subtract(cmd.place_xy, ORIGIN[:2]), m.place_xy, atol=1e-9)
                       for m in firsts),
                   f"{tag}: oracle = a move model plan's first move (end {cmd.end}, {cmd.planned_moves} planned, "
                   f"{len(firsts)} tied plan(s))")
        targets = [xyz for _label, xyz in cmd.path]
        if cmd.kind == "flip":
            # A flip: FLIP_SEGMENTS points on a half circle of the flip radius,
            # rising over the axis and coming down at the mirror image; the last
            # one is place_down at table height.
            labels = [w.label for w in plan.waypoint_plan.waypoints]
            gate.check(labels[0] == "grasp" and labels[-1] == "place_down" and len(labels) == 1 + FLIP_SEGMENTS,
                       f"{tag}: flip waypoints grasp + {FLIP_SEGMENTS} arc points ({labels})")
            top = max(t[2] for t in targets) - ORIGIN[2]
            rope_r = float(BAND["tube_radius"])
            gate.check(abs(top - (cmd.flip_radius + rope_r)) < 0.02 and abs(targets[-1][2] - ORIGIN[2] - rope_r) < 1e-6,
                       f"{tag}: flip rises to {top * 1000:.0f} mm (radius {cmd.flip_radius * 1000:.0f}) and lands on the table")
            gate.check(abs(np.hypot(cmd.axis[0], cmd.axis[1]) - 1.0) < 1e-9 and cmd.axis[2] == 0.0,
                       f"{tag}: flip axis is a horizontal unit vector")
        else:
            gate.check([w.label for w in plan.waypoint_plan.waypoints] == ["grasp", "carry", "cross", "place"],
                       f"{tag}: waypoints grasp / carry / cross / place")
            # Every lay move carries and crosses over no higher than it lifts,
            # with the hand within CROSS_TAUT x the lifted rope of the lift
            # point unless the ride floor binds, and never so low that the
            # lifted crossing (4 cm past the lift point) would ride under
            # CROSS_RIDE_MIN in the straight-tail picture.
            arc = cmd.crossing_arc + pinch.lift_clearance
            for label, target in (("carry", cmd.carry), ("cross-over", cmd.cross)):
                height = target[2] - ORIGIN[2]
                ride = height * pinch.lift_clearance / (CROSS_TAUT * arc)
                gate.check(target[2] <= cmd.lift_z + 1e-9 and ride >= CROSS_RIDE_MIN - 1e-6,
                           f"{tag}: {label} at {height * 1000:.0f} mm of a {(cmd.lift_z - ORIGIN[2]) * 1000:.0f} mm lift, "
                           f"crossing rides {ride * 1000:.0f} mm")
        if cmd.planned_moves > 1:
            gate.check(cmd.room >= params.min_lay_down - 1e-9,
                       f"{tag}: first move's bowed rope keeps 25 mm from the crossing it leaves "
                       f"(room {cmd.room * 1000:.0f} mm on lines bowed {cmd.bend * 1000:.0f} mm)")
        inside = all(WS["x"][0] <= t[0] - ORIGIN[0] <= WS["x"][1] and WS["y"][0] <= t[1] - ORIGIN[1] <= WS["y"][1]
                     and t[2] - ORIGIN[2] <= float(WS["z_max"]) + 1e-9 for t in targets)
        gate.check(inside, f"{tag}: hand targets in the workspace box, lift {(cmd.lift_z - ORIGIN[2]) * 100:.1f} cm")
        wrong = make_band_untwist_rule("wrong_end").decide(scene, state, world, pinch_cfg=pinch)
        if wrong is not None:
            gate.check(wrong[0].end != cmd.end and not wrong[0].grasped_over_end,
                       f"{tag}: wrong_end grasps the other plug (end {wrong[0].end})")
        else:
            print(f"[--] {tag}: wrong_end has no move (the under side's plug is out of reach under the ceiling)")
    gate.check(make_band_untwist_rule("one_move").budget_cap == 1 and make_band_untwist_rule("oracle").budget_cap is None,
               "one_move caps the budget at 1; oracle leaves it to the plan")

    # Corner c474 ("6", short tail on top, heading 30, centre at the window's far
    # corner): its landing sits 0.4 mm inside the 0.78 m reach limit at spawn.
    # Settled 2 mm off, the oracle must still move (2026-09-11 it did not).
    _scene, _world, params = stub_scene(np.zeros((2, 3)))
    local = shape_points("six", short_over=1, half_angle_deg=55.0, loop_radius=0.030, short_len=0.090, stem_len=0.120)
    moves = [m for p in sequence.plans(sequence.Rope.from_points(local), params) for m in p.moves]
    window = shapes.centre_window(local, np.array([m.place_xy for m in moves]), np.array([m.grasp_xy for m in moves]),
                                  heading_deg=30.0, workspace_x=tuple(WS["x"]), workspace_y=tuple(WS["y"]),
                                  margin=float(WS["margin"]), arm_base_xy=tuple(TASK["reach"]["base_xy"]),
                                  max_hand_dist=float(TASK["reach"]["max_hand_dist"]))
    points = shapes.to_task_frame(local, window.at(1.0, 0.0), 30.0)
    points[:, :2] += np.array([0.002, 0.0])
    scene, world, _params = stub_scene(points)
    decided = make_band_untwist_rule("oracle").decide(scene, state_of(world), world, pinch_cfg=pinch)
    gate.check(decided is not None, "corner c474 settled 2 mm off its spawn: the oracle still has a move (runtime reach headroom)")


def main() -> int:
    gate = Gate()
    check_config(gate)
    check_reading(gate)
    check_planner(gate)
    print()
    print("PASS" if not gate.fails else f"FAIL ({len(gate.fails)})")
    return 0 if not gate.fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

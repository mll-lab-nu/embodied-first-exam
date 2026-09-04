"""Offline gate for `band_untwist` (docx 3.3, open-rope tabletop version).

No Genesis, no GPU: numpy + PyYAML. Three parts, all on the literal values in
`configs/task_configs/band_untwist_topogym_tabletop_v1.yaml` so the two cannot
drift.

1. **Spawn geometry** -- the figure-8 control polyline: the two rope ends are at
   least the gripper's clearance apart, no corner is tighter than three tube
   radii, the over strand really is `over_lift` above the under strand where
   they cross, and the polyline's length matches the analytic tangents-plus-arcs.

2. **Self-crossing reading** -- the open-polyline counter on analytic curves:
   the spawn 8 reads 1 with end 0 on top; the same 8 pressed flat (depth scaled
   by 0.02) still reads 1 -- the docx's anti-shortcut, "hiding the crossing does
   not change the judgement"; a straight rope and a C whose two ends lie side
   by side read 0 -- the C is the case a closed-curve counter gets wrong, since
   its phantom closing segment lands right between the ends; a hand-built
   two-crossing curve reads 2, the wrong-end outcome.

3. **Planner** -- on the spawn polyline with the counter's own reading: the
   oracle grasps the measured over end and the contrast grasps the other; the
   lift clears the rope hanging below the hand; the landing point keeps the
   carried strand as extended as it was, sits at least `place_clearance` from
   the other end AND from the whole strand that stays down, on its far side,
   matches the layout's offline replay of the same rule, and every hand target
   is inside the workspace box and under its ceiling. A staying strand that
   bulges past its plug pushes the landing further round (corner c130).

4. **Variation envelope** -- every corner of the yaml's `variation:` block
   (each uniform axis at both ends, `over_end` at both values, `end_gap`
   derived from `end_frac`): the eight `figure_eight_checks` rows pass, the
   polyline still reads as exactly one crossing, and the measured over end is
   the one the spec asked for. Then three negatives: an open lobe too small for
   the gripper's clearance closes the `end_gap` range, a crossing pushed
   toward the workspace edge fails the footprint row, and a `place_clearance`
   no point on the landing circle can honour makes the landing sweep raise.

    python tests/check_band_untwist_geometry.py

Prints one line per check and exits non-zero if any fails.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.planning.band_untwist_planner import (  # noqa: E402
    make_band_untwist_rule,
    place_beside,
    point_to_polyline,
    stay_strand_xy,
)


def load_by_path(name: str, relative: str):
    """Import a Genesis-free module without running its package's `__init__`
    (`topogym.tasks` and `topogym.verification` both import Genesis)."""

    path = REPO / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fig8 = load_by_path("band_untwist_fig8", "topogym/tasks/entangle/_figure_eight_geometry.py")
verifier = load_by_path("band_untwist_verifier", "topogym/verification/band_untwist_verifier.py")


def config_defaults() -> dict:
    """Literal values from the task config -- no Hydra, no interpolation."""

    task = yaml.safe_load(
        (REPO / "configs/task_configs/band_untwist_topogym_tabletop_v1.yaml").read_text(encoding="utf-8")
    )
    prefabs = yaml.safe_load(
        (REPO / "configs/prefab_configs/topogym_prefabs_v1.yaml").read_text(encoding="utf-8")
    )
    common = yaml.safe_load(
        (REPO / "configs/common_configs/manipulation_space_tabletop_v1.yaml").read_text(encoding="utf-8")
    )
    workspace = common["manipulation_space"]["workspace"]
    eight = task["figure_eight"]
    return {
        "spec": fig8.FigureEightSpec(
            closed_lobe_radius=float(eight["closed_lobe_radius"]),
            open_lobe_radius=float(eight["open_lobe_radius"]),
            end_gap=float(eight["end_gap"]),
            half_angle_deg=float(eight["half_angle_deg"]),
            over_lift=float(eight["over_lift"]),
            base_z=float(eight["base_z"]),
            center=(float(eight["center_x"]), float(eight["center_y"])),
            heading_deg=float(eight["heading_deg"]),
            arc_points_per_quarter=int(eight["arc_points_per_quarter"]),
            lift_ramp=float(eight["lift_ramp"]),
            over_end=int(eight["over_end"]),
        ),
        "radius": float(prefabs["rope_pbd"]["radius"]),
        "tube_radius": float(eight["tube_radius"]),
        "min_clearance": float(task["rope"]["free_end_connector"]["min_clearance"]),
        "end_gap_max_ratio": float(eight["end_gap_max_ratio"]),
        "merge_radius": float(task["success"]["crossing_merge_radius"]),
        "lift_clearance": float(task["pinch"]["lift_clearance"]),
        "place_clearance": float(task["pinch"]["place_clearance"]),
        "workspace": {
            "x": tuple(float(v) for v in workspace["x"]),
            "y": tuple(float(v) for v in workspace["y"]),
            "z": tuple(float(v) for v in workspace["z"]),
        },
        # The task yaml's own copy of the box (the variation hooks only see task cfg).
        "task_workspace": {
            "x": tuple(float(v) for v in task["workspace"]["x"]),
            "y": tuple(float(v) for v in task["workspace"]["y"]),
            "z_max": float(task["workspace"]["z_max"]),
            "margin": float(task["workspace"]["margin"]),
        },
        "variation": list(task["variation"]),
    }


def checks_for(d: dict, spec, place_clearance: float | None = None) -> list:
    """The eight envelope rows, with the same literals the hooks read."""

    ws = d["task_workspace"]
    return fig8.figure_eight_checks(
        spec,
        tube_radius=d["tube_radius"],
        min_clearance=d["min_clearance"],
        end_gap_max_ratio=d["end_gap_max_ratio"],
        workspace_x=ws["x"],
        workspace_y=ws["y"],
        workspace_z_max=ws["z_max"],
        workspace_margin=ws["margin"],
        lift_clearance=d["lift_clearance"],
        place_clearance=d["place_clearance"] if place_clearance is None else place_clearance,
    )


def checks_line(rows) -> str:
    return " ".join(f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
                    for name, measured, limit, ok in rows)


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


class Gate:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, text: str) -> None:
        self.failures += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {text}")


# --- 1. spawn geometry -------------------------------------------------------


def check_geometry(gate: Gate, d: dict) -> np.ndarray:
    spec, radius = d["spec"], d["radius"]
    points = fig8.figure_eight_control_points(spec)
    local, over_mask = fig8.figure_eight_local_points(spec)

    separation = fig8.figure_eight_end_separation(spec)
    gate.check(
        separation >= d["min_clearance"],
        f"rope ends {separation * 1000:.0f}mm apart >= gripper clearance {d['min_clearance'] * 1000:.0f}mm",
    )
    gate.check(
        abs(d["tube_radius"] - radius) < 1e-12,
        f"figure_eight.tube_radius {d['tube_radius']} == prefabs.rope_pbd.radius {radius} (the hooks read the copy)",
    )
    radii = fig8.chord_turn_radii(points)
    # 3D circumradii, so the crossing bump counts (its points are collinear from
    # above); at the default ramp the tightest corner is still on the lobe arcs.
    tightest = float(np.nanmin(radii[np.isfinite(radii)]))
    gate.check(
        tightest >= 3.0 * radius,
        f"tightest control-polygon corner radius {tightest * 1000:.1f}mm >= 3 x tube radius "
        f"{3.0 * radius * 1000:.0f}mm",
    )
    apex = local[over_mask][1]
    under = local[~over_mask]
    under_at_crossing = under[np.argmin(np.linalg.norm(under[:, :2] - apex[None, :2], axis=1))]
    gap = float(apex[2] - under_at_crossing[2])
    gate.check(
        abs(gap - spec.over_lift) < 1e-9 and float(np.linalg.norm(under_at_crossing[:2] - apex[:2])) < 1e-9,
        f"over strand passes {gap * 1000:.1f}mm above the under strand at the crossing "
        f"(over_lift {spec.over_lift * 1000:.1f}mm)",
    )
    arc = fig8.polyline_arc_length(points)
    expected = fig8.figure_eight_expected_arc_length(spec)
    gate.check(
        abs(arc - expected) / expected < 0.02,
        f"control polyline length {arc * 1000:.0f}mm within 2% of analytic {expected * 1000:.0f}mm",
    )
    bottom = float(points[:, 2].min()) - radius
    gate.check(bottom > 0.0, f"tube bottom {bottom * 1000:.1f}mm above the table")
    ws = d["workspace"]
    inside = bool(
        (points[:, 0] >= ws["x"][0]).all()
        and (points[:, 0] <= ws["x"][1]).all()
        and (points[:, 1] >= ws["y"][0]).all()
        and (points[:, 1] <= ws["y"][1]).all()
    )
    gate.check(
        inside,
        f"rope footprint x[{points[:, 0].min():+.3f},{points[:, 0].max():+.3f}] "
        f"y[{points[:, 1].min():+.3f},{points[:, 1].max():+.3f}] inside the workspace",
    )
    tw = d["task_workspace"]
    gate.check(
        tw["x"] == ws["x"] and tw["y"] == ws["y"] and abs(tw["z_max"] - ws["z"][1]) < 1e-12,
        f"task yaml workspace copy x{tw['x']} y{tw['y']} z_max {tw['z_max']} == manipulation_space.workspace",
    )
    return points


# --- 2. self-crossing reading ---------------------------------------------------


def _straight(length: float, z: float) -> np.ndarray:
    return np.column_stack([np.linspace(0.0, length, 40), np.zeros(40), np.full(40, z)])


def _open_c(radius: float, gap_deg: float, z: float) -> np.ndarray:
    """A circle with a small opening: the two ends sit side by side, no crossing."""

    half = np.radians(gap_deg) / 2.0
    angles = np.linspace(np.pi + half, 3.0 * np.pi - half, 60)
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.full(60, z)])


def _two_crossings(z: float) -> np.ndarray:
    """A hand-built open curve that crosses itself exactly twice (checked by
    hand: segment 6 over segment 1, segment 7 over segment 0)."""

    xy = np.array(
        [
            [0.00, 0.00],
            [0.10, 0.00],
            [0.10, 0.05],
            [-0.05, 0.05],
            [-0.05, -0.02],
            [0.15, -0.02],
            [0.15, 0.03],
            [0.02, 0.03],
            [0.02, -0.01],
        ]
    )
    zs = np.full(len(xy), z)
    zs[6:] += 0.012
    return np.column_stack([xy, zs])


def check_reading(gate: Gate, d: dict, spawn_points: np.ndarray) -> None:
    spec, merge = d["spec"], d["merge_radius"]
    z0 = spec.base_z
    dense = densify(spawn_points, 0.006)
    pressed = dense.copy()
    pressed[:, 2] = z0 + (pressed[:, 2] - z0) * 0.02

    cases = [
        ("figure-8 spawn", dense, 1),
        ("figure-8 pressed flat (depth x0.02)", pressed, 1),
        ("straight rope", _straight(0.5, z0), 0),
        ("C with ends side by side (no phantom closing segment)", _open_c(0.06, 20.0, z0), 0),
        ("two crossings (wrong-end outcome)", densify(_two_crossings(z0), 0.006), 2),
    ]
    for label, polyline, expected in cases:
        hits = verifier.open_self_crossings(polyline, merge_radius=merge)
        detail = ", ".join(
            f"over_end={h.over_end} over_at={h.over_at:.2f} gap={h.z_gap * 1000:.1f}mm sign={h.sign:+d}"
            for h in hits
        )
        gate.check(len(hits) == expected, f"{label}: reads {len(hits)} (expected {expected}) {detail}")
        if label == "figure-8 spawn" and hits:
            gate.check(
                hits[0].over_end == spec.over_end,
                f"figure-8 spawn: measured over end {hits[0].over_end} == spec's {spec.over_end}",
            )

    # The mirror axis: same two end positions, the other strand on top.
    mirrored = replace(spec, over_end=1 - spec.over_end)
    m_points = fig8.figure_eight_control_points(mirrored)
    m_hits = verifier.open_self_crossings(densify(m_points, 0.006), merge_radius=merge)
    gate.check(
        len(m_hits) == 1 and m_hits[0].over_end == mirrored.over_end,
        f"figure-8 mirrored (over_end={mirrored.over_end}): reads {len(m_hits)}, measured over end "
        f"{m_hits[0].over_end if m_hits else '-'}",
    )
    gate.check(
        np.allclose(m_points[[0, -1], :2], spawn_points[[0, -1], :2], atol=1e-9),
        "figure-8 mirrored: both rope ends sit exactly where the unmirrored ends sit",
    )


# --- 3. planner ---------------------------------------------------------------


@dataclass
class _Rope:
    radius: float


@dataclass
class _Cfg:
    rope: _Rope


@dataclass
class _Layout:
    cfg: _Cfg

    def world_z(self, z):
        return float(z)

    def strand_name(self, index=0):
        return f"rope_{index}"


@dataclass
class _Scene:
    layout: _Layout
    ends: dict

    def connector_xy(self, end):
        return self.ends[int(end)]


@dataclass
class _State:
    crossings: tuple

    @property
    def crossing_count(self):
        return len(self.crossings)


class _Pinch:
    def __init__(self, lift_clearance, place_clearance):
        self.lift_clearance = lift_clearance
        self.place_clearance = place_clearance


def check_planner(gate: Gate, d: dict, spawn_points: np.ndarray) -> None:
    dense = densify(spawn_points, 0.006)
    hits = verifier.open_self_crossings(dense, merge_radius=d["merge_radius"])
    if len(hits) != 1:
        gate.check(False, "planner: spawn does not read as one crossing; skipping")
        return
    state = _State(crossings=hits)
    scene = _Scene(
        layout=_Layout(cfg=_Cfg(rope=_Rope(radius=d["radius"]))),
        ends={0: tuple(dense[0, :2]), 1: tuple(dense[-1, :2])},
    )
    pinch = _Pinch(d["lift_clearance"], d["place_clearance"])
    ws = d["workspace"]

    picks = {}
    for mode in ("oracle", "wrong_end"):
        planned = make_band_untwist_rule(mode).decide(scene, state, dense, pinch_cfg=pinch)
        if planned is None:
            gate.check(False, f"{mode}: planner returned None on the spawn state")
            continue
        command, plan = planned
        picks[mode] = command.end
        crossing_xy = np.asarray(command.crossing_xy)
        grasp = np.asarray(command.grasp_xy)
        other = np.asarray(scene.ends[command.other_end])
        place = np.asarray(command.place_xy)
        lift = command.lift_z
        gate.check(
            lift >= command.crossing_arc + d["lift_clearance"],
            f"{mode}: lift {lift * 1000:.0f}mm clears the {command.crossing_arc * 1000:.0f}mm of rope "
            f"from the crossing to end {command.end}",
        )
        gate.check(
            lift <= ws["z"][1],
            f"{mode}: lift {lift * 1000:.0f}mm under the {ws['z'][1] * 1000:.0f}mm workspace ceiling",
        )
        r_place = float(np.linalg.norm(place - crossing_xy))
        r_other = float(np.linalg.norm(other - crossing_xy))
        gate.check(
            abs(r_place - r_other) < 1e-9,
            f"{mode}: landing point {r_place * 1000:.1f}mm from the crossing == other end's "
            f"{r_other * 1000:.1f}mm (carried strand neither taut nor slack)",
        )
        chord = float(np.linalg.norm(place - other))
        gate.check(
            chord >= d["place_clearance"] - 1e-9,
            f"{mode}: landing point {chord * 1000:.1f}mm from the other end (place_clearance "
            f"{d['place_clearance'] * 1000:.0f}mm)",
        )
        stay_at = hits[0].under_at if command.grasped_over_end else hits[0].over_at
        stay = stay_strand_xy(dense, other_end=command.other_end, stay_at=stay_at)
        stay_clear = point_to_polyline(place, stay)
        gate.check(
            stay_clear >= d["place_clearance"] - 1e-9,
            f"{mode}: landing point {stay_clear * 1000:.1f}mm from the strand that stays down "
            f"({len(stay)} vertices, end {command.other_end} to the crossing)",
        )
        if mode == "oracle":
            replay, _stay, _contact = fig8.predicted_place(
                d["spec"], place_clearance=d["place_clearance"], lift_clearance=d["lift_clearance"]
            )
            gap = float(np.linalg.norm(replay - place))
            gate.check(
                gap < 0.005,
                f"{mode}: layout's offline replay lands {gap * 1000:.1f}mm from the planner's point "
                "(same place_beside, control polygon vs dense polyline)",
            )
        gate.check(
            float(np.linalg.norm(place - grasp)) > float(np.linalg.norm(other - grasp)),
            f"{mode}: landing point is on the far side of the other end from the grasp",
        )
        for label, xy in (("grasp", grasp), ("place", place)):
            inside = ws["x"][0] <= xy[0] <= ws["x"][1] and ws["y"][0] <= xy[1] <= ws["y"][1]
            gate.check(inside, f"{mode}: {label} ({xy[0]:+.3f},{xy[1]:+.3f}) inside the workspace")
        gate.check(
            plan.waypoint_plan.labels() == ("grasp", "carry", "cross", "place"),
            f"{mode}: waypoint labels {plan.waypoint_plan.labels()}",
        )

    if len(picks) == 2:
        gate.check(
            picks["oracle"] == hits[0].over_end and picks["wrong_end"] == 1 - hits[0].over_end,
            f"contrast pair grasps different ends: oracle=end{picks['oracle']} "
            f"wrong_end=end{picks['wrong_end']} (measured over end {hits[0].over_end})",
        )

    # `place_beside` picks the far side regardless of which end is grasped; with
    # the staying strand a straight line to the crossing the chord rule holds.
    straight = np.array([[0.04, -0.1], [0.0, 0.0]])
    far = place_beside((0.0, 0.0), (-0.04, -0.1), (0.04, -0.1), straight, clearance=0.035)
    gate.check(far[0] > 0.04, f"place_beside lands past the other end: x={far[0]:+.3f}")
    chord = float(np.linalg.norm(np.asarray(far) - np.array([0.04, -0.1])))
    gate.check(
        0.035 - 1e-6 <= chord <= 0.037,
        f"place_beside straight strand: chord {chord * 1000:.1f}mm, the 35mm rule plus at most one sweep step",
    )
    # A staying strand that bulges out past its plug pushes the landing further round.
    bulged = np.array([[0.04, -0.1], [0.09, -0.08], [0.06, -0.03], [0.0, 0.0]])
    pushed = place_beside((0.0, 0.0), (-0.04, -0.1), (0.04, -0.1), bulged, clearance=0.035)
    gate.check(
        point_to_polyline(pushed, bulged) >= 0.035 - 1e-9
        and float(np.linalg.norm(np.asarray(pushed) - np.array([0.04, -0.1]))) > 0.035 + 1e-6,
        f"place_beside bulging strand: landing pushed to {np.asarray(pushed).round(3)}, "
        f"{point_to_polyline(pushed, bulged) * 1000:.1f}mm clear of the strand",
    )

    # Refuses on anything but exactly one crossing.
    for count, label in ((0, "solved"), (2, "two crossings")):
        fake = _State(crossings=tuple(hits) * count)
        planned = make_band_untwist_rule("oracle").decide(scene, fake, dense, pinch_cfg=pinch)
        gate.check(planned is None, f"planner refuses to move when {label}: {planned is None}")


# --- 4. variation envelope -------------------------------------------------------


def envelope(d: dict) -> dict:
    """``{leaf: [values to visit]}`` straight from the yaml's variation block."""

    axes = {}
    for entry in d["variation"]:
        path = entry.get("path", "")
        leaf = path.split(".")[-1]
        if entry["kind"] == "uniform":
            axes[leaf] = [float(entry["lo"]), float(entry["hi"])]
        elif entry["kind"] == "choice":
            axes[leaf] = list(entry["values"])
    return axes


def spec_at(d: dict, **leaves) -> object:
    """A spec with the sampled leaves written and ``end_gap`` derived, as the hooks do."""

    base = d["spec"]
    end_frac = leaves.pop("end_frac", 0.5)
    cx = leaves.pop("center_x", base.center[0])
    cy = leaves.pop("center_y", base.center[1])
    r_o = leaves.get("open_lobe_radius", base.open_lobe_radius)
    end_gap = fig8.end_gap_from_frac(r_o, end_frac, d["min_clearance"], d["end_gap_max_ratio"])
    return replace(base, center=(cx, cy), end_gap=end_gap, **leaves)


def check_envelope(gate: Gate, d: dict) -> None:
    axes = envelope(d)
    want = {"over_end", "heading_deg", "center_x", "center_y", "half_angle_deg",
            "closed_lobe_radius", "open_lobe_radius", "end_frac"}
    gate.check(set(axes) == want, f"variation block declares {sorted(axes)}")
    names = list(axes)
    worst: dict[str, tuple[float, str]] = {}
    bad_corners, bad_reads, n = [], [], 0
    for combo in itertools.product(*(axes[k] for k in names)):
        leaves = dict(zip(names, combo))
        label = " ".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in leaves.items())
        spec = spec_at(d, **leaves)
        rows = checks_for(d, spec)
        n += 1
        for name, measured, limit, ok in rows:
            margin = (measured - limit) if name not in ("end_gap_ratio", "lift_height") else (limit - measured)
            if name not in worst or margin < worst[name][0]:
                worst[name] = (margin, f"{measured:+.4f}/{limit:+.4f} @ {label}")
        if not all(ok for *_, ok in rows):
            bad_corners.append(f"{label}: {checks_line(rows)}")
        dense = densify(fig8.figure_eight_control_points(spec), 0.006)
        hits = verifier.open_self_crossings(dense, merge_radius=d["merge_radius"])
        if len(hits) != 1 or hits[0].over_end != spec.over_end:
            bad_reads.append(f"{label}: reads {len(hits)} over_end={[h.over_end for h in hits]}")
    for name, (margin, text) in worst.items():
        print(f"     tightest {name:<16} margin {margin:+.4f}  ({text})")
    gate.check(not bad_corners, f"{n} envelope corners: all eight checks pass" + (f"; failing: {bad_corners[:3]}" if bad_corners else ""))
    gate.check(not bad_reads, f"{n} envelope corners: exactly one crossing, measured over end == spec" + (f"; failing: {bad_reads[:3]}" if bad_reads else ""))

    # Negatives: the derived range must close, and the footprint row must reject.
    try:
        fig8.end_gap_from_frac(0.036, 0.5, d["min_clearance"], d["end_gap_max_ratio"])
    except ValueError as exc:
        gate.check(True, f"open_lobe_radius 0.036 closes the end_gap range: {str(exc)[:70]}")
    else:
        gate.check(False, "open_lobe_radius 0.036 was accepted (end_gap range should be empty)")
    rows = checks_for(d, spec_at(d, center_x=0.16))
    row = next(r for r in rows if r[0] == "footprint")
    gate.check(not row[3], f"center_x=0.16 fails the footprint row: {row[1]:+.4f} vs {row[2]:+.4f}")
    # A clearance no point on the landing circle can honour: the sweep raises
    # in the planner, and the checks row reports it as a failure, not a crash.
    try:
        fig8.predicted_place(d["spec"], place_clearance=0.30, lift_clearance=d["lift_clearance"])
    except ValueError as exc:
        gate.check(True, f"place_clearance 0.30 makes the landing sweep raise: {str(exc)[:60]}")
    else:
        gate.check(False, "place_clearance 0.30 was accepted (no landing point can be that clear)")
    row = next(r for r in checks_for(d, d["spec"], place_clearance=0.30) if r[0] == "place_clearance")
    gate.check(not row[3], f"place_clearance 0.30 fails its row: {row[1]:+.4f} vs {row[2]:+.4f}")


def main() -> int:
    d = config_defaults()
    gate = Gate()
    print("-- spawn geometry")
    points = check_geometry(gate, d)
    print(f"   checks: {checks_line(checks_for(d, d['spec']))}")
    print("-- self-crossing reading")
    check_reading(gate, d, points)
    print("-- planner")
    check_planner(gate, d, points)
    print("-- variation envelope")
    check_envelope(gate, d)
    print(f"\n{'PASS' if gate.failures == 0 else f'{gate.failures} FAILED'}")
    return 1 if gate.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

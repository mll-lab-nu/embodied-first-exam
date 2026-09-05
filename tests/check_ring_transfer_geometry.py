"""Offline gate for the ring_transfer layout (docx 2.6): posts, loop, the carry
oracle's feasibility rows and the variation envelope -- everything that can be
wrong before a GPU is spent.

Runs the REAL geometry module (`topogym/tasks/routing/_ring_transfer_geometry.py`)
and the REAL `RingTransferLayout` against the REAL task config, so an edit to
either is caught here.

What it proves:
  - the periodic tube is watertight, genus one, and closes at self-linking 0
    (a band spawned at Lk = +-1 looks identical and cannot be flipped flat);
  - the IPC barrier stays inside the tube's own self-contact clearance;
  - the carry oracle's fifteen `RingTransferLayout.checks()` rows pass on the
    baseline: loop clears the post, spawn loop clears the target, head
    overhang retains the loop, pinch on the straight, palm box clear of both
    heads at the grasp / over the anchor / at the drop, fingertips over the
    anchor's head, lift_low below the hang depth, bottom U on the shaft, U
    wide enough for the target, hanging strands clear of the anchor's head,
    hands and spawn loop inside the workspace, hand reach;
  - transfer route (reported, hard-gated only when it is the run config's
    default motion): the stretch trapezoid admits post B with two negative
    controls, the far-cap path keeps the strands off B until the descent, the
    loop stays taut through the carry, carry height above its floor, every
    held point in the workspace, hook grasps a gripper's width from both posts;
  - variation envelope: the baseline yaml restores the hand-written layout
    (posts, long axis, pinch side / point, three carry heights); a heading of
    30 deg is the baseline rotated about the pair's midpoint; `ring.on_post: B`
    reverses the crossings; all 256 corners of the yaml's `variation:` block
    derive and pass every row (tightest margin per row printed); three
    negative controls are rejected.

    python tests/check_ring_transfer_geometry.py

Needs the project venv: the geometry module imports `topogym.world.closed_band`,
whose package init imports Genesis (CPU import is enough; no GPU is used).
"""

from __future__ import annotations

import itertools
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.tasks.routing import _ring_transfer_geometry as geo  # noqa: E402
from topogym.tasks.routing.ring_transfer import RingTransferLayout, derive_task_cfg  # noqa: E402
from topogym.world.rope import check_self_contact_clearance  # noqa: E402

TASK_CONFIG = REPO / "configs/task_configs/ring_transfer_topogym_tabletop_v1.yaml"
RUN_CONFIG = REPO / "configs/run_configs/ring_transfer.yaml"
PREFABS = REPO / "configs/prefab_configs/topogym_prefabs_v1.yaml"
COMMON = REPO / "configs/common_configs/manipulation_space_tabletop_v1.yaml"

# The stretch ratio a StableNeoHookean tube at E=1e5 is trusted to; the spike
# reads the real number. Above this the follow band is asked to hold more than
# a newton and no run has measured whether it can.
MAX_STRETCH_RATIO = 1.20
# Clearance the strands keep from post B's shaft while they are not meant to
# touch it (swing, rise, carry), on top of r_post + r_tube.
STRAND_CLEARANCE = 0.005
WORKSPACE_MARGIN = 0.02


def load_task_cfg():
    root = OmegaConf.create(
        {
            "task": OmegaConf.load(TASK_CONFIG),
            "prefabs": OmegaConf.load(PREFABS),
            "common": OmegaConf.load(COMMON),
        }
    )
    OmegaConf.resolve(root)
    return root.task, root.common


def edge_multiplicities(faces: np.ndarray) -> Counter:
    edges: Counter = Counter()
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(min(u, v), max(u, v))] += 1
    return Counter(edges.values())


def main() -> int:
    task, common = load_task_cfg()
    failures: list[str] = []
    # The transfer route (stretch trapezoid over the anchor) only works for close
    # posts; it is gated hard only when it is the demo's default motion, and
    # otherwise reported as available / not available.
    default_motion = str(OmegaConf.load(RUN_CONFIG).motion)
    transfer_failures: list[str] = []
    transfer_fail = transfer_failures if default_motion != "transfer" else failures

    layout = RingTransferLayout(task)
    posts, ring, anchor, target, spawn = layout.posts, layout.ring, layout.anchor, layout.target, layout.spawn
    d_hat = float(task.rope.fem.contact_d_hat)
    frames, vertices, faces = geo.spawn_mesh(ring, spawn)
    print(
        f"loop           perimeter {frames.perimeter:.4f} m, loop radius {ring.loop_radius * 1000:.1f} mm, "
        f"{len(spawn)} rings x {ring.radial_segments}, reach {geo.loop_reach(spawn, ring, anchor) * 1000:.1f} mm "
        f"from {anchor.name}, far cap at {np.round(geo.far_cap_point(spawn, ring, anchor)[:2] * 1000, 1).tolist()} mm"
    )

    # --- skin ------------------------------------------------------------------
    multiplicity = edge_multiplicities(faces)
    euler = len(vertices) - sum(multiplicity.values()) + len(faces)
    print()
    print(
        f"skin           edge multiplicity {dict(multiplicity)}, V-E+F = {euler} (torus: 0), "
        f"Lk = {frames.self_linking} at Tw {frames.twist_turns:+.4f} turns (k = {frames.closure_turns})"
    )
    if set(multiplicity) != {2} or euler != 0:
        failures.append("periodic tube is not a watertight torus")
    if frames.self_linking != 0:
        failures.append(f"self-linking {frames.self_linking}, want 0")
    check_self_contact_clearance(
        radius=ring.tube_radius,
        radial_segments=ring.radial_segments,
        ring_spacing=ring.segment_length,
        contact_d_hat=d_hat,
    )

    # --- stretch triangle ------------------------------------------------------
    half = 0.5 * float(task.grasp.spread)
    landing = geo.landing_point(ring=ring, anchor=anchor, target=target, transfer_cfg=task.transfer)
    need = geo.min_strand_separation(target, ring, d_hat)
    have = geo.strand_separation_at(
        ring=ring, anchor=anchor, landing_xy=landing, held_half_width=half, query_xy=target.center
    )
    print()
    print(
        f"stretch        landing {np.round(landing * 1000, 1).tolist()} mm, fingers spread {2 * half * 1000:.0f} mm; "
        f"strand separation at {target.name} {have * 1000:.1f} mm vs needed {need * 1000:.1f} mm "
        f"{'ok' if have >= need else 'FAIL'}"
    )
    if have < need:
        transfer_fail.append("stretch trapezoid does not admit the target post")
    pinched = geo.strand_separation_at(
        ring=ring, anchor=anchor, landing_xy=landing, held_half_width=ring.tube_radius, query_xy=target.center
    )
    print(
        f"               negative control, pinched cap: {pinched * 1000:.1f} vs {need * 1000:.1f} mm "
        f"{'rejected as expected' if pinched < need else 'NOT rejected'}"
    )
    if pinched >= need:
        failures.append("negative control: a pinched cap should not admit the target post")
    # A post 5 mm too fat for this trapezoid must be rejected; the radius is derived
    # from the layout so the control keeps biting when the layout is scaled.
    fat = replace(target, radius=0.5 * have - 2.0 * ring.tube_radius - d_hat + 0.005)
    fat_have = geo.strand_separation_at(
        ring=ring, anchor=anchor, landing_xy=landing, held_half_width=half, query_xy=fat.center
    )
    fat_need = geo.min_strand_separation(fat, ring, d_hat)
    print(
        f"               negative control, {fat.radius * 1000:.1f} mm post: {fat_have * 1000:.1f} vs {fat_need * 1000:.1f} mm "
        f"{'rejected as expected' if fat_have < fat_need else 'NOT rejected'}"
    )
    if fat_have >= fat_need:
        failures.append("negative control: an over-size post should not fit the trapezoid")

    floor = geo.carry_height_floor(
        anchor=anchor,
        crossed=target,
        landing_xy=landing,
        tube_radius=ring.tube_radius,
        margin=float(task.transfer.carry_margin),
    )
    carry_z = float(task.transfer.carry_z)
    print(f"carry height   carry_z {carry_z * 1000:.1f} mm >= floor {floor * 1000:.1f} mm  {'ok' if carry_z >= floor else 'FAIL'}")
    if carry_z < floor:
        transfer_fail.append("carry_z below carry_height_floor")

    # --- the far-cap path, sampled --------------------------------------------
    path = geo.far_cap_path(ring=ring, anchor=anchor, target=target, spawn_line=spawn, transfer_cfg=task.transfer)
    axis = geo.post_axis_segment(target)
    keep_off = target.radius + ring.tube_radius + STRAND_CLEARANCE
    workspace = common.manipulation_space.workspace
    print()
    print("far-cap path   (strand-to-B-axis distance per leg, min over samples)")
    worst_stretch = 0.0
    slack_legs: list[str] = []
    previous = None
    for label, point in path:
        if previous is None:
            previous = point
            continue
        samples = [previous + alpha * (point - previous) for alpha in np.linspace(0.0, 1.0, 12)]
        # The swing keeps the spawn reach, so nothing stretches there; the
        # stretch model is only meaningful once the cap is pulled past its reach.
        leg_min = np.inf
        for held in samples:
            for start, end in geo.strand_segments(ring=ring, anchor=anchor, held_xyz=held, held_half_width=half):
                leg_min = min(leg_min, geo.segment_distance(start, end, *axis))
            ratio = geo.stretched_length(ring=ring, anchor=anchor, held_xyz=held, held_half_width=half) / ring.perimeter
            if label in ("rise", "carry"):
                worst_stretch = max(worst_stretch, ratio)
            # The rise starts unstretched by construction (the swing keeps the
            # spawn reach) and happens where B is tens of mm clear of the
            # strands; tautness only matters where the strands sweep over B.
            if label == "carry" and ratio < 1.0 and label not in slack_legs:
                    slack_legs.append(label)
        descending = label == "descend"
        # On the descent the strands pass the head on the way down, so the head
        # radius is what they must clear; before that they must stay off the shaft.
        want = (target.head_radius + ring.tube_radius) if descending else keep_off
        ok = leg_min >= want
        print(
            f"  {label:8s} -> {np.round(point * 1000, 1).tolist()} mm: {leg_min * 1000:.1f} mm "
            f"(want >= {want * 1000:.1f}) {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            transfer_fail.append(f"strands touch post {target.name} during leg {label!r}")
        for held in (previous, point):
            if not (
                float(workspace.x[0]) + WORKSPACE_MARGIN <= held[0] <= float(workspace.x[1]) - WORKSPACE_MARGIN
                and float(workspace.y[0]) + WORKSPACE_MARGIN <= held[1] <= float(workspace.y[1]) - WORKSPACE_MARGIN
                and held[2] <= float(workspace.z[1])
            ):
                transfer_fail.append(f"held point {np.round(held, 3).tolist()} leaves the workspace at leg {label!r}")
        previous = point
    print(f"stretch ratio  worst over rise+carry {worst_stretch:.3f} (cap {MAX_STRETCH_RATIO}); slack legs: {slack_legs or 'none'}")
    if worst_stretch > MAX_STRETCH_RATIO:
        transfer_fail.append(f"stretch ratio {worst_stretch:.3f} exceeds {MAX_STRETCH_RATIO}")
    if slack_legs:
        transfer_fail.append(f"loop goes slack during {slack_legs}: strand sag over post B is not modelled")
    at_table = geo.stretched_length(
        ring=ring, anchor=anchor, held_xyz=path[-1][1], held_half_width=half
    ) / ring.perimeter
    rest = geo.rest_length_around([anchor, target], ring) / ring.perimeter
    print(
        f"               at the landing point {at_table:.3f}; taut around both posts would need "
        f"{rest:.3f} of the perimeter -> the finished loop is {'slack' if rest < 1.0 else 'stretched'}"
    )

    # --- grasps ----------------------------------------------------------------
    clearance = float(task.grasp.post_clearance)
    left, right = geo.hook_points(spawn, ring, anchor, float(task.grasp.spread))
    near = geo.near_cap_point(spawn, ring, anchor)
    print()
    print("grasp points")
    print(
        f"  hook bands at {np.round(left[:2] * 1000, 1).tolist()} / {np.round(right[:2] * 1000, 1).tolist()} mm, "
        f"{np.linalg.norm(left - right) * 1000:.1f} mm apart (band radius {float(task.grasp.band_radius) * 1000:.0f}, must not overlap)"
    )
    if np.linalg.norm(left - right) <= 2.0 * float(task.grasp.band_radius):
        failures.append("hook bands overlap")
    for name, point, gated in (("hook L", left, True), ("hook R", right, True), ("near cap", near, False)):
        for post in posts.values():
            gap = float(geo.xy_distance_to_post(point, post)[0]) - post.radius
            verdict = ("ok" if gap >= clearance else "FAIL") if gated else "(reported only)"
            print(f"  {name:8s} to {post.name} surface {gap * 1000:.1f} mm (want >= {clearance * 1000:.0f}) {verdict}")
            if gated and gap < clearance:
                failures.append(f"{name} grasp too close to post {post.name}")

    # --- carry oracle: the Layout's rows ----------------------------------------
    pinch = layout.pinch_point()
    depth = geo.hang_depth(ring, task.carry)
    carry = layout.carry_path()
    print()
    print(
        f"carry          pinch at {np.round(pinch[:2] * 1000, 1).tolist()} mm (side {layout.pinch_side:+.0f}, along {layout.pinch_along * 1000:.1f} mm), "
        f"long axis {np.round(layout.long_axis, 3).tolist()}; hang depth {depth * 1000:.0f} mm "
        f"({'measured' if getattr(task.carry, 'hang_depth', None) is not None else 'estimate'}); "
        f"lift_low {layout.lift_low_z * 1000:.0f} / hang_bottom {layout.hang_bottom_z * 1000:.0f} / drop {layout.drop_z * 1000:.0f} mm; "
        f"clear fingertips at {carry[3][1][2] * 1000:.0f} mm (workspace z max {float(workspace.z[1]) * 1000:.0f})"
    )
    rows = layout.checks()
    print(f"checks         {len(rows)} rows (measured / limit)")
    for name, measured, limit, ok in rows:
        print(f"  {name:34s} {measured:+.4f} / {limit:+.4f}  {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"layout check {name} failed: {measured:+.4f} against {limit:+.4f}")
    if len(rows) != 15:
        failures.append(f"expected 15 layout rows, got {len(rows)}")

    lift_z = anchor.top_z + ring.tube_radius + float(task.transfer.lift_margin)
    print(f"lift-off       near band to {lift_z * 1000:.1f} mm (head top {anchor.top_z * 1000:.1f}) then +{float(task.transfer.shift) * 1000:.0f} mm toward {target.name}")
    for post in posts.values():
        overhang = post.head_radius - post.radius
        print(f"  head {post.name}: overhang {overhang * 1000:.1f} mm vs tube diameter {2 * ring.tube_radius * 1000:.0f} (want >=) {'ok' if overhang >= 2 * ring.tube_radius else 'FAIL'}")
        if overhang < 2 * ring.tube_radius:
            failures.append(f"post {post.name} head overhang smaller than the tube diameter: it will not retain the loop")

    print()
    print("variation envelope")
    failures.extend(_check_variation_envelope(task))

    print()
    print(
        f"transfer route  {'available' if not transfer_failures else 'NOT available for this layout'}"
        f" (default motion: {default_motion})"
        + ("".join(f"\n  - {item}" for item in transfer_failures) if transfer_failures else "")
    )
    print()
    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("PASS")
    return 0


def _corner_layout(task, values: dict):
    """A copy of the task config with `values` (dotted path -> value) applied,
    the yaml's derivation hook run, and the Layout built on it."""

    cfg = OmegaConf.create(OmegaConf.to_container(task, resolve=True))
    for path, value in values.items():
        OmegaConf.update(cfg, path, value, merge=False)
    derive_task_cfg(cfg)
    return cfg, RingTransferLayout(cfg)


def _rotate_about(points, center_xy, angle_deg):
    pts = np.asarray(points, dtype=float).copy()
    c, s = np.cos(np.radians(angle_deg)), np.sin(np.radians(angle_deg))
    rel = pts[:, :2] - np.asarray(center_xy, dtype=float)[None, :]
    pts[:, 0] = center_xy[0] + c * rel[:, 0] - s * rel[:, 1]
    pts[:, 1] = center_xy[1] + s * rel[:, 0] + c * rel[:, 1]
    return pts


def _check_variation_envelope(task) -> list[str]:
    failures: list[str] = []
    base = RingTransferLayout(task)

    # 1. The baseline yaml (randomize off) restores the hand-written 2026-08-25/26 layout.
    want = {
        "A": (-0.100, 0.000), "B": (0.120, 0.000), "long_axis": (0.0, -1.0), "pinch_side": -1.0,
        "pinch_along": 0.070, "lift_low_z": 0.120, "hang_bottom_z": 0.040, "drop_z": 0.040,
    }
    got = {
        "A": tuple(base.posts["A"].center), "B": tuple(base.posts["B"].center), "long_axis": tuple(base.long_axis),
        "pinch_side": base.pinch_side, "pinch_along": base.pinch_along, "lift_low_z": base.lift_low_z,
        "hang_bottom_z": base.hang_bottom_z, "drop_z": base.drop_z,
    }
    for key, value in want.items():
        ok = np.allclose(got[key], value, atol=1e-6)
        print(f"  baseline {key:14s} {np.round(got[key], 4).tolist() if isinstance(got[key], tuple) else round(got[key], 4)} (want {value}) {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"baseline yaml does not restore {key}: {got[key]} vs {value}")

    # 2. heading 30 deg = the baseline rotated about the pair's midpoint (posts,
    #    spawn loop, pinch point and carry path all turn together).
    mid = (float(task.pair.mid_x), float(task.pair.mid_y))
    cfg30 = OmegaConf.create(OmegaConf.to_container(task, resolve=True))
    cfg30.pair.heading_deg = 30.0
    turned = RingTransferLayout(cfg30, pair_mid=mid)
    same = (
        np.allclose(_rotate_about(np.vstack([base.posts["A"].center, base.posts["B"].center]), mid, 30.0),
                    np.vstack([turned.posts["A"].center, turned.posts["B"].center]), atol=1e-9)
        and np.allclose(_rotate_about(base.spawn, mid, 30.0), turned.spawn, atol=1e-6)
        and np.allclose(_rotate_about(np.asarray([p for _, p in base.carry_path()]), mid, 30.0),
                        np.asarray([p for _, p in turned.carry_path()]), atol=1e-6)
        and turned.pinch_side == base.pinch_side
    )
    print(f"  heading 30 deg: posts, spawn loop and carry path are the baseline rotated about the midpoint {'ok' if same else 'FAIL'}")
    if not same:
        failures.append("a heading of 30 deg is not the baseline layout rotated about the pair's midpoint")

    # 3. ring.on_post = B: the goal is A, the crossings reverse, the pinch side flips.
    cfg_b, on_b = _corner_layout(task, {"ring.on_post": "B"})
    reversed_ok = (
        str(cfg_b.goal.on_post) == "A" and on_b.crossings() == [("A", "on"), ("B", "off")]
        and on_b.pinch_side == -base.pinch_side and on_b.instruction() == "Move the elastic loop from post B onto post A."
    )
    print(f"  on_post B: goal {cfg_b.goal.on_post}, crossings {on_b.crossings()}, pinch side {on_b.pinch_side:+.0f}, instruction {on_b.instruction()!r} {'ok' if reversed_ok else 'FAIL'}")
    if not reversed_ok:
        failures.append("ring.on_post=B does not reverse the transfer")

    # 4. Every corner of the yaml's variation block derives and passes every row.
    axes = []
    for directive in task.variation:
        kind = str(directive.kind)
        if kind == "uniform":
            axes.append((str(directive.path), [float(directive.lo), float(directive.hi)]))
        elif kind == "choice":
            axes.append((str(directive.path), [v for v in directive["values"]]))
    corners = list(itertools.product(*[values for _, values in axes]))
    tight: dict[str, tuple[float, tuple]] = {}
    rejected, bad = 0, 0
    for corner in corners:
        values = {path: value for (path, _), value in zip(axes, corner)}
        try:
            _, layout = _corner_layout(task, values)
        except ValueError as exc:
            rejected += 1
            print(f"  corner {values} rejected: {exc}")
            continue
        rows = layout.checks()
        for name, measured, limit, ok in rows:
            margin = (limit - measured) if name == "hand_reach" else (measured - limit)
            if name not in tight or margin < tight[name][0]:
                tight[name] = (margin, corner)
            if not ok:
                bad += 1
                print(f"  corner {values}: {name} {measured:+.4f} against {limit:+.4f} FAIL")
    print(f"  {len(corners)} corners: {rejected} rejected, {bad} failing rows; tightest margin per row:")
    for name, (margin, corner) in tight.items():
        print(f"    {name:34s} {margin * 1000:+7.1f} mm at {corner}")
    if len(corners) != 256:
        failures.append(f"expected 256 corners from the yaml, got {len(corners)}")
    if rejected or bad:
        failures.append(f"variation envelope: {rejected} corners rejected, {bad} failing rows")

    # 5. Negative controls: a taller post, a fatter post, a pair pushed past the
    #    workspace must each be rejected by the named row.
    for label, values, row in (
        ("post height 0.130", {"post_shape.height": 0.130}, "lift_low_below_hang"),
        ("post radius 0.050", {"post_shape.radius": 0.050}, "loop_clears_post"),
        ("spacing 0.280 at mid_x 0.040", {"pair.spacing": 0.280, "pair.mid_x": 0.040}, "carry_in_workspace"),
    ):
        cfg = OmegaConf.create(OmegaConf.to_container(task, resolve=True))
        for path, value in values.items():
            OmegaConf.update(cfg, path, value, merge=False)
        # No derivation: the literal midpoint is the point of the third control.
        for name, center in geo.pair_centers(cfg.pair).items():
            cfg.posts[name].x, cfg.posts[name].y = float(center[0]), float(center[1])
        rows = {name: ok for name, _, _, ok in RingTransferLayout(cfg).checks()}
        caught = not rows[row]
        print(f"  negative control {label}: {row} {'rejected as expected' if caught else 'NOT rejected'}")
        if not caught:
            failures.append(f"negative control {label} should fail {row}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())

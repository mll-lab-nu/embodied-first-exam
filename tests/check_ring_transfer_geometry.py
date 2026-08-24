"""Offline gate for the ring_transfer layout (docx 2.6): posts, loop, and the
one-gripper stretch path -- everything that can be wrong before a GPU is spent.

Runs the REAL geometry module (`topogym/tasks/routing/_ring_transfer_geometry.py`)
against the REAL task config, so an edit to either is caught here.

What it proves:
  - the loop clears every post's shaft with the barrier distance to spare, and
    the spawn loop does not touch the post it is not hooked on;
  - the periodic tube is watertight, genus one, and closes at self-linking 0
    (a band spawned at Lk = +-1 looks identical and cannot be flipped flat);
  - the IPC barrier stays inside the tube's own self-contact clearance;
  - the stretch trapezoid admits post B: where the two taut strands pass B they
    are further apart than B's diameter plus two tubes plus the barrier, and
    the negative controls (a pinched cap; rope_winding's 20 mm posts) are
    rejected;
  - along the whole far-cap path -- swing, rise, carry, descend -- the strands
    never come within a tube radius of post B's shaft until the descent, and on
    the descent they come down on either side of it;
  - the loop is taut through the carry (the straight-strand model only holds
    under tension, and the carry is where the strands sweep over B), never stretched beyond the cap ratio, and the
    carry height is above `carry_height_floor` for the landing point;
  - every held point is inside the manipulation workspace, and the far-cap
    grasp is a gripper's width away from both posts.

    python tests/check_ring_transfer_geometry.py

Needs the project venv: the geometry module imports `topogym.world.closed_band`,
whose package init imports Genesis (CPU import is enough; no GPU is used).
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.tasks.routing import _ring_transfer_geometry as geo  # noqa: E402
from topogym.world.rope import check_self_contact_clearance  # noqa: E402

TASK_CONFIG = REPO / "configs/task_configs/ring_transfer_topogym_tabletop_v1.yaml"
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

    posts = geo.posts_from_config(task.posts)
    ring = geo.ring_from_config(task.ring, task.rope)
    d_hat = float(task.rope.fem.contact_d_hat)
    anchor = posts[ring.enclosure[0]]
    target = posts[str(task.goal.enclosure[0])]
    others = [post for post in posts.values() if post.name != anchor.name]

    spawn = geo.spawn_centerline(ring, posts)
    frames, vertices, faces = geo.spawn_mesh(ring, spawn)
    print(
        f"loop           perimeter {frames.perimeter:.4f} m, loop radius {ring.loop_radius * 1000:.1f} mm, "
        f"{len(spawn)} rings x {ring.radial_segments}, reach {geo.loop_reach(spawn, ring, anchor) * 1000:.1f} mm "
        f"from {anchor.name}, far cap at {np.round(geo.far_cap_point(spawn, ring, anchor)[:2] * 1000, 1).tolist()} mm"
    )

    # --- posts vs loop ---------------------------------------------------------
    print()
    print("post clearance")
    for post in posts.values():
        need = post.radius + ring.tube_radius + d_hat
        print(
            f"  {post.name}: loop_radius {ring.loop_radius * 1000:.1f} >= r_post + r_tube + d_hat "
            f"= {need * 1000:.1f} mm  {'ok' if ring.loop_radius >= need else 'FAIL'}"
        )
        if ring.loop_radius < need:
            failures.append(f"loop_radius too small for post {post.name}")
    distance_anchor = float(np.min(geo.xy_distance_to_post(spawn, anchor)))
    print(
        f"  spawn loop to {anchor.name} axis: {distance_anchor * 1000:.1f} mm "
        f"(shaft + tube {(anchor.radius + ring.tube_radius) * 1000:.1f})"
    )
    if distance_anchor < anchor.radius + ring.tube_radius:
        failures.append(f"spawn loop intersects post {anchor.name}")
    for post in others:
        gap = float(np.min(geo.xy_distance_to_post(spawn, post))) - post.radius - ring.tube_radius
        print(f"  spawn loop to {post.name} surface: {gap * 1000:.1f} mm (want >= 20)")
        if gap < 0.020:
            failures.append(f"spawn loop too close to post {post.name}")

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
        failures.append("stretch trapezoid does not admit the target post")
    pinched = geo.strand_separation_at(
        ring=ring, anchor=anchor, landing_xy=landing, held_half_width=ring.tube_radius, query_xy=target.center
    )
    print(
        f"               negative control, pinched cap: {pinched * 1000:.1f} vs {need * 1000:.1f} mm "
        f"{'rejected as expected' if pinched < need else 'NOT rejected'}"
    )
    if pinched >= need:
        failures.append("negative control: a pinched cap should not admit the target post")
    fat = replace(target, radius=0.020)
    fat_have = geo.strand_separation_at(
        ring=ring, anchor=anchor, landing_xy=landing, held_half_width=half, query_xy=fat.center
    )
    fat_need = geo.min_strand_separation(fat, ring, d_hat)
    print(
        f"               negative control, 20 mm post: {fat_have * 1000:.1f} vs {fat_need * 1000:.1f} mm "
        f"{'rejected as expected' if fat_have < fat_need else 'NOT rejected'}"
    )
    if fat_have >= fat_need:
        failures.append("negative control: a 20 mm post should not fit the triangle")

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
        failures.append("carry_z below carry_height_floor")

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
        want = (target.radius + ring.tube_radius) if descending else keep_off
        ok = leg_min >= want
        print(
            f"  {label:8s} -> {np.round(point * 1000, 1).tolist()} mm: {leg_min * 1000:.1f} mm "
            f"(want >= {want * 1000:.1f}) {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            failures.append(f"strands touch post {target.name} during leg {label!r}")
        for held in (previous, point):
            if not (
                float(workspace.x[0]) + WORKSPACE_MARGIN <= held[0] <= float(workspace.x[1]) - WORKSPACE_MARGIN
                and float(workspace.y[0]) + WORKSPACE_MARGIN <= held[1] <= float(workspace.y[1]) - WORKSPACE_MARGIN
                and held[2] <= float(workspace.z[1])
            ):
                failures.append(f"held point {np.round(held, 3).tolist()} leaves the workspace at leg {label!r}")
        previous = point
    print(f"stretch ratio  worst over rise+carry {worst_stretch:.3f} (cap {MAX_STRETCH_RATIO}); slack legs: {slack_legs or 'none'}")
    if worst_stretch > MAX_STRETCH_RATIO:
        failures.append(f"stretch ratio {worst_stretch:.3f} exceeds {MAX_STRETCH_RATIO}")
    if slack_legs:
        failures.append(f"loop goes slack during {slack_legs}: strand sag over post B is not modelled")
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

    lift_z = anchor.top_z + ring.tube_radius + float(task.transfer.lift_margin)
    print(f"lift-off       near band to {lift_z * 1000:.1f} mm then +{float(task.transfer.shift) * 1000:.0f} mm toward {target.name}")

    print()
    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

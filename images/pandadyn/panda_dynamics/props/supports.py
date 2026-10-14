"""Bolted fixture stands with visible, collidable finite-thickness members.

Supports are scene hardware, never contacts or attachments added to payloads.
Z=0 is the worktop; outside it, a pedestal reaches the floor at z=-0.525 m.
"""
import numpy as np
import sapien


METAL = [0.29, 0.32, 0.34, 1]


def add_post(builder, frame, world_top, half=0.009):
    """Add a vertical world-aligned support to a static/root-link builder."""
    top = np.asarray(world_top, dtype=float)
    floor = 0.0 if -0.54 <= top[0] <= 0.70 and abs(top[1]) <= 0.48 else -0.525
    if top[2] - floor < 0.012:
        return
    center = np.array([top[0], top[1], (top[2] + floor) / 2])
    local = frame.inv() * sapien.Pose(center)
    half_size = [half, half, (top[2] - floor) / 2]
    builder.add_box_collision(pose=local, half_size=half_size)
    builder.add_box_visual(pose=local, half_size=half_size, material=METAL)
    foot = frame.inv() * sapien.Pose([top[0], top[1], floor + 0.003])
    builder.add_box_collision(pose=foot, half_size=[0.025, 0.025, 0.003])
    builder.add_box_visual(pose=foot, half_size=[0.025, 0.025, 0.003], material=METAL)


def support_static_builder(builder, frame):
    """Support raised rigid props at two points beneath their lowest box.

Task tracks can add more trestles explicitly. Nothing fills an opening or
extends above the existing bottom of the collision geometry.
"""
    candidates = []
    for record in list(builder.collision_records):
        if record.type != 'box':
            continue
        pose = frame * record.pose
        half = np.asarray(record.scale)
        for x in (-0.65 * half[0], 0.65 * half[0]):
            point = pose * sapien.Pose([x, 0, -half[2]])
            candidates.append(point.p)
    if not candidates:
        return
    lowest = min(float(p[2]) for p in candidates)
    if lowest <= 0.018:
        return
    base = sorted(candidates, key=lambda p: p[2])[:2]
    for point in base:
        add_post(builder, frame, point)


def pedestal(root, origin, top_local=-0.045):
    frame = sapien.Pose(origin)
    add_post(root, frame, np.asarray(origin) + [0, 0, top_local], half=0.016)


def hanging_stand(root, pivot):
    """Rear upright and horizontal bearing arm leave the swing plane open."""
    frame = sapien.Pose(pivot)
    add_post(root, frame, np.asarray(pivot) + [0, 0.16, 0], half=0.012)
    pose = sapien.Pose([0, 0.08, 0])
    root.add_box_collision(pose=pose, half_size=[0.012, 0.08, 0.012])
    root.add_box_visual(pose=pose, half_size=[0.012, 0.08, 0.012], material=METAL)

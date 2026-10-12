# Cast Keyhole / easier: start state

Source task: `robotangle-cast-keyhole-easier-i00` (RoboTangle release robotangle-r2). Units: mm, degrees. Positions are in the table frame (origin = centre of the tabletop surface, +Z up); see `layout.json` for the same poses relative to the robot base(s).

## Robot

ALOHA 2 bimanual (two ViperX-300s 6-DoF arms with ALOHA parallel grippers), from MuJoCo Menagerie aloha.xml; base frames = left/base_link and right/base_link mounting faces.

- `aloha_left_base`: position (-469.0, -19.0, 0.0) mm, yaw 0 deg
- `aloha_right_base`: position (469.0, -19.0, 0.0) mm, yaw 180 deg

Start joint targets (rad; simulator order left/waist, left/shoulder, left/elbow, left/forearm_roll, left/wrist_angle, left/wrist_rotate, left_native_gripper, right/waist, right/shoulder, right/elbow, right/forearm_roll, right/wrist_angle, right/wrist_rotate, right_native_gripper): 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0084, 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0084

## What is where at the start

The two plates start interlocked (each passes through the other's keyhole slot) and rest on the table. Both are free bodies.

| part | printable | role | position (x, y, z) | quaternion (w, x, y, z) | euler xyz (deg) | bottom above table |
|---|---|---|---|---|---|---|
| keyhole_gold | yes | movable | (-70.5, 50.0, 31.3) | (0.6533, 0.2706, 0.6533, 0.2706) | (90.0, 45.0, 90.0) | 0.5 |
| keyhole_silver | yes | movable | (70.5, 50.0, 31.3) | (0.6533, 0.2706, 0.6533, 0.2706) | (90.0, 45.0, 90.0) | 0.5 |

Goal region (`goal_region`, a flat outline only, no collision): x -128.3 to 128.3, y 114.8 to 371.3 mm. Mark it with tape.

## Measured gaps between parts at the start

Minimum surface distance between the exported solids in the start layout (pairs within 20 mm; <= 0.25 mm = resting contact).

| part A | part B | min gap (mm) |
|---|---|---|
| keyhole_gold | keyhole_silver | 4.80 |

## Clearances reported by the task generator

- `minimum_initial_surface_clearance_m`: 4.81 mm

# 3D buzz wire / medium: start state

Source task: `robotangle-buzz-wire-3d-medium-i00` (RoboTangle release robotangle-r2). Units: mm, degrees. Positions are in the table frame (origin = centre of the tabletop surface, +Z up); see `layout.json` for the same poses relative to the robot base(s).

## Robot

Franka Emika Panda (7-DoF) with a Robotiq 2F-85 gripper; base frame = link0 mounting face (world_tabletop_v1.yaml robot_mount.pos).

- `panda_base`: position (-434.3, 0.0, 0.0) mm, yaw 0 deg

Start joint targets (rad; simulator order joint1, joint2, joint3, joint4, joint5, joint6, joint7, arm_native_gripper): 0.0000, 0.3927, 0.0000, -1.9635, 0.0000, 2.3562, -0.7854, 0.0000

## What is where at the start

The wand starts resting on the deck with its loop around the start of the wire (the wire passes through the loop: the wand is threaded on the wire from the start). The wire, its two end blocks and the raised wooden deck are fixed.

| part | printable | role | position (x, y, z) | quaternion (w, x, y, z) | euler xyz (deg) | bottom above table |
|---|---|---|---|---|---|---|
| wire_base | yes | fixed | (55.7, -270.0, 71.2) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| wire_rail_REFERENCE_tube | no (reference) | fixed | (72.2, -294.3, 237.6) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 153.0 |
| wire_wood_stop_0 | yes | fixed | (-161.3, -389.0, 148.5) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 142.5 |
| wire_wood_stop_1 | yes | fixed | (305.7, -390.0, 148.5) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 142.5 |
| wand | yes | movable | (-141.5, -378.1, 145.6) | (0.9684, 0.0059, -0.0232, 0.2481) | (0.0, -2.7, 28.7) | 142.6 |

## Measured gaps between parts at the start

Minimum surface distance between the exported solids in the start layout (pairs within 20 mm; <= 0.25 mm = resting contact).

| part A | part B | min gap (mm) |
|---|---|---|
| wire_base | wand | 0.06 (contact) |
| wire_wood_stop_0 | wand | 8.46 |

## Clearances reported by the task generator

- `layout.clearance_cover_m`: 0.35 mm
- `layout.finish_cradle_mount_clearance_m`: 0.00 mm
- `nominal_radial_clearance_m`: 12.67 mm

## Non-printable: wire_rail (bent metal wire)

- kind: bent metal wire
- length_mm: 2604.6
- diameter_mm: 2.94
- min_bend_radius_mm: 1.98
- loop_inner_radius_mm: 14.14
- loop_tube_diameter_mm: 2.52
- nominal_radial_clearance_mm: 12.67
- sections: ["start_post", "entry_comb", "layered_eight", "front_vertical_w", "exit_bend", "finish_post"]
- centreline_csv: buzz_wire_centerline.csv
- reference_tube_stl: wire_rail_REFERENCE_tube.stl

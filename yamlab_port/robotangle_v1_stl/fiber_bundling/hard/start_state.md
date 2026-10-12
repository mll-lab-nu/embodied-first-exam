# Fiber bundling (cable through ring) / hard: start state

Source task: `robotangle-fiber-bundling-hard-i00` (RoboTangle release robotangle-r2). Units: mm, degrees. Positions are in the table frame (origin = centre of the tabletop surface, +Z up); see `layout.json` for the same poses relative to the robot base(s).

## Robot

Franka Emika Panda (7-DoF) with a Robotiq 2F-85 gripper; base frame = link0 mounting face (world_tabletop_v1.yaml robot_mount.pos).

- `panda_base`: position (-434.3, 0.0, 0.0) mm, yaw 0 deg

Start joint targets (rad; simulator order joint1, joint2, joint3, joint4, joint5, joint6, joint7, arm_native_gripper): 0.0000, 0.3927, 0.0000, -1.9635, 0.0000, 2.3562, -0.7854, 0.0000

## What is where at the start

The cable is anchored in the terminal box gland, runs as a slack lead to the U cradle and rests in it, strands fanned out toward the ring. The ring stands on its post; nothing is threaded yet.

| part | printable | role | position (x, y, z) | quaternion (w, x, y, z) | euler xyz (deg) | bottom above table |
|---|---|---|---|---|---|---|
| cable_terminal_box | yes | fixed | (-385.8, -410.0, 151.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| bundling_ring | yes | fixed | (385.7, -250.0, 240.0) | (0.7071, 0.0000, 0.7071, 0.0000) | (-0.0, 90.0, 0.0) | 218.5 |
| cable_cradle_base | yes | fixed | (55.7, -250.0, 6.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| cable_cradle_post | yes | fixed | (55.7, -250.0, 114.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 12.0 |
| cable_cradle_pad | yes | fixed | (55.7, -250.0, 224.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 220.0 |
| cable_cradle_left | yes | fixed | (55.7, -271.0, 235.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 216.0 |
| cable_cradle_right | yes | fixed | (55.7, -229.0, 235.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 216.0 |
| ring_mount_base | yes | fixed | (385.7, -250.0, 6.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| ring_mount_post | yes | fixed | (385.7, -250.0, 115.2) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 12.0 |

## Clearances reported by the task generator

- `fiber_min_initial_surface_clearance_m`: 0.72 mm
- `trunk_radial_clearance_m`: 1.48 mm
- `coarse_min_initial_surface_clearance_m`: 11.67 mm

## Non-printable: fiber_bundle (cable)

- physics_model: articulated_cable
- sim_material:
  - gravity_compensation: 1.0
- kind: cable
- lead_length_mm: 830.14
- jacket_diameter_mm: 24.0
- trunk_length_mm: 240.0
- fiber_count: 16
- fiber_diameter_mm: 2.4
- fiber_length_mm: 80.0
- fan_angle_deg: [28.0, 50.0]
- density_kg_m3: 1100.0
- ring_inner_radius_mm: 13.5
- trunk_radial_clearance_mm: 1.48
- model: fixed terminal root; passive articulated slack lead, working trunk and fine strands
- appearance: black cable jacket, cut sheath and filler, PVC insulated cores, 3 mm stranded copper tips

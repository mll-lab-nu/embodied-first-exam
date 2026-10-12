# Rope threading / medium: start state

Source task: `robotangle-rope-threading-medium-i00` (RoboTangle release robotangle-r2). Units: mm, degrees. Positions are in the table frame (origin = centre of the tabletop surface, +Z up); see `layout.json` for the same poses relative to the robot base(s).

## Robot

ALOHA 2 bimanual (two ViperX-300s 6-DoF arms with ALOHA parallel grippers), from MuJoCo Menagerie aloha.xml; base frames = left/base_link and right/base_link mounting faces.

- `aloha_left_base`: position (-469.0, -19.0, 20.9) mm, yaw 0 deg
- `aloha_right_base`: position (469.0, -19.0, 20.9) mm, yaw 180 deg

Start joint targets (rad; simulator order left/waist, left/shoulder, left/elbow, left/forearm_roll, left/wrist_angle, left/wrist_rotate, left_native_gripper, right/waist, right/shoulder, right/elbow, right/forearm_roll, right/wrist_angle, right/wrist_rotate, right_native_gripper): 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0084, 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0084

## What is where at the start

The rope lies on the table in a gentle curve, unthreaded (rope_start_centerline.csv; rings and threading order in topology_topview.png). Ring stands are fixed. The ALOHA bases stand on two 70 x 70 x 20.9 mm risers (printable, included).

| part | printable | role | position (x, y, z) | quaternion (w, x, y, z) | euler xyz (deg) | bottom above table |
|---|---|---|---|---|---|---|
| R1 | yes | fixed | (75.0, -19.0, 331.9) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 250.9 |
| R1_stand | yes | fixed | (75.0, -94.0, 170.9) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 4.9 |
| R1_base | yes | fixed | (75.0, -94.0, 4.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| R2 | yes | fixed | (-25.0, 120.0, 310.9) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 229.9 |
| R2_stand | yes | fixed | (50.0, 120.0, 160.4) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 4.9 |
| R2_base | yes | fixed | (50.0, 120.0, 4.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| R3 | yes | fixed | (90.0, 375.0, 280.9) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 203.8 |
| R3_stand | yes | fixed | (18.8, 398.7, 145.4) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | 4.9 |
| R3_base | yes | fixed | (18.8, 398.7, 4.0) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| left_base_riser | yes | fixed | (-469.0, -19.0, 10.4) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |
| right_base_riser | yes | fixed | (469.0, -19.0, 10.4) | (1.0000, 0.0000, 0.0000, 0.0000) | (0.0, 0.0, 0.0) | -0.0 |

## Clearances reported by the task generator

- `table_surface_gap_m`: 0.30 mm
- `minimum_fixture_gap_lower_bound_m`: 124.63 mm
- `minimum_nonlocal_rope_surface_gap_m`: 26.36 mm

## Non-printable: rope (rope)

- physics_model: fem_elastic
- sim_material:
  - E: 5000000.0
  - friction_mu: 0.3
  - model: stable_neohookean
  - nu: 0.3
  - rho: 650.0
- kind: rope
- length_mm: 1100.0
- diameter_mm: 8.0
- route:
  - order: ["R1-", "R2+", "R3+"]
  - rings: [{"name": "R1", "centre_table_mm": [75.0, -19.0, 331.9], "normal": [1.0, 0.0, 0.0], "aperture_diameter_mm": 137.99999999999997}, {"name": "R2", "centre_table_mm": [-25.0, 120.0, 310.9], "normal": [0.0, 1.0, 0.0], "aperture_diameter_mm": 137.99999999999997}, {"name": "R3", "centre_table_mm": [90.0, 375.0, 280.9], "normal": [0.3, 0.9, 0.316228], "aperture_diameter_mm": 137.99999999999997}]
  - meaning: 'R1-' = the rope passes through ring R1 against its normal, '+' = along it, in this order from the rope's material start (first CSV row) to its end; at the start the rope lies unthreaded on the table (no crossings)
- centreline_csv: rope_start_centerline.csv

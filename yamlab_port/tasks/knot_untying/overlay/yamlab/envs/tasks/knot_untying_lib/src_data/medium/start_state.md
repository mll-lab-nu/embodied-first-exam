# Knot untying / medium: start state

Source task: `robotangle-knot-untying-medium-i00` (RoboTangle release robotangle-r2). Units: mm, degrees. Positions are in the table frame (origin = centre of the tabletop surface, +Z up); see `layout.json` for the same poses relative to the robot base(s).

## Robot

ALOHA 2 bimanual (two ViperX-300s 6-DoF arms with ALOHA parallel grippers), from MuJoCo Menagerie aloha.xml; base frames = left/base_link and right/base_link mounting faces.

- `aloha_left_base`: position (-469.0, -19.0, 0.0) mm, yaw 0 deg
- `aloha_right_base`: position (469.0, -19.0, 0.0) mm, yaw 180 deg

Start joint targets (rad; simulator order left/waist, left/shoulder, left/elbow, left/forearm_roll, left/wrist_angle, left/wrist_rotate, left_gripper, right/waist, right/shoulder, right/elbow, right/forearm_roll, right/wrist_angle, right/wrist_rotate, right_gripper): 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0001, 0.0000, -0.9600, 1.1600, 0.0000, -0.3000, 0.0000, 0.0001

## What is where at the start

The rope lies on the table in the knot listed below (centreline in rope_start_centerline.csv, top view with the crossings in topology_topview.png). No rigid parts; nothing to print.

## Clearances reported by the task generator

- `minimum_nonlocal_surface_gap_m`: 3.51 mm
- `table_surface_clearance_m`: 1.00 mm
- `parameters.table_clearance_m`: 1.00 mm

## Non-printable: rope (rope)

- physics_model: fem_elastic
- sim_material:
  - E: 50000.0
  - friction_mu: 0.3
  - model: stable_neohookean
  - nu: 0.3
  - rho: 650.0
- kind: rope
- length_mm: 1073.77
- diameter_mm: 8.0
- knot:
  - type: open_overhand
  - closure: trefoil_3_1
  - crossings: 3
  - over_under_along_rope: ["U", "O", "U", "O", "U", "O"]
  - gauss_code: [1, 2, 3, 1, 2, 3]
  - handedness: right
  - tail_length_mm: 180.0
  - planar_scale_mm: 32.0
  - crossing_height_gaps_mm: [11.62, 11.62, 11.62]
  - min_bend_radius_mm: 27.11
- centreline_csv: rope_start_centerline.csv

> **Subset for the YAMLab port:** only the five families ported to YAMLab are included here (buzz_wire_3d, cast_keyhole, fiber_bundling, knot_untying, rope_threading). The full 11-family package is in the lab's workspace at `tmp/2026-10-11_robotangle_v1_stl/`; ask Qineng.

# RoboTangle (pre-MuJoCo release): 3D-print package

Every rigid part of every scene of the Genesis-based RoboTangle release, as STL files, with the scene layouts and start states, so the tasks can be rebuilt for a real robot.

## Suggested starting families

All 11 families are included, and you are welcome to pick whichever suit your setup. If it helps to start somewhere, these are the families we would suggest looking at first (in no particular order):

- `cast_coil` or `cast_keyhole`
- `buzz_wire_3d`
- `rope_threading`
- `fiber_bundling`
- `blanket_flatten`

## Source

- Repository `robot_coding_bench`, branch `main` at commit **4ff51fa5b** (2026-10-11 04:11 -0700), the last state of `main` before the MuJoCo migration. RoboTangle entered `main` in 2c9ebbe4d (PR #81, 2026-10-08); later commits on `main` changed texts, graders and tooling only, not geometry.
- Release `robotangle-r2` (`scripts/robotangle/release.json`): simulator source = `dev/jianwen` commit **2dafa5f2b2f596d3be78d92bb1b4377b548c4c7f** (topogym, Genesis 1.2.1), image `eai-robotangle:0.2.22`, frozen task instances pinned by sha256 in `scripts/robotangle/assets.json`.
- Not included: the MuJoCo port (`dev/robotangle_mujoco`), the later redesigned tiers, and what this release did not ship (slotted_post_ring, orbits, rope_threading very_easy/easier, blanket_flatten easier).
- How the geometry was produced: for each of the 52 frozen instances, the release's own task code declared the scene (`TaskDefinition.declare` + `finalize_spec`, which runs each family's geometry generator with the instance's parameters; no physics). The effective task parameters matched the frozen instances in 52/52 cases. Start poses are the frozen instances' start poses (identical to the declared poses in every case).

## Families and tiers

Tiers, easiest first: very_easy, easier, easy, medium, hard. 11 families, 52 tiers.

| family | robot | what the task is | tiers in this release |
|---|---|---|---|
| `interlocked_claws` (Interlocked claws) | ALOHA 2 (bimanual) | Two rigid claw-shaped pieces hooked through each other; separate them completely (very_easy/easier: and place the brown piece in the goal square). | very_easy, easier, easy, medium, hard |
| `cast_coil` (Cast Coil (two-piece burr)) | ALOHA 2 (bimanual) | Two rigid voxel-style puzzle pieces (gold, silver) lying apart on the table; assemble them (very_easy/easier: into a cube with flush faces; easy/medium/hard: into their interlocking configuration). | very_easy, easier, easy, medium, hard |
| `cast_keyhole` (Cast Keyhole) | ALOHA 2 (bimanual) | Two flat rigid keyhole plates (gold, silver) start interlocked through each other's slots; take the silver piece out and place it in the goal square. | very_easy, easier, easy, medium, hard |
| `hedgehog_in_cage` (Hedgehog in cage) | Franka Panda + Robotiq 2F-85 | A spiky ball inside a bar cage fixed on a square mount; extract the ball through the cage's openings (the cage design differs per tier) and put it in the goal square. | very_easy, easier, easy, medium, hard |
| `horseshoe_ring` (Horseshoes and ring) | ALOHA 2 (bimanual) | The classic two-horseshoe puzzle: two horseshoes joined by two chain links, with a closed ring trapped on them; free the ring and put it in the goal square. | very_easy, easier, easy, medium, hard |
| `lock_picking` (Rotor lock (key through rotor plates)) | Franka Panda + Robotiq 2F-85 | A long tabbed key rests in V cradles; insert it through two or three slotted rotor plates (each turns about the insertion axis between stops) and the final END plate. | very_easy, easier, easy, medium, hard |
| `buzz_wire_3d` (3D buzz wire) | Franka Panda + Robotiq 2F-85 | The wire-loop game: guide a metal loop on a wooden handle along a bent 3D wire from the start to the finish support without touching it, then rest the tool on the finish support. | very_easy, easier, easy, medium, hard |
| `fiber_bundling` (Fiber bundling (cable through ring)) | Franka Panda + Robotiq 2F-85 | A thick cable leaves a fixed terminal box, lies in a U cradle and ends in a fan of fine strands; pass the sheath and every strand through a fixed copper ring. | very_easy, easier, easy, medium, hard |
| `rope_threading` (Rope threading) | ALOHA 2 (bimanual, on 20.9 mm risers) | Thread a rope through two or three rings on stands in a given order and direction. | easy, medium, hard |
| `knot_untying` (Knot untying) | ALOHA 2 (bimanual) | A soft rope lies on the table tied in a loose knot or overlap pattern; untie and spread it so its top view has no crossings. | very_easy, easier, easy, medium, hard |
| `blanket_flatten` (Blanket flattening) | ALOHA 2 (bimanual) | Unfold and spread a blanket flat on the table. | very_easy, easy, medium, hard |

## Parts per family and tier

Counts: printable STLs / reference-only STLs / non-printable items (rope, cable, cloth, wire). Every tier folder is self-contained even where tiers share a part (see Shared parts).

### interlocked_claws

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 2 / 0 / 0 | piece_0, piece_1 | - |
| easier | 2 / 0 / 0 | piece_0, piece_1 | - |
| easy | 2 / 0 / 0 | piece_0, piece_1 | - |
| medium | 2 / 0 / 0 | piece_0, piece_1 | - |
| hard | 2 / 0 / 0 | claw_0, claw_1 | - |

### cast_coil

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 2 / 0 / 0 | coil_gold, coil_silver | - |
| easier | 2 / 0 / 0 | coil_gold, coil_silver | - |
| easy | 2 / 0 / 0 | coil_gold, coil_silver | - |
| medium | 2 / 0 / 0 | coil_gold, coil_silver | - |
| hard | 2 / 0 / 0 | coil_gold, coil_silver | - |

### cast_keyhole

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 2 / 0 / 0 | keyhole_gold, keyhole_silver | - |
| easier | 2 / 0 / 0 | keyhole_gold, keyhole_silver | - |
| easy | 2 / 0 / 0 | keyhole_gold, keyhole_silver | - |
| medium | 2 / 0 / 0 | keyhole_gold, keyhole_silver | - |
| hard | 2 / 0 / 0 | keyhole_gold, keyhole_silver | - |

### hedgehog_in_cage

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 3 / 0 / 0 | hedgehog_mount, hedgehog_cage, hedgehog_ball | - |
| easier | 3 / 0 / 0 | hedgehog_mount, hedgehog_cage, hedgehog_ball | - |
| easy | 3 / 0 / 0 | hedgehog_mount, hedgehog_cage, hedgehog_ball | - |
| medium | 3 / 0 / 0 | hedgehog_mount, hedgehog_cage, hedgehog_ball | - |
| hard | 3 / 0 / 0 | hedgehog_mount, hedgehog_cage, hedgehog_ball | - |

### horseshoe_ring

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 5 / 0 / 0 | horseshoe_left, horseshoe_right, chain_upper_1, chain_lower_1, target_ring | - |
| easier | 5 / 0 / 0 | horseshoe_left, horseshoe_right, chain_upper_1, chain_lower_1, target_ring | - |
| easy | 5 / 0 / 0 | horseshoe_left, horseshoe_right, chain_upper_1, chain_lower_1, target_ring | - |
| medium | 5 / 0 / 0 | horseshoe_left, horseshoe_right, chain_upper_1, chain_lower_1, target_ring | - |
| hard | 5 / 0 / 0 | horseshoe_left, horseshoe_right, chain_upper_1, chain_lower_1, target_ring | - |

### lock_picking

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 15 / 0 / 0 | lock_base, lock_disc_0, lock_frame_0, lock_disc_1, lock_frame_1, key_tray, key_tray_post_0, key_cradle_0_0, key_cradle_0_1, key_tray_post_1, key_cradle_1_0, key_cradle_1_1, lock_goal_post, lock_goal, lock_key | - |
| easier | 15 / 0 / 0 | lock_base, lock_disc_0, lock_frame_0, lock_disc_1, lock_frame_1, key_tray, key_tray_post_0, key_cradle_0_0, key_cradle_0_1, key_tray_post_1, key_cradle_1_0, key_cradle_1_1, lock_goal_post, lock_goal, lock_key | - |
| easy | 17 / 0 / 0 | lock_base, lock_disc_0, lock_frame_0, lock_disc_1, lock_frame_1, lock_disc_2, lock_frame_2, key_tray, key_tray_post_0, key_cradle_0_0, key_cradle_0_1, key_tray_post_1, key_cradle_1_0, key_cradle_1_1, lock_goal_post, lock_goal, lock_key | - |
| medium | 17 / 0 / 0 | lock_base, lock_disc_0, lock_frame_0, lock_disc_1, lock_frame_1, lock_disc_2, lock_frame_2, key_tray, key_tray_post_0, key_cradle_0_0, key_cradle_0_1, key_tray_post_1, key_cradle_1_0, key_cradle_1_1, lock_goal_post, lock_goal, lock_key | - |
| hard | 17 / 0 / 0 | lock_base, lock_disc_0, lock_frame_0, lock_disc_1, lock_frame_1, lock_disc_2, lock_frame_2, key_tray, key_tray_post_0, key_cradle_0_0, key_cradle_0_1, key_tray_post_1, key_cradle_1_0, key_cradle_1_1, lock_goal_post, lock_goal, lock_key | - |

### buzz_wire_3d

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 4 / 1 / 1 | wire_base, wire_wood_stop_0, wire_wood_stop_1, wand | wire_rail, wire_rail_REFERENCE_tube |
| easier | 4 / 1 / 1 | wire_base, wire_wood_stop_0, wire_wood_stop_1, wand | wire_rail, wire_rail_REFERENCE_tube |
| easy | 4 / 1 / 1 | wire_base, wire_wood_stop_0, wire_wood_stop_1, wand | wire_rail, wire_rail_REFERENCE_tube |
| medium | 4 / 1 / 1 | wire_base, wire_wood_stop_0, wire_wood_stop_1, wand | wire_rail, wire_rail_REFERENCE_tube |
| hard | 4 / 1 / 1 | wire_base, wire_wood_stop_0, wire_wood_stop_1, wand | wire_rail, wire_rail_REFERENCE_tube |

### fiber_bundling

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 9 / 0 / 1 | cable_terminal_box, bundling_ring, cable_cradle_base, cable_cradle_post, cable_cradle_pad, cable_cradle_left, cable_cradle_right, ring_mount_base, ring_mount_post | fiber_bundle |
| easier | 9 / 0 / 1 | cable_terminal_box, bundling_ring, cable_cradle_base, cable_cradle_post, cable_cradle_pad, cable_cradle_left, cable_cradle_right, ring_mount_base, ring_mount_post | fiber_bundle |
| easy | 9 / 0 / 1 | cable_terminal_box, bundling_ring, cable_cradle_base, cable_cradle_post, cable_cradle_pad, cable_cradle_left, cable_cradle_right, ring_mount_base, ring_mount_post | fiber_bundle |
| medium | 9 / 0 / 1 | cable_terminal_box, bundling_ring, cable_cradle_base, cable_cradle_post, cable_cradle_pad, cable_cradle_left, cable_cradle_right, ring_mount_base, ring_mount_post | fiber_bundle |
| hard | 9 / 0 / 1 | cable_terminal_box, bundling_ring, cable_cradle_base, cable_cradle_post, cable_cradle_pad, cable_cradle_left, cable_cradle_right, ring_mount_base, ring_mount_post | fiber_bundle |

### rope_threading

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| easy | 8 / 0 / 1 | R1, R1_stand, R1_base, R2, R2_stand, R2_base, left_base_riser, right_base_riser | rope |
| medium | 11 / 0 / 1 | R1, R1_stand, R1_base, R2, R2_stand, R2_base, R3, R3_stand, R3_base, left_base_riser, right_base_riser | rope |
| hard | 11 / 0 / 1 | R1, R1_stand, R1_base, R2, R2_stand, R2_base, R3, R3_stand, R3_base, left_base_riser, right_base_riser | rope |

### knot_untying

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 0 / 0 / 1 | - | rope |
| easier | 0 / 0 / 1 | - | rope |
| easy | 0 / 0 / 1 | - | rope |
| medium | 0 / 0 / 1 | - | rope |
| hard | 0 / 0 / 1 | - | rope |

### blanket_flatten

| tier | STLs (print / ref / non-printable) | printable parts | non-printable |
|---|---|---|---|
| very_easy | 0 / 0 / 1 | - | blanket |
| easy | 0 / 0 / 1 | - | blanket |
| medium | 0 / 0 / 1 | - | blanket |
| hard | 0 / 0 / 1 | - | blanket |

## Folder layout

`<family>/<tier>/` holds:
- `<part>.stl`: one file per physical part (binary STL, millimetres).
- `layout.json` / `layout.csv`: every part's start pose, the robot type and base pose(s), the goal-region outline.
- `start_state.md`: start poses in a table, what is interlocked/inserted/held at the start, joint states, measured gaps between parts, the generator's design clearances, the specs of rope/cable/cloth/wire and knot topology.
- `preview.png`: a quick render of the parts in their start layout; knot_untying and rope_threading also have `topology_topview.png` (the knot's crossings with over/under, or the rings and threading order).
- non-printable references where relevant: `*_centerline.csv` polylines (mm, table frame), `wire_rail_REFERENCE_tube.stl`, `blanket_start_state_REFERENCE_points.ply`.
- `audit.json`: the checks behind this README (watertightness, volume, wall thickness, gaps, sources).

## Units and frames

- Millimetres everywhere. Angles in degrees except the raw joint values in `start_state.md` (rad).
- **Table frame**: origin at the centre of the tabletop surface, +Z up, X/Y = the simulator's world axes. The simulated table is 1500 x 1400 mm (X x Y); its top is 919.6 mm above the floor. ALOHA tasks: both arm bases lie on the line y = -19 mm, at x = -469 mm (left arm, facing +X) and x = +469 mm (right arm, yaw 180 deg). Panda tasks: the arm base is at (-434.3, 0.0, 0.0) mm, facing +X. Exact values are in each `layout.json` (`frames.robot_bases`).
- **Part frame (STL coordinates)**: the origin is the centre of the part's axis-aligned bounding box, measured in the part's own body axes in the simulator; the STL is not re-oriented for printing. Parts that stand fixed on the table have identity orientation, so their STL Z is up and their bottom face sits at `bottom_z_above_table_mm`. Free parts (pieces, rings, keys, wands) keep their body axes; choose the print orientation in the slicer.
- **Poses**: `pose.table` places the STL origin and axes in the table frame: position (mm), quaternion (w, x, y, z), and euler_xyz_deg = extrinsic rotations about the table's X, then Y, then Z. Apply the rotation about the STL origin, then translate. `pose.<robot_base>` gives the same pose relative to each robot base frame (base frame: x forward, z up, origin on the mounting face). `layout.csv` has one row per part and reference frame.

## Geometry source and fidelity

- Default: the **union of the simulator's collision solids** for each part, i.e. the shape the physics actually used (generator-written convex pieces, boxes and prisms; spheres/cylinders tessellated with 128 facets around and 5120-face spheres). For these parts the generator's visual mesh has the same volume where it is watertight (cast pieces, keyhole plates, claws, hedgehog ball, lock key) to within 0.4 %, so nothing is lost. Where collision pieces only touched each other (lock rotors and END plates), the touching shells were grown by 0.005 mm, or the pieces by 0.01 mm, so that they fuse into one solid (`repair` in `audit.json`).
- Exception (smooth sources): the horseshoes, chain links and target ring (horseshoe_ring), the copper ring (fiber_bundling) and the buzz-wire wand use the generator's smooth tube meshes; their simulated collision was a chain of spheres and cylinders within 0.3 mm of them. The horseshoe bands' convex collision pieces stick out of the smooth band by up to 4 mm locally (0.2-0.5 % of the volume).
- Rope-threading rings, stands and bases, and the lock key cradles, are the generator's meshes, which the simulator used directly. Boxes (mounts, posts, trays, risers, cradle plates) are exact.
- Visual-only decoration is left out: lock rotor/END-plate outline rims (+5 mm), the terminal box's LEDs, labels and bolts, cable jacket textures, the buzz-wire deck's wood grain.
- Goal squares are visual-only outlines in the simulator (no collision). They are given as rectangles in `layout.json` (`markers`) and `start_state.md`; mark them with tape.

## What is printable and what is not

Printable (rigid): claw pieces, cast-coil and keyhole pieces, the hedgehog ball, cage and mount, horseshoes, chain links, the target ring, lock rotors, stop frames, END plate, key, key tray, posts and V cradles, lock base, the buzz-wire deck, wire end blocks and wand, cable terminal box, U cradle parts, ring and its mount, rope-threading rings, stands and bases, ALOHA risers.

Not printable (buy or make; specs in each tier's `start_state.md`):

| family | item | simulated spec | suggestion |
|---|---|---|---|
| buzz_wire_3d | wire rail | 2.94 mm wire; length / smallest bend radius per tier: very_easy 610 / 34.7 mm, easier 646 / 29.4 mm, easy 996 / 26.7 mm, medium 2605 / 2.0 mm, hard 2179 / 1.3 mm; wand loop inner radius 14.14 mm | 3 mm copper, brass or aluminium rod bent to `buzz_wire_centerline.csv`; `wire_rail_REFERENCE_tube.stl` can be printed as a bending template. Wire shape differs per tier. |
| fiber_bundling | cable | jacket 24 mm diameter; slack lead 830 mm + working trunk 240 mm, ending in 2-16 strands (per tier) of 2.4 mm x 80 mm; articulated rigid segments, density 1100 kg/m3 | a 24 mm multi-core cable with the jacket stripped back 80 mm to expose N insulated cores; the ring aperture radius is 13.5 mm (radial clearance over the jacket 1.48 mm: very tight) |
| rope_threading | rope | 8 mm diameter, 1100 mm long, FEM neo-Hookean E = 5 MPa, density 650 kg/m3 | 8 mm hemp or cotton rope |
| knot_untying | rope | 8 mm diameter, 989-1355 mm long (per tier), FEM neo-Hookean E = 50 kPa, density 650 kg/m3, friction 0.3 | soft 8 mm cotton or braided polyester rope; tie the knot in `start_state.md` |
| blanket_flatten | blanket | 600 x 480 mm cloth; PBD parameters rho 4.0, stretch compliance 1e-07, bending compliance 1e-05; table friction static 0.5 / kinetic 0.4 | a light cotton or fleece cloth cut to 600 x 480 mm; arrange it like the start-state point cloud |

## Print risks (flags)

How to read the thickness flags: 'thin' means at least 1 % of the part's surface sits on a wall under 1.5 mm; 'local thin spot/knife edge' means only isolated rays found a thin wall (sharp concave corners, the tips of wedges, where two faces meet at a shallow angle), with the 1st percentile still thick. The lock-picking key cradles are V-wedge blocks whose sloped face runs out to a sharp edge: blunt that edge to about 1 mm. The hedgehog cages have slender bars and fins (medium: about 1 mm), which are better printed in a stiff material or scaled up.

Thresholds: walls thinner than 1.5 mm (ray-cast wall thickness over 3000 surface samples; p1 = 1st percentile), clearances under 0.5 mm, parts over 250 mm. All STLs were re-loaded as a slicer would and checked with trimesh: watertight, consistent winding, volume > 0.

- Watertight/winding/volume failures: **0**.

| family | tier | part | flag |
|---|---|---|---|
| interlocked_claws | easy | piece_0 | local thin spot/knife edge: min 0.19 mm (p1 9.00) |
| interlocked_claws | easy | piece_1 | local thin spot/knife edge: min 0.19 mm (p1 9.00) |
| interlocked_claws | medium | piece_0 | large: 329 mm > 250 mm bed |
| interlocked_claws | medium | piece_1 | large: 308 mm > 250 mm bed |
| interlocked_claws | hard | claw_0 | local thin spot/knife edge: min 0.07 mm (p1 11.58) |
| cast_keyhole | medium | keyhole_gold | local thin spot/knife edge: min 0.15 mm (p1 7.88) |
| hedgehog_in_cage | very_easy | hedgehog_cage | local thin spot/knife edge: min 0.91 mm (p1 9.00) |
| hedgehog_in_cage | easier | hedgehog_cage | local thin spot/knife edge: min 1.21 mm (p1 9.00) |
| hedgehog_in_cage | easy | hedgehog_cage | local thin spot/knife edge: min 1.43 mm (p1 8.99) |
| hedgehog_in_cage | medium | hedgehog_cage | thin: wall p1 1.04 mm, min 0.01 mm |
| hedgehog_in_cage | hard | hedgehog_cage | local thin spot/knife edge: min 0.14 mm (p1 2.38) |
| horseshoe_ring | very_easy | horseshoe_left | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | very_easy | horseshoe_right | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | easier | horseshoe_left | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | easier | horseshoe_right | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | easy | horseshoe_left | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | easy | horseshoe_right | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | medium | horseshoe_left | local thin spot/knife edge: min 1.30 mm (p1 5.49) |
| horseshoe_ring | medium | horseshoe_left | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | medium | horseshoe_right | local thin spot/knife edge: min 0.97 mm (p1 5.49) |
| horseshoe_ring | medium | horseshoe_right | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | hard | horseshoe_left | sim collision proxy up to 4.0 mm outside this smooth source |
| horseshoe_ring | hard | horseshoe_right | sim collision proxy up to 4.0 mm outside this smooth source |
| lock_picking | very_easy | key_cradle_0_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | very_easy | key_cradle_0_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | very_easy | key_cradle_1_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | very_easy | key_cradle_1_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | very_easy | key_tray | large: 400 mm > 250 mm bed |
| lock_picking | very_easy | lock_base | large: 885 mm > 250 mm bed |
| lock_picking | very_easy | lock_disc_0 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | very_easy | lock_disc_1 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | very_easy | lock_frame_0 | large: 270 mm > 250 mm bed |
| lock_picking | very_easy | lock_frame_1 | large: 270 mm > 250 mm bed |
| lock_picking | very_easy | lock_key | local thin spot/knife edge: min 1.00 mm (p1 3.14) |
| lock_picking | very_easy | lock_key | large: 380 mm > 250 mm bed |
| lock_picking | easier | key_cradle_0_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | easier | key_cradle_0_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | easier | key_cradle_1_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | easier | key_cradle_1_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | easier | key_tray | large: 400 mm > 250 mm bed |
| lock_picking | easier | lock_base | large: 885 mm > 250 mm bed |
| lock_picking | easier | lock_disc_0 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | easier | lock_disc_1 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | easier | lock_frame_0 | large: 270 mm > 250 mm bed |
| lock_picking | easier | lock_frame_1 | large: 270 mm > 250 mm bed |
| lock_picking | easier | lock_key | local thin spot/knife edge: min 1.00 mm (p1 3.14) |
| lock_picking | easier | lock_key | large: 380 mm > 250 mm bed |
| lock_picking | easy | key_cradle_0_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | easy | key_cradle_0_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | easy | key_cradle_1_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | easy | key_cradle_1_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | easy | key_tray | large: 550 mm > 250 mm bed |
| lock_picking | easy | lock_base | large: 1185 mm > 250 mm bed |
| lock_picking | easy | lock_disc_0 | local thin spot/knife edge: min 1.45 mm (p1 7.32) |
| lock_picking | easy | lock_disc_2 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | easy | lock_frame_0 | large: 270 mm > 250 mm bed |
| lock_picking | easy | lock_frame_1 | large: 270 mm > 250 mm bed |
| lock_picking | easy | lock_frame_2 | large: 270 mm > 250 mm bed |
| lock_picking | easy | lock_key | local thin spot/knife edge: min 1.03 mm (p1 2.75) |
| lock_picking | easy | lock_key | large: 530 mm > 250 mm bed |
| lock_picking | medium | key_cradle_0_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | medium | key_cradle_0_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | medium | key_cradle_1_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | medium | key_cradle_1_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | medium | key_tray | large: 550 mm > 250 mm bed |
| lock_picking | medium | lock_base | large: 1185 mm > 250 mm bed |
| lock_picking | medium | lock_disc_2 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | medium | lock_frame_0 | large: 270 mm > 250 mm bed |
| lock_picking | medium | lock_frame_1 | large: 270 mm > 250 mm bed |
| lock_picking | medium | lock_frame_2 | large: 270 mm > 250 mm bed |
| lock_picking | medium | lock_key | local thin spot/knife edge: min 1.03 mm (p1 2.75) |
| lock_picking | medium | lock_key | large: 530 mm > 250 mm bed |
| lock_picking | hard | key_cradle_0_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | hard | key_cradle_0_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | hard | key_cradle_1_0 | thin: wall p1 0.24 mm, min 0.01 mm |
| lock_picking | hard | key_cradle_1_1 | thin: wall p1 0.26 mm, min 0.01 mm |
| lock_picking | hard | key_tray | large: 550 mm > 250 mm bed |
| lock_picking | hard | lock_base | large: 1185 mm > 250 mm bed |
| lock_picking | hard | lock_disc_0 | local thin spot/knife edge: min 1.08 mm (p1 2.34) |
| lock_picking | hard | lock_disc_1 | local thin spot/knife edge: min 0.15 mm (p1 8.01) |
| lock_picking | hard | lock_disc_2 | local thin spot/knife edge: min 1.10 mm (p1 7.99) |
| lock_picking | hard | lock_frame_0 | large: 270 mm > 250 mm bed |
| lock_picking | hard | lock_frame_1 | large: 270 mm > 250 mm bed |
| lock_picking | hard | lock_frame_2 | large: 270 mm > 250 mm bed |
| lock_picking | hard | lock_key | local thin spot/knife edge: min 1.03 mm (p1 2.75) |
| lock_picking | hard | lock_key | large: 530 mm > 250 mm bed |
| buzz_wire_3d | very_easy | wire_base | local thin spot/knife edge: min 0.28 mm (p1 6.00) |
| buzz_wire_3d | very_easy | wire_base | large: 520 mm > 250 mm bed |
| buzz_wire_3d | easier | wire_base | local thin spot/knife edge: min 0.28 mm (p1 6.00) |
| buzz_wire_3d | easier | wire_base | large: 520 mm > 250 mm bed |
| buzz_wire_3d | easy | wire_base | local thin spot/knife edge: min 0.28 mm (p1 6.00) |
| buzz_wire_3d | easy | wire_base | large: 520 mm > 250 mm bed |
| buzz_wire_3d | medium | wire_base | local thin spot/knife edge: min 0.28 mm (p1 6.00) |
| buzz_wire_3d | medium | wire_base | large: 520 mm > 250 mm bed |
| buzz_wire_3d | hard | wire_base | local thin spot/knife edge: min 0.82 mm (p1 6.00) |
| buzz_wire_3d | hard | wire_base | large: 520 mm > 250 mm bed |
| fiber_bundling | very_easy | cable_terminal_box | large: 302 mm > 250 mm bed |
| fiber_bundling | easier | cable_terminal_box | large: 302 mm > 250 mm bed |
| fiber_bundling | easy | cable_terminal_box | large: 302 mm > 250 mm bed |
| fiber_bundling | medium | cable_terminal_box | large: 302 mm > 250 mm bed |
| fiber_bundling | hard | cable_terminal_box | large: 302 mm > 250 mm bed |
| rope_threading | easy | R1_stand | large: 332 mm > 250 mm bed |
| rope_threading | easy | R2_stand | large: 311 mm > 250 mm bed |
| rope_threading | medium | R1_stand | large: 332 mm > 250 mm bed |
| rope_threading | medium | R2_stand | large: 311 mm > 250 mm bed |
| rope_threading | medium | R3_stand | large: 281 mm > 250 mm bed |
| rope_threading | hard | R1_stand | large: 332 mm > 250 mm bed |
| rope_threading | hard | R2_stand | large: 311 mm > 250 mm bed |
| rope_threading | hard | R3_stand | large: 281 mm > 250 mm bed |

### Design clearances that matter for a real build

From the generators' own reports (per tier in `start_state.md`) and the measured start layouts:

| family | tier | clearance (mm) | what |
|---|---|---|---|
| interlocked_claws | very_easy | 4.00 | `dimensions.short_leg_gap_m` |
| interlocked_claws | very_easy | 4.00 | `initial_surface_gap_m` |
| interlocked_claws | easier | 9.00 | `dimensions.head_frame_gap_m` |
| interlocked_claws | easier | 8.00 | `initial_surface_gap_m` |
| interlocked_claws | medium | 4.52 | `initial_surface_gap_m` |
| interlocked_claws | hard | 9.43 | `initial_surface_clearance_m` |
| cast_coil | very_easy | 0.30 **(<0.5)** | `final_pair_clearance_m` |
| cast_coil | easier | 0.30 **(<0.5)** | `final_pair_clearance_m` |
| cast_coil | easy | 0.75 | `minimum_initial_clearance_m` |
| cast_coil | medium | 0.75 | `minimum_initial_clearance_m` |
| cast_coil | hard | 0.75 | `minimum_initial_clearance_m` |
| cast_keyhole | very_easy | 4.81 | `minimum_initial_surface_clearance_m` |
| cast_keyhole | easier | 4.81 | `minimum_initial_surface_clearance_m` |
| cast_keyhole | easy | 3.90 | `minimum_initial_surface_clearance_m` |
| cast_keyhole | medium | 0.63 | `minimum_initial_surface_clearance_m` |
| cast_keyhole | hard | 3.90 | `minimum_initial_surface_clearance_m` |
| hedgehog_in_cage | very_easy | 0.30 **(<0.5)** | `initial_pose.clearance_to_cage_m` |
| hedgehog_in_cage | easier | 0.30 **(<0.5)** | `initial_pose.clearance_to_cage_m` |
| hedgehog_in_cage | easy | 0.99 | `initial_pose.minimum_conservative_clearance_m` |
| horseshoe_ring | very_easy | 1.89 | `minimum_clearance_lower_bound_m` |
| horseshoe_ring | easier | 1.89 | `minimum_clearance_lower_bound_m` |
| horseshoe_ring | easy | 1.89 | `minimum_clearance_lower_bound_m` |
| horseshoe_ring | medium | 1.52 | `minimum_clearance_lower_bound_m` |
| horseshoe_ring | hard | 1.65 | `minimum_clearance_lower_bound_m` |
| buzz_wire_3d | very_easy | 12.67 | `nominal_radial_clearance_m` |
| buzz_wire_3d | easier | 12.67 | `nominal_radial_clearance_m` |
| buzz_wire_3d | easy | 12.67 | `nominal_radial_clearance_m` |
| buzz_wire_3d | medium | 12.67 | `nominal_radial_clearance_m` |
| buzz_wire_3d | hard | 12.67 | `nominal_radial_clearance_m` |
| fiber_bundling | very_easy | 13.60 | `fiber_min_initial_surface_clearance_m` |
| fiber_bundling | very_easy | 1.48 | `trunk_radial_clearance_m` |
| fiber_bundling | very_easy | 11.67 | `coarse_min_initial_surface_clearance_m` |
| fiber_bundling | easier | 11.46 | `fiber_min_initial_surface_clearance_m` |
| fiber_bundling | easier | 1.48 | `trunk_radial_clearance_m` |
| fiber_bundling | easier | 11.67 | `coarse_min_initial_surface_clearance_m` |
| fiber_bundling | easy | 8.91 | `fiber_min_initial_surface_clearance_m` |
| fiber_bundling | easy | 1.48 | `trunk_radial_clearance_m` |
| fiber_bundling | easy | 11.67 | `coarse_min_initial_surface_clearance_m` |
| fiber_bundling | medium | 3.72 | `fiber_min_initial_surface_clearance_m` |
| fiber_bundling | medium | 1.48 | `trunk_radial_clearance_m` |
| fiber_bundling | medium | 11.67 | `coarse_min_initial_surface_clearance_m` |
| fiber_bundling | hard | 0.72 | `fiber_min_initial_surface_clearance_m` |
| fiber_bundling | hard | 1.48 | `trunk_radial_clearance_m` |
| fiber_bundling | hard | 11.67 | `coarse_min_initial_surface_clearance_m` |

Puzzle clearances were designed for a simulator with exact geometry and no friction variation. Whether to scale or add tolerance is entirely your call. For reference, the tightest clearances are under ~0.5 mm (cast_coil 0.30-0.75 mm, cast_keyhole medium 0.63 mm, hedgehog 0.3-1.0 mm, fiber_bundling ring over the jacket 1.48 mm and strands 0.72 mm in hard). Two options if your printer needs room: print all parts of a tier at the same larger scale, or offset the mating faces by the printer's tolerance (typically 0.2-0.4 mm per face for FDM). If you scale, check the ALOHA (max opening about 74 mm) and Robotiq 2F-85 (85 mm) strokes against the grasped part sizes.

## Shared parts

Identical STLs (same geometry to 0.001 mm) that appear in several tiers of a family; each tier folder still has its own copy. A part name listed twice means two different shapes, each shared by the tiers in brackets.

- **cast_coil**: `coil_silver` (easy, medium, hard)
- **cast_keyhole**: `keyhole_silver` (easy, medium, hard); `keyhole_silver` (very_easy, easier)
- **hedgehog_in_cage**: `hedgehog_ball` (very_easy, easier, easy, medium); `hedgehog_mount` (very_easy, easier, easy, medium, hard)
- **horseshoe_ring**: `chain_lower_1` (very_easy, easier, easy, medium, hard); `chain_upper_1` (very_easy, easier, easy, medium, hard); `horseshoe_left` (very_easy, easier, easy); `horseshoe_right` (very_easy, easier, easy)
- **lock_picking**: `key_cradle_0_0` (very_easy, easier, easy, medium, hard); `key_cradle_0_1` (very_easy, easier, easy, medium, hard); `key_cradle_1_0` (very_easy, easier, easy, medium, hard); `key_cradle_1_1` (very_easy, easier, easy, medium, hard); `key_tray` (easy, medium, hard); `key_tray` (very_easy, easier); `key_tray_post_0` (very_easy, easier, easy, medium, hard); `key_tray_post_1` (very_easy, easier, easy, medium, hard); `lock_base` (easy, medium, hard); `lock_base` (very_easy, easier); `lock_disc_0` (very_easy, easier); `lock_disc_1` (very_easy, easier); `lock_disc_2` (easy, medium, hard); `lock_frame_0` (easy, medium); `lock_frame_1` (very_easy, easier); `lock_frame_2` (easy, medium, hard); `lock_goal` (very_easy, easier, easy, medium, hard); `lock_goal_post` (very_easy, easier, easy, medium, hard); `lock_key` (easy, medium, hard); `lock_key` (very_easy, easier)
- **buzz_wire_3d**: `wand` (very_easy, easier, easy, medium, hard); `wire_base` (very_easy, easier, easy, medium); `wire_wood_stop_0` (very_easy, easier, easy, medium, hard); `wire_wood_stop_1` (very_easy, easier, easy, medium, hard)
- **fiber_bundling**: `bundling_ring` (very_easy, easier, easy, medium, hard); `cable_cradle_base` (very_easy, easier, easy, medium, hard); `cable_cradle_left` (very_easy, easier, easy, medium, hard); `cable_cradle_pad` (very_easy, easier, easy, medium, hard); `cable_cradle_post` (very_easy, easier, easy, medium, hard); `cable_cradle_right` (very_easy, easier, easy, medium, hard); `cable_terminal_box` (very_easy, easier, easy, medium, hard); `ring_mount_base` (very_easy, easier, easy, medium, hard); `ring_mount_post` (very_easy, easier, easy, medium, hard)
- **rope_threading**: `R1` (easy, medium); `R1_base` (easy, medium, hard); `R1_stand` (easy, medium); `R2` (easy, medium); `R2_base` (easy, medium, hard); `R2_stand` (easy, medium, hard); `R3_base` (medium, hard); `left_base_riser` (easy, medium, hard); `right_base_riser` (easy, medium, hard)

## Caveats

- Masses, friction and stiffness were simulator parameters (in `start_state.md` where they matter); printed parts will weigh and slide differently.
- The simulator gave grasps an assist (a rigid weld once the fingers close on a part); real grasps need suitable finger pads, and some parts may need flats or grip features.
- interlocked_claws starts with both grippers already holding the pieces in the air; all other tasks start with the objects at rest.
- buzz_wire_3d medium and hard have near-sharp corners in the wire (sampled bend radius 2.0 and 1.3 mm, less than the 1.47 mm wire radius): bend them as tight as the rod allows; the reference tube self-intersects there.
- Measured start gaps of a few hundredths of a millimetre are resting contacts of the settled start pose.
- The buzz-wire deck (520 x 385 x 142 mm), the lock base (up to 1185 mm), the cable terminal box (247 x 180 x 302 mm) and the long key exceed common print beds: build them from wood/sheet or print in sections.
